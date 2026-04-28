"""
Cliente para la API E-utilities del NCBI (PubMed).

E-utilities expone endpoints HTTP que devuelven XML:
  - esearch : busca PMIDs que matchean una query.
  - efetch  : descarga el detalle de uno o varios PMIDs.

Documentación oficial:
  https://www.ncbi.nlm.nih.gov/books/NBK25501/

Rate limits:
  - Sin API key : 3 req/s.
  - Con API key : 10 req/s. La key es gratis (registro NCBI).

Buenas prácticas:
  - Identifícate con tool y email (los rate limits y bans se aplican por user-agent).
  - Procesa los PMIDs en lotes de 200 (PubMed soporta hasta ~10k pero los lotes de 200
    son el sweet-spot para fiabilidad y memoria).
  - Implementa retries exponenciales en errores transitorios (408, 429, 5xx).

Lo que aprendes aquí: cómo se integran APIs externas en serio, no con
requests.get sin manejo de nada.
"""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import cast

import httpx

from cip.config import get_settings
from cip.logging_setup import get_logger

log = get_logger(__name__)

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ESEARCH_URL = f"{EUTILS_BASE}/esearch.fcgi"
EFETCH_URL = f"{EUTILS_BASE}/efetch.fcgi"
TRANSIENT_HTTP_STATUS_CODES = {408, 429, 500, 502, 503, 504}


@dataclass(slots=True)
class PubMedPaper:
    """Representación in-memory de un paper. Se mapea a `Paper` ORM en el ingest."""

    pmid: str
    title: str
    abstract: str | None
    journal: str | None
    publication_year: int | None
    authors: list[str]
    mesh_terms: list[str]
    doi: str | None
    raw_xml: bytes  # el XML original, lo guardaremos en S3


class PubMedClient:
    """Cliente async para PubMed E-utilities."""

    def __init__(self, batch_size: int = 200, max_retries: int = 3) -> None:
        settings = get_settings()
        self.api_key = settings.pubmed_api_key or None
        self.tool = settings.pubmed_tool_name
        self.email = settings.pubmed_email
        self.batch_size = batch_size
        self.max_retries = max_retries

        # Rate limit: 10 req/s con key, 3 sin. Convertido a delay entre requests.
        self._delay_s = 0.11 if self.api_key else 0.34

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

    async def __aenter__(self) -> PubMedClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._client.aclose()

    # --------------------------------------------------------
    # Helpers internos
    # --------------------------------------------------------
    def _common_params(self) -> dict[str, str]:
        params = {"tool": self.tool, "email": self.email}
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    async def _request(self, url: str, params: dict[str, str]) -> httpx.Response:
        """GET con retries exponenciales para errores transitorios."""
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = await self._client.get(url, params=params)
                if resp.status_code in TRANSIENT_HTTP_STATUS_CODES:
                    raise httpx.HTTPStatusError(
                        f"transient {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                resp.raise_for_status()
                return resp
            except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.TransportError) as exc:
                if isinstance(exc, httpx.HTTPStatusError) and (
                    exc.response.status_code not in TRANSIENT_HTTP_STATUS_CODES
                ):
                    raise

                last_exc = exc
                wait = 2**attempt
                log.warning(
                    "pubmed_request_retry",
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    wait_s=wait,
                    error=str(exc),
                )
                await asyncio.sleep(wait)

        assert last_exc is not None
        raise last_exc

    # --------------------------------------------------------
    # API pública
    # --------------------------------------------------------
    async def search_pmids(self, query: str, max_results: int = 100) -> list[str]:
        """Busca PMIDs que matchean una query. Devuelve hasta `max_results`."""
        params = {
            **self._common_params(),
            "db": "pubmed",
            "term": query,
            "retmax": str(max_results),
            "retmode": "xml",
            "sort": "relevance",
        }
        resp = await self._request(ESEARCH_URL, params)
        root = ET.fromstring(resp.text)
        pmids = [el.text for el in root.findall(".//IdList/Id") if el.text]
        log.info("pubmed_search_done", query=query, found=len(pmids))
        await asyncio.sleep(self._delay_s)
        return pmids

    async def fetch_papers(self, pmids: list[str]) -> AsyncIterator[PubMedPaper]:
        """Descarga papers por PMIDs en lotes. Yields PubMedPaper."""
        for i in range(0, len(pmids), self.batch_size):
            batch = pmids[i : i + self.batch_size]
            params = {
                **self._common_params(),
                "db": "pubmed",
                "id": ",".join(batch),
                "retmode": "xml",
                "rettype": "abstract",
            }
            resp = await self._request(EFETCH_URL, params)
            raw_xml = resp.content
            log.info(
                "pubmed_fetch_batch",
                batch_index=i // self.batch_size,
                batch_size=len(batch),
                bytes=len(raw_xml),
            )
            for paper in _parse_pubmed_xml(raw_xml):
                yield paper
            await asyncio.sleep(self._delay_s)


