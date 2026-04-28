"""
Pipeline de ingesta: PubMed -> Postgres + MinIO.

Flujo:
  1. esearch para obtener PMIDs.
  2. efetch en lotes para descargar el XML.
  3. Por cada paper:
       - Subir el XML crudo a MinIO (deduplicado por PMID).
       - Insertar/actualizar el registro en Postgres (upsert).
  4. Registrar la run en `ingest_runs` para auditoría.

Uso:

    docker compose exec api python -m cip.ingest \\
        --query "complement system" --max-results 100

    # Otra query útil para tu contexto:
    docker compose exec api python -m cip.ingest \\
        --query "rare disease drug development" --max-results 200

Idempotencia: si vuelves a correr la misma query, los PMIDs ya existentes
se actualizan (upsert), no se duplican. Esto es básico en data engineering:
todo pipeline debe poder reejecutarse sin romper nada.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import typer
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cip.db import IngestRun, Paper, get_sessionmaker
from cip.logging_setup import configure_logging, get_logger
from cip.pubmed import PubMedClient, PubMedPaper
from cip.storage import ObjectStorage

log = get_logger(__name__)


def _s3_key_for(pmid: str) -> str:
    """Esquema de keys en S3: prefijo por sharding básico."""
    return f"pubmed/{pmid[:2]}/{pmid}.xml"


async def _upsert_paper(session: AsyncSession, paper: PubMedPaper, raw_s3_key: str) -> bool:
    """
    Inserta o actualiza un Paper. Devuelve True si fue insert (nuevo), False si fue update.

    Usamos `INSERT ... ON CONFLICT DO UPDATE` (Postgres-specific) porque es
    atómico y mucho más eficiente que `SELECT then INSERT/UPDATE`.
    """
    values: dict[str, str | int | None] = {
        "pmid": paper.pmid,
        "title": paper.title,
        "abstract": paper.abstract,
        "journal": paper.journal,
        "publication_year": paper.publication_year,
        "authors": "|".join(paper.authors) if paper.authors else None,
        "mesh_terms": "|".join(paper.mesh_terms) if paper.mesh_terms else None,
        "doi": paper.doi,
        "raw_s3_key": raw_s3_key,
    }

    # Comprobamos si existía para reportar insert vs update. Es una métrica operativa
    # ligera, no un contador atómico perfecto bajo escritores concurrentes.
    existed = await session.scalar(select(Paper.pmid).where(Paper.pmid == paper.pmid))

    stmt = pg_insert(Paper).values(**values)
    update_values: dict[str, str | int | datetime | None] = {
        k: v for k, v in values.items() if k != "pmid"
    }
    update_values["updated_at"] = datetime.now(UTC)
    stmt = stmt.on_conflict_do_update(
        index_elements=["pmid"],
        set_=update_values,
    )
    await session.execute(stmt)
    return existed is None


async def run_ingest(query: str, max_results: int) -> None:
    """Función principal del pipeline."""
    sessionmaker = get_sessionmaker()
    storage = ObjectStorage()
    storage.ensure_bucket()

    inserted = updated = fetched = 0

    # 1. Crear el registro de run
    async with sessionmaker() as session:
        ingest_run = IngestRun(query=query, max_results=max_results, status="running")
        session.add(ingest_run)
        await session.commit()
        await session.refresh(ingest_run)
        run_id = ingest_run.id
        log.info("ingest_run_started", run_id=run_id, query=query, max_results=max_results)

    try:
        async with PubMedClient() as pubmed:
            # 2. Buscar PMIDs
            pmids = await pubmed.search_pmids(query, max_results=max_results)
            if not pmids:
                log.warning("no_pmids_found", query=query)
            else:
                # 3. Descargar y persistir
                async with sessionmaker() as session:
                    async for paper in pubmed.fetch_papers(pmids):
                        fetched += 1

                        # 3a. Subir XML a MinIO (idempotente por key)
                        s3_key = _s3_key_for(paper.pmid)
                        if not storage.object_exists(s3_key):
                            storage.put_object(
                                s3_key,
                                paper.raw_xml,
                                content_type="application/xml",
                            )

                        # 3b. Upsert en Postgres
                        is_new = await _upsert_paper(session, paper, s3_key)
                        if is_new:
                            inserted += 1
                        else:
                            updated += 1

                        # Commit cada 50 papers para no acumular una transacción enorme
                        if fetched % 50 == 0:
                            await session.commit()
                            log.info(
                                "ingest_progress",
                                fetched=fetched,
                                inserted=inserted,
                                updated=updated,
                            )

                    await session.commit()

        # 4. Marcar la run como completada
        async with sessionmaker() as session:
            completed_run = await session.get(IngestRun, run_id)
            if completed_run is not None:
                completed_run.papers_fetched = fetched
                completed_run.papers_inserted = inserted
                completed_run.papers_updated = updated
                completed_run.status = "success"
                completed_run.finished_at = datetime.now(UTC)
                await session.commit()

        log.info(
            "ingest_run_done",
            run_id=run_id,
            fetched=fetched,
            inserted=inserted,
            updated=updated,
        )

    except Exception as exc:
        log.exception("ingest_run_failed", run_id=run_id, error=str(exc))
        async with sessionmaker() as session:
            failed_run = await session.get(IngestRun, run_id)
            if failed_run is not None:
                failed_run.status = "failed"
                failed_run.error_message = str(exc)
                failed_run.finished_at = datetime.now(UTC)
                await session.commit()
        raise


# ============================================================
# CLI
# ============================================================
app = typer.Typer(add_completion=False, help="Pipeline de ingesta de PubMed.")


@app.command()
def main(
    query: str = typer.Option(..., "--query", "-q", help="Query PubMed (ej. 'complement system')."),
    max_results: int = typer.Option(100, "--max-results", "-n", min=1, max=10000),
) -> None:
    """Lanza la ingesta."""
    configure_logging()
    asyncio.run(run_ingest(query=query, max_results=max_results))


if __name__ == "__main__":
    app()
