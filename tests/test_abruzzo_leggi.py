"""Abruzzo publication-text tools: verification and source integrity."""
from dataclasses import dataclass
from types import SimpleNamespace
import pytest
from src.tools import gazzetta


@dataclass
class FakeResult:
    codice_redazionale: str = "24R00001"
    data_pubblicazione: str = "2024-09-21"
    title: str = "Nuova legge urbanistica sul governo del territorio"
    emettitore: str = "REGIONE ABRUZZO"
    tipo: str = "LEGGE REGIONALE"
    riferimento: str = ""
    eli_url: str = "https://www.gazzettaufficiale.it/eli/id/2024/09/21/24R00001/s3"


def detail(text, estremi="LEGGE REGIONALE 20 dicembre 2023, n. 58"):
    return SimpleNamespace(
        estremi=estremi, tipo="",
        title="Nuova legge urbanistica sul governo del territorio",
        emettitore="", text=text,
        eli_url="https://www.gazzettaufficiale.it/eli/id/2024/09/21/24R00001/s3",
    )


ORIGINAL = (
    "Pubblicata nel Bollettino Ufficiale della Regione Abruzzo\n"
    "Art. 1.\nFinalita'\n1. Governo del territorio\n"
    "Art. 2.\nNorme di attuazione\n2. Territorio\n"
)


def test_federated_parser_filters_unrelated_regions_and_unsafe_links():
    html = """
    <a href="http://www2.consiglio.regione.abruzzo.it/leggi_tv/testi_vigenti/insieme.asp?numero=58">
       ABRUZZO - LEGGE REGIONALE n. 58 del 20 dicembre 2023 - TESTO VIGENTE
    </a>
    <a href="http://other.example/laws">ABRUZZO - LEGGE REGIONALE n. 1 del 2023</a>
    <a href="http://www2.consiglio.regione.abruzzo.it/leggi_tv/other">
       MARCHE - LEGGE REGIONALE n. 3 del 2023
    </a>
    """
    result = gazzetta._parse_abruzzo_federated(html)
    assert len(result) == 1
    assert result[0]["numero"] == "58"
    assert result[0]["anno"] == "2023"
    assert "VIGENTE" in result[0]["stato"]


@pytest.mark.asyncio
async def test_search_uses_federated_law_metadata(monkeypatch):
    seen = []

    async def fake_search(parole, numero, anno):
        seen.append((parole, numero, anno))
        return [{
            "numero": "58", "anno": "2023",
            "titolo": "Nuova legge urbanistica sul governo del territorio",
            "descrizione": "ABRUZZO - LEGGE REGIONALE n. 58",
            "stato": "VIGENTE secondo indice Normattiva Regioni",
            "url": "http://www2.consiglio.regione.abruzzo.it/leggi_tv/testi_vigenti/insieme.asp?numero=58",
        }]

    monkeypatch.setattr(gazzetta, "_query_abruzzo_federated", fake_search)
    result = await gazzetta._cerca_leggi_regione_abruzzo_impl(
        parole="urbanistica", numero="58", anno_da="2023", anno_a="2023"
    )
    assert result.success
    assert "58/2023" in result.results_text
    assert "Normattiva" in result.results_text
    assert seen == [("urbanistica", "58", "2023")]


@pytest.mark.asyncio
async def test_search_empty_does_not_claim_absence(monkeypatch):
    async def fake_search(*args):
        return []

    monkeypatch.setattr(gazzetta, "_query_abruzzo_federated", fake_search)
    result = await gazzetta._cerca_leggi_regione_abruzzo_impl(numero="58")
    assert not result.success
    assert "NON prova" in result.results_text


@pytest.mark.asyncio
async def test_search_invalid_inputs_do_not_network(monkeypatch):
    async def fail(*args):
        raise AssertionError("Must not perform a network request")

    monkeypatch.setattr(gazzetta, "_query_abruzzo_federated", fail)
    for opts in ({}, {"numero": "abc"}, {"anno_da": "20242025"}, {"anno_da": "2023", "anno_a": "2024"}):
        result = await gazzetta._cerca_leggi_regione_abruzzo_impl(**opts)
        assert not result.success


@pytest.mark.asyncio
async def test_read_single_article_and_vigenza_warning(monkeypatch):
    async def fake_fetch(*args, **kwargs):
        return detail(ORIGINAL)

    monkeypatch.setattr(gazzetta, "fetch_atto", fake_fetch)
    res = await gazzetta._leggi_legge_regione_abruzzo_impl(
        "24R00001", "2024-09-21", articolo="1"
    )
    assert res.success
    assert "Governo del territorio" in res.results_text
    assert "Norme di attuazione" not in res.results_text
    assert "Vigenza NON verificata" in res.results_text
    assert "bura.regione.abruzzo.it" in res.results_text


@pytest.mark.asyncio
async def test_read_refuses_other_region(monkeypatch):
    async def fake_fetch(*args, **kwargs):
        return detail("Bollettino Ufficiale della Regione Marche\nArt. 1.\nAltro")

    monkeypatch.setattr(gazzetta, "fetch_atto", fake_fetch)
    res = await gazzetta._leggi_legge_regione_abruzzo_impl("24R00001", "2024-09-21")
    assert not res.success
    assert "Non restituisco testi di altre regioni" in res.results_text


@pytest.mark.asyncio
async def test_article_not_found_is_not_false_legal_conclusion(monkeypatch):
    async def fake_fetch(*args, **kwargs):
        return detail(ORIGINAL)

    monkeypatch.setattr(gazzetta, "fetch_atto", fake_fetch)
    res = await gazzetta._leggi_legge_regione_abruzzo_impl("24R00001", "2024-09-21", articolo="99")
    assert not res.success
    assert "non individuato" in res.results_text


@pytest.mark.asyncio
async def test_read_pagination_and_validation(monkeypatch):
    async def fake_fetch(*args, **kwargs):
        return detail(ORIGINAL + "X" * 26000)

    monkeypatch.setattr(gazzetta, "fetch_atto", fake_fetch)
    res = await gazzetta._leggi_legge_regione_abruzzo_impl("24R00001", "2024-09-21")
    assert res.success
    assert "da_carattere=25001" in res.results_text
    for bad in ("code", "99R", "24R0000"):
        out = await gazzetta._leggi_legge_regione_abruzzo_impl(bad, "2024-09-21")
        assert not out.success
