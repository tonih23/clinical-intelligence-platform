"""
Tests del parser de PubMed.

Probamos el parser con un fragmento XML real de PubMed (estructura
representativa). No tocamos red, no tocamos DB; son unit tests rápidos.
"""

import xml.etree.ElementTree as ET
from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest

from cip.pubmed import ESEARCH_URL, PubMedClient, _parse_pubmed_xml

SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">12345678</PMID>
      <Article>
        <Journal>
          <Title>Nature Reviews Drug Discovery</Title>
          <JournalIssue>
            <PubDate>
              <Year>2023</Year>
              <Month>Jun</Month>
            </PubDate>
          </JournalIssue>
        </Journal>
        <ArticleTitle>Complement system in rare diseases.</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">The complement system plays a key role.</AbstractText>
          <AbstractText Label="METHODS">We reviewed recent literature.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author>
            <LastName>Smith</LastName>
            <ForeName>John</ForeName>
          </Author>
          <Author>
            <LastName>Doe</LastName>
            <ForeName>Jane</ForeName>
          </Author>
        </AuthorList>
      </Article>
      <MeshHeadingList>
        <MeshHeading>
          <DescriptorName UI="D003165">Complement System</DescriptorName>
        </MeshHeading>
        <MeshHeading>
          <DescriptorName UI="D035583">Rare Diseases</DescriptorName>
        </MeshHeading>
      </MeshHeadingList>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">12345678</ArticleId>
        <ArticleId IdType="doi">10.1038/example.2023.001</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""

MULTI_ARTICLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">111</PMID>
      <Article>
        <Journal><Title>Journal One</Title></Journal>
        <ArticleTitle>First article title.</ArticleTitle>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">222</PMID>
      <Article>
        <Journal><Title>Journal Two</Title></Journal>
        <ArticleTitle>Second unrelated article.</ArticleTitle>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


class FakeAsyncClient:
    def __init__(self, outcomes: list[httpx.Response | Exception]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    async def get(self, _url: str, *, params: dict[str, str]) -> httpx.Response:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code, request=httpx.Request("GET", ESEARCH_URL))


@pytest.fixture
def no_retry_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[float], Coroutine[Any, Any, None]]:
    async def sleep(_: float) -> None:
        return None

    monkeypatch.setattr("cip.pubmed.asyncio.sleep", sleep)
    return sleep


def test_parse_pubmed_xml_returns_one_paper() -> None:
    papers = _parse_pubmed_xml(SAMPLE_XML)
    assert len(papers) == 1


def test_parse_pubmed_xml_basic_fields() -> None:
    papers = _parse_pubmed_xml(SAMPLE_XML)
    p = papers[0]

    assert p.pmid == "12345678"
    assert p.title == "Complement system in rare diseases."
    assert p.journal == "Nature Reviews Drug Discovery"
    assert p.publication_year == 2023
    assert p.doi == "10.1038/example.2023.001"


def test_parse_pubmed_xml_abstract_concatenated() -> None:
    papers = _parse_pubmed_xml(SAMPLE_XML)
    p = papers[0]

    assert p.abstract is not None
    assert "complement system" in p.abstract.lower()
    assert "reviewed recent literature" in p.abstract.lower()


def test_parse_pubmed_xml_authors() -> None:
    papers = _parse_pubmed_xml(SAMPLE_XML)
    p = papers[0]

    assert p.authors == ["Smith, John", "Doe, Jane"]


def test_parse_pubmed_xml_mesh_terms() -> None:
    papers = _parse_pubmed_xml(SAMPLE_XML)
    p = papers[0]

    assert "Complement System" in p.mesh_terms
    assert "Rare Diseases" in p.mesh_terms


def test_parse_pubmed_xml_empty_returns_empty_list() -> None:
    empty_xml = b"<?xml version='1.0'?><PubmedArticleSet></PubmedArticleSet>"
    assert _parse_pubmed_xml(empty_xml) == []


def test_parse_pubmed_xml_raw_xml_is_scoped_to_each_article() -> None:
    papers = _parse_pubmed_xml(MULTI_ARTICLE_XML)
    by_pmid = {paper.pmid: paper for paper in papers}

    assert set(by_pmid) == {"111", "222"}
    assert b"Second unrelated article" not in by_pmid["111"].raw_xml
    assert b"First article title" not in by_pmid["222"].raw_xml

    first_root = ET.fromstring(by_pmid["111"].raw_xml)
    assert first_root.tag == "PubmedArticleSet"
    assert len(first_root.findall("PubmedArticle")) == 1


@pytest.mark.asyncio
async def test_request_does_not_retry_permanent_4xx(no_retry_sleep: object) -> None:
    client = PubMedClient(max_retries=3)
    fake_client = FakeAsyncClient([response(400)])
    client._client = fake_client  # type: ignore[assignment]

    with pytest.raises(httpx.HTTPStatusError):
        await client._request(ESEARCH_URL, {"db": "pubmed"})

    assert fake_client.calls == 1


@pytest.mark.asyncio
async def test_request_retries_transient_status(no_retry_sleep: object) -> None:
    client = PubMedClient(max_retries=3)
    fake_client = FakeAsyncClient([response(500), response(200)])
    client._client = fake_client  # type: ignore[assignment]

    resp = await client._request(ESEARCH_URL, {"db": "pubmed"})

    assert resp.status_code == 200
    assert fake_client.calls == 2


@pytest.mark.asyncio
async def test_request_retries_timeouts(no_retry_sleep: object) -> None:
    request = httpx.Request("GET", ESEARCH_URL)
    client = PubMedClient(max_retries=3)
    fake_client = FakeAsyncClient([httpx.ReadTimeout("timed out", request=request), response(200)])
    client._client = fake_client  # type: ignore[assignment]

    resp = await client._request(ESEARCH_URL, {"db": "pubmed"})

    assert resp.status_code == 200
    assert fake_client.calls == 2
