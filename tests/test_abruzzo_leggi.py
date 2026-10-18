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


@pytest.mark.asyncio
async def test_search_abruzzo_filters_other_regions(monkeypatch):
    calls = []

    async def fake_search(serie, **kwargs):
        calls.append((serie, kwargs))
        return 2, [
            FakeResult(),
            FakeResult(codice_redazionale="24R99999", emettitore="REGIONE MARCHE"),
        ]

    monkeypatch.setattr(gazzetta, "search_atti", fake_search)
    result = await gazzetta._cerca_leggi_regione_abruzzo_impl(
        parole="urbanistica", anno_da="2024", max_risultati=20,
    )
    assert result.success
    assert result.num_found == 1
    assert calls[0][0] == "regioni"
    assert calls[0][1]["descrizione_emettitore"] == "REGIONE ABRUZZO"
    assert "24R00001" in result.results_text
    assert "24R99999" not in result.results_text
    assert "non testo coordinato vigente" in result.results_text


@pytest.mark.asyncio
async def test_search_empty_is_not_claim_of_absence(monkeypatch):
    async def fake_search(*args, **kwargs):
        return 0, []

    monkeypatch.setattr(gazzetta, "search_atti", fake_search)
    res = await gazzetta._cerca_leggi_regione_abruzzo_impl(numero="58")
    assert not res.success
    assert "NON significa" in res.results_text


@pytest.mark.asyncio
async def test_search_invalid_inputs_do_not_network(monkeypatch):
    async def fail(*args, **kwargs):
        raise AssertionError("Must not perform a network request")

    monkeypatch.setattr(gazzetta, "search_atti", fail)
    for opts in ({}, {"numero": "abc"}, {"anno_da": "20242025"}):
        res = await gazzetta._cerca_leggi_regione_abruzzo_impl(**opts)
        assert not res.success


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
