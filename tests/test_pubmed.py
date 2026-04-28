"""
Tests del parser de PubMed.

Probamos el parser con un fragmento XML real de PubMed (estructura
representativa). No tocamos red, no tocamos DB; son unit tests rápidos.
"""

from cip.pubmed import _parse_pubmed_xml

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
