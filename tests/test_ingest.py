"""Tests de detalles críticos del upsert de ingesta."""

from sqlalchemy.dialects import postgresql

from cip.ingest import _upsert_paper
from cip.pubmed import PubMedPaper


class FakeSession:
    def __init__(self, existing_pmid: str | None) -> None:
        self.existing_pmid = existing_pmid
        self.statement: object | None = None

    async def scalar(self, statement: object) -> str | None:
        return self.existing_pmid

    async def execute(self, statement: object) -> None:
        self.statement = statement


def sample_paper() -> PubMedPaper:
    return PubMedPaper(
        pmid="123",
        title="Example title",
        abstract="Example abstract",
        journal="Example Journal",
        publication_year=2024,
        authors=["Smith, Jane"],
        mesh_terms=["Complement System"],
        doi="10.1000/example",
        raw_xml=b"<PubmedArticleSet />",
    )


async def test_upsert_paper_sets_updated_at_on_conflict() -> None:
    session = FakeSession(existing_pmid="123")

    is_new = await _upsert_paper(session, sample_paper(), "pubmed/12/123.xml")  # type: ignore[arg-type]

    assert is_new is False
    assert session.statement is not None
    sql = str(session.statement.compile(dialect=postgresql.dialect()))  # type: ignore[attr-defined]
    update_clause = sql.split("DO UPDATE SET", maxsplit=1)[1]
    assert "updated_at" in update_clause


async def test_upsert_paper_reports_insert_when_pmid_did_not_exist() -> None:
    session = FakeSession(existing_pmid=None)

    is_new = await _upsert_paper(session, sample_paper(), "pubmed/12/123.xml")  # type: ignore[arg-type]

    assert is_new is True
