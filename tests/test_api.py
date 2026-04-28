"""Tests mínimos de endpoints API sin tocar servicios externos."""

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient

from cip import api as api_module
from cip.db import Paper


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> Iterator[None]:
    api_module.app.dependency_overrides.clear()
    yield
    api_module.app.dependency_overrides.clear()


class HealthySession:
    async def execute(self, statement: object) -> None:
        self.statement = statement


class PaperSession:
    def __init__(self, paper: Paper | None) -> None:
        self.paper = paper

    async def get(self, model: type[Paper], pmid: str) -> Paper | None:
        if self.paper is None or self.paper.pmid != pmid:
            return None
        return self.paper


class FakeStorage:
    bucket = "pubmed-raw"

    def presigned_get_url(self, key: str, expires_seconds: int = 3600) -> str:
        assert key == "pubmed/12/123.xml"
        assert expires_seconds == 3600
        return "http://minio:9000/pubmed-raw/pubmed/12/123.xml?signature=test"


def test_health_returns_ok() -> None:
    with TestClient(api_module.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_health_ready_checks_database() -> None:
    async def override_session() -> AsyncIterator[HealthySession]:
        yield HealthySession()

    api_module.app.dependency_overrides[api_module.get_session] = override_session

    with TestClient(api_module.app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0", "database": "ok"}


def test_get_paper_raw_returns_presigned_url(monkeypatch: pytest.MonkeyPatch) -> None:
    paper = Paper(
        pmid="123",
        title="Example",
        raw_s3_key="pubmed/12/123.xml",
    )

    async def override_session() -> AsyncIterator[PaperSession]:
        yield PaperSession(paper)

    api_module.app.dependency_overrides[api_module.get_session] = override_session
    monkeypatch.setattr(api_module, "ObjectStorage", FakeStorage)

    with TestClient(api_module.app) as client:
        response = client.get("/papers/123/raw")

    assert response.status_code == 200
    assert response.json() == {
        "pmid": "123",
        "s3_bucket": "pubmed-raw",
        "s3_key": "pubmed/12/123.xml",
        "presigned_url": "http://minio:9000/pubmed-raw/pubmed/12/123.xml?signature=test",
    }
