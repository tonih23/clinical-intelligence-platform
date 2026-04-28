"""
API HTTP de la plataforma.

Endpoints (Sprint 1):
  GET /health              -> healthcheck (lo usa Docker y luego Kubernetes)
  GET /papers              -> lista paginada
  GET /papers/{pmid}       -> un paper por PMID
  GET /papers/search?q=... -> búsqueda full-text simple
  GET /papers/{pmid}/raw   -> URL para descargar el XML crudo de S3
  GET /ingest-runs         -> historial de ingestas

Decisiones:
  - FastAPI con dependencias (`Depends`) para inyectar la sesión de DB.
    Es la forma idiomática y testeable.
  - Pydantic v2 para los schemas de respuesta (separados del modelo ORM,
    porque el ORM puede tener campos internos que no quieres exponer).
  - Sin auth en Sprint 1; se añade en Sprint 4.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cip.config import get_settings
from cip.db import IngestRun, Paper, get_session
from cip.logging_setup import configure_logging, get_logger
from cip.storage import ObjectStorage

log = get_logger(__name__)


# ============================================================
# Schemas Pydantic (DTOs de respuesta)
# ============================================================
class PaperRead(BaseModel):
    """Representación de un Paper en respuestas HTTP."""

    model_config = ConfigDict(from_attributes=True)

    pmid: str
    title: str
    abstract: str | None
    journal: str | None
    publication_year: int | None
    authors: list[str]
    mesh_terms: list[str]
    doi: str | None
    raw_s3_key: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_paper(cls, p: Paper) -> "PaperRead":
        """Convierte el modelo ORM (con authors/mesh como string) a la DTO."""
        return cls(
            pmid=p.pmid,
            title=p.title,
            abstract=p.abstract,
            journal=p.journal,
            publication_year=p.publication_year,
            authors=p.authors.split("|") if p.authors else [],
            mesh_terms=p.mesh_terms.split("|") if p.mesh_terms else [],
            doi=p.doi,
            raw_s3_key=p.raw_s3_key,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )


class PaperListResponse(BaseModel):
    items: list[PaperRead]
    total: int
    limit: int
    offset: int


class IngestRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    query: str
    max_results: int
    papers_fetched: int
    papers_inserted: int
    papers_updated: int
    status: str
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str


# ============================================================
# App
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    """Lifespan handler: startup/shutdown."""
    configure_logging()
    log.info("api_starting", version="0.1.0")
    yield
    log.info("api_shutting_down")


app = FastAPI(
    title="Clinical Intelligence Platform",
    description="Sprint 1 — ingesta y consulta de papers de PubMed.",
    version="0.1.0",
    lifespan=lifespan,
)


# ============================================================
# Endpoints
# ============================================================
@app.get("/health", response_model=HealthResponse, tags=["meta"])
async def health() -> HealthResponse:
    """Healthcheck. Devuelve 200 si el proceso está vivo."""
    return HealthResponse(version="0.1.0")


@app.get("/papers", response_model=PaperListResponse, tags=["papers"])
async def list_papers(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    journal: str | None = Query(None, description="Filtrar por nombre exacto de journal"),
    year: int | None = Query(None, description="Filtrar por año de publicación"),
) -> PaperListResponse:
    """Lista papers con paginación y filtros simples."""
    stmt = select(Paper).order_by(desc(Paper.created_at))
    count_stmt = select(func.count()).select_from(Paper)

    if journal:
        stmt = stmt.where(Paper.journal == journal)
        count_stmt = count_stmt.where(Paper.journal == journal)
    if year:
        stmt = stmt.where(Paper.publication_year == year)
        count_stmt = count_stmt.where(Paper.publication_year == year)

    stmt = stmt.limit(limit).offset(offset)

    total = await session.scalar(count_stmt) or 0
    result = await session.execute(stmt)
    papers = result.scalars().all()

    return PaperListResponse(
        items=[PaperRead.from_orm_paper(p) for p in papers],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/papers/search", response_model=PaperListResponse, tags=["papers"])
async def search_papers(
    session: Annotated[AsyncSession, Depends(get_session)],
    q: str = Query(..., min_length=2, description="Texto a buscar en título o abstract"),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaperListResponse:
    """
    Búsqueda full-text muy básica (ILIKE).

    En Sprint 3 reemplazamos esto por Elasticsearch con BM25 + dense vectors.
    """
    pattern = f"%{q}%"
    stmt = (
        select(Paper)
        .where(or_(Paper.title.ilike(pattern), Paper.abstract.ilike(pattern)))
        .order_by(desc(Paper.created_at))
        .limit(limit)
        .offset(offset)
    )
    count_stmt = (
        select(func.count())
        .select_from(Paper)
        .where(or_(Paper.title.ilike(pattern), Paper.abstract.ilike(pattern)))
    )

    total = await session.scalar(count_stmt) or 0
    result = await session.execute(stmt)
    papers = result.scalars().all()

    return PaperListResponse(
        items=[PaperRead.from_orm_paper(p) for p in papers],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/papers/{pmid}", response_model=PaperRead, tags=["papers"])
async def get_paper(
    pmid: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PaperRead:
    """Devuelve un paper por su PMID."""
    paper = await session.get(Paper, pmid)
    if paper is None:
        raise HTTPException(status_code=404, detail=f"Paper PMID={pmid} not found")
    return PaperRead.from_orm_paper(paper)


@app.get("/papers/{pmid}/raw", tags=["papers"])
async def get_paper_raw(
    pmid: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    """Devuelve metadata para descargar el XML crudo de S3."""
    paper = await session.get(Paper, pmid)
    if paper is None or paper.raw_s3_key is None:
        raise HTTPException(status_code=404, detail="Raw XML not found for this PMID")

    settings = get_settings()
    return {
        "pmid": pmid,
        "s3_bucket": settings.s3_bucket,
        "s3_key": paper.raw_s3_key,
        "console_url": (
            f"http://localhost:9001/browser/{settings.s3_bucket}/"
            f"{paper.raw_s3_key.replace('/', '%2F')}"
        ),
    }


@app.get("/ingest-runs", response_model=list[IngestRunRead], tags=["ingest"])
async def list_ingest_runs(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(20, ge=1, le=100),
) -> list[IngestRunRead]:
    """Historial de ejecuciones del pipeline de ingesta."""
    stmt = select(IngestRun).order_by(desc(IngestRun.started_at)).limit(limit)
    result = await session.execute(stmt)
    runs = result.scalars().all()
    return [IngestRunRead.model_validate(r) for r in runs]
