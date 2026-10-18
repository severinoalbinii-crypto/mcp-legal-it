"""Unit test (mocked) per il nuovo client BURAT, senza accesso alla rete."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.tools.abruzzo import (
    _bulletin_links, _law_entries, _match_law, _safe_url, _search_url,
    cerca_leggi_regione_abruzzo, leggi_legge_regione_abruzzo,
    verifica_modifiche_legge_abruzzo,
)

SEARCH = """
<html><body>
<a href="/bollettini/ordinario-50-2023-12-20">Ordinario n. 50/2023</a>
<a href="https://evil.example/bollettini/inventato">Non ufficiale</a>
<a href="/bollettini/ordinario-50-2023-12-20">Duplicato</a>
</body></html>
"""

DETAIL = """
<html><body>
<h3>Leggi regionali</h3>
<h4>LEGGE REGIONALE 20 dicembre 2023, n. 58</h4>
<p>Nuova legge urbanistica sul governo del territorio</p>
<a href="/sites/bura.regione.abruzzo.it/files/bollettini/2023-12-20/lr58.pdf">Scarica il documento</a>
<h4>DETERMINAZIONE DPC 88/2023</h4>
<a href="/sites/bura.regione.abruzzo.it/files/bollettini/2023-12-20/altro.pdf">Altro</a>
</body></html>
"""

ACT = {
    "titolo": "LEGGE REGIONALE 20 dicembre 2023, n. 58",
    "descrizione": "Nuova legge urbanistica sul governo del territorio",
    "url_bollettino": "https://bura.regione.abruzzo.it/bollettini/ordinario-50-2023-12-20",
    "url_documento": "https://bura.regione.abruzzo.it/sites/bura.regione.abruzzo.it/files/bollettini/2023-12-20/lr58.pdf",
}


def _fn(tool):
    return getattr(tool, "fn", tool)


def test_search_url_query_is_encoded():
    assert "cerca_testo=zona+agricola" in _search_url("zona agricola")


def test_allowed_hosts_and_paths():
    assert _safe_url("/bollettini/ordinario-50-2023-12-20")
    assert _safe_url("https://evil.example/documento.pdf") is None
    assert _safe_url("http://bura.regione.abruzzo.it/bollettini/a") is None
    assert _safe_url("https://bura.regione.abruzzo.it/admin") is None
    assert _safe_url("//evil.example/bollettini/a") is None


def test_search_links_deduplicate_and_deny_other_hosts():
    links = _bulletin_links(SEARCH)
    assert len(links) == 1
    assert links[0]["titolo"] == "Ordinario n. 50/2023"


def test_exact_law_entries_and_pdf():
    entries = _law_entries(DETAIL, ACT["url_bollettino"])
    assert len(entries) == 1
    assert entries[0]["titolo"] == ACT["titolo"]
    assert entries[0]["url_documento"] == ACT["url_documento"]
    assert _match_law(entries[0]["titolo"], 58, 2023)
    assert not _match_law(entries[0]["titolo"], 5, 2023)
    assert not _match_law(entries[0]["titolo"], 58, 2024)


@pytest.mark.asyncio
async def test_search_returns_identified_laws_only():
    with patch("src.tools.abruzzo._lookup", new=AsyncMock(return_value={
        "leggi": [ACT], "bollettini": [{"titolo": "BURAT", "url": ACT["url_bollettino"]}],
        "errori_dettaglio": [],
    })):
        payload = json.loads(await _fn(cerca_leggi_regione_abruzzo)("urbanistica", anno=2023, numero=58))
    assert payload["esito"] == "risultati"
    assert len(payload["leggi"]) == 1


@pytest.mark.asyncio
async def test_pdf_reader_and_uncoordinated_warning():
    with patch("src.tools.abruzzo._pdf_text", new=AsyncMock(return_value=("Art. 60 - territorio rurale", False))):
        payload = json.loads(await _fn(leggi_legge_regione_abruzzo)(
            numero=58, anno=2023, url_documento=ACT["url_documento"],
        ))
    assert payload["esito"] == "testo_estratto"
    assert "territorio rurale" in payload["testo"]
    assert "Non è il testo coordinato vigente" in payload["avvertenza"]


@pytest.mark.asyncio
async def test_reader_rejects_external_document():
    payload = json.loads(await _fn(leggi_legge_regione_abruzzo)(
        numero=58, anno=2023, url_documento="https://bad.example/doc.pdf",
    ))
    assert payload["esito"] == "input_non_valido"


@pytest.mark.asyncio
async def test_amendments_never_claim_vigency():
    with patch("src.tools.abruzzo._lookup", new=AsyncMock(return_value={
        "leggi": [], "bollettini": [], "errori_dettaglio": [],
    })):
        payload = json.loads(await _fn(verifica_modifiche_legge_abruzzo)(58, 2023))
    assert payload["esito"] == "ricerca_indicativa"
    assert "NON" in payload["avvertenza"]


@pytest.mark.asyncio
async def test_search_source_failure_not_reported_as_zero():
    import httpx
    with patch("src.tools.abruzzo._lookup", new=AsyncMock(side_effect=httpx.ConnectError("timeout"))):
        payload = json.loads(await _fn(cerca_leggi_regione_abruzzo)("urbanistica"))
    assert payload["esito"] == "fonte_non_disponibile"
