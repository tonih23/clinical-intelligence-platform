"""
Capa de persistencia: modelos ORM y sesión async de SQLAlchemy.

Decisiones:

- SQLAlchemy 2.0 con la API async (asyncpg como driver).
- Mapped[] + DeclarativeBase: la sintaxis moderna de SQLAlchemy 2.0,
  con tipado estático real (mypy no se queja).
- Una tabla `papers` (la entidad principal) y una `ingest_runs` (auditoría
  de cuándo se ejecutó la ingesta y cuántos papers procesó).
- En Sprint 2 añadimos Alembic para migraciones; aquí, por simplicidad,
  creamos las tablas con `Base.metadata.create_all()` desde db_init.py.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from cip.config import get_settings


# ============================================================
# Base declarativa
# ============================================================
class Base(DeclarativeBase):
    """Base de todos los modelos ORM."""


# ============================================================
# Modelos
# ============================================================
class Paper(Base):
    """Un artículo científico de PubMed."""

    __tablename__ = "papers"

    # PMID es el identificador único de PubMed (un entero como string).
    # Lo usamos como clave primaria.
    pmid: Mapped[str] = mapped_column(String(20), primary_key=True)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    journal: Mapped[str | None] = mapped_column(String(500), nullable=True)
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Authors y MeSH terms los guardamos como JSON-en-texto (lista separada por |)
    # En Sprint 2 los normalizamos a tablas auxiliares.
    authors: Mapped[str | None] = mapped_column(Text, nullable=True)
    mesh_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Ruta en S3 al XML crudo (por si queremos reprocesar)
    raw_s3_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Índices secundarios para búsquedas comunes
    __table_args__ = (
        Index("ix_papers_journal", "journal"),
        Index("ix_papers_publication_year", "publication_year"),
    )

    def __repr__(self) -> str:
        return f"<Paper pmid={self.pmid!r} title={self.title[:40]!r}>"


class IngestRun(Base):
    """Registro de cada ejecución del pipeline de ingesta."""

    __tablename__ = "ingest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    max_results: Mapped[int] = mapped_column(Integer, nullable=False)
    papers_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    papers_inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    papers_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


# ============================================================
# Engine y sesión
# ============================================================
_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Devuelve el engine async (lazy singleton)."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.postgres_dsn,
            echo=False,            # True para ver el SQL generado en logs
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,    # detecta conexiones zombie tras un reinicio de Postgres
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Devuelve el sessionmaker async (lazy singleton)."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,  # típico en código async para evitar lazy-loads accidentales
            class_=AsyncSession,
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependencia FastAPI: inyecta una sesión por request."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session