# ============================================================
# Parser XML
# ============================================================
def _parse_pubmed_xml(xml_bytes: bytes) -> list[PubMedPaper]:
    """
    Parsea el XML que devuelve efetch a una lista de PubMedPaper.

    Estructura simplificada del XML:

      <PubmedArticleSet>
        <PubmedArticle>
          <MedlineCitation>
            <PMID>12345</PMID>
            <Article>
              <ArticleTitle>...</ArticleTitle>
              <Abstract><AbstractText>...</AbstractText></Abstract>
              <Journal><Title>...</Title></Journal>
              <AuthorList>
                <Author><LastName>...</LastName><ForeName>...</ForeName></Author>
              </AuthorList>
            </Article>
            <MeshHeadingList>
              <MeshHeading><DescriptorName>...</DescriptorName></MeshHeading>
            </MeshHeadingList>
          </MedlineCitation>
          <PubmedData>
            <ArticleIdList>
              <ArticleId IdType="doi">10.xxxx/...</ArticleId>
            </ArticleIdList>
          </PubmedData>
        </PubmedArticle>
        ...
      </PubmedArticleSet>
    """
    root = ET.fromstring(xml_bytes)
    papers: list[PubMedPaper] = []

    for article in root.findall(".//PubmedArticle"):
        try:
            article_xml = _raw_xml_for_article(article)
            paper = _parse_single_article(article, article_xml)
            if paper is not None:
                papers.append(paper)
        except Exception as exc:
            log.warning("pubmed_parse_error", error=str(exc))
            continue

    return papers


def _raw_xml_for_article(article: ET.Element) -> bytes:
    """Serializa un artículo individual como XML válido y autocontenido."""
    article_xml = cast(bytes, ET.tostring(article, encoding="utf-8"))
    return b'<?xml version="1.0" encoding="utf-8"?>\n<PubmedArticleSet>' + article_xml + (
        b"</PubmedArticleSet>"
    )


def _parse_single_article(article: ET.Element, raw_xml: bytes) -> PubMedPaper | None:
    pmid_el = article.find(".//MedlineCitation/PMID")
    if pmid_el is None or not pmid_el.text:
        return None
    pmid = pmid_el.text.strip()

    title_el = article.find(".//Article/ArticleTitle")
    title = _text_of(title_el) or "(no title)"

    # Abstract puede tener varios <AbstractText> con label="BACKGROUND", "METHODS", etc.
    abstract_parts: list[str] = []
    for el in article.findall(".//Article/Abstract/AbstractText"):
        if text := _text_of(el):
            abstract_parts.append(text)
    abstract = "\n\n".join(abstract_parts) if abstract_parts else None

    journal_el = article.find(".//Article/Journal/Title")
    journal = _text_of(journal_el)

    year_el = article.find(".//Article/Journal/JournalIssue/PubDate/Year")
    publication_year = int(year_el.text) if year_el is not None and year_el.text else None

    authors: list[str] = []
    for author in article.findall(".//Article/AuthorList/Author"):
        last = _text_of(author.find("LastName"))
        first = _text_of(author.find("ForeName"))
        if last and first:
            authors.append(f"{last}, {first}")
        elif last:
            authors.append(last)

    mesh_terms = [
        _text_of(el)
        for el in article.findall(".//MeshHeadingList/MeshHeading/DescriptorName")
        if _text_of(el)
    ]

    doi: str | None = None
    for art_id in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
        if art_id.get("IdType") == "doi" and art_id.text:
            doi = art_id.text.strip()
            break

    return PubMedPaper(
        pmid=pmid,
        title=title,
        abstract=abstract,
        journal=journal,
        publication_year=publication_year,
        authors=authors,
        mesh_terms=[m for m in mesh_terms if m],
        doi=doi,
        raw_xml=raw_xml,
    )


def _text_of(el: ET.Element | None) -> str | None:
    """Devuelve el texto de un elemento, o None si está vacío."""
    if el is None:
        return None
    # `itertext()` concatena texto de hijos también (ej. <i>, <sub> dentro del título)
    text = "".join(el.itertext()).strip()
    return text or None
