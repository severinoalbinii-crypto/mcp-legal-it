"""Consultazione verificabile delle leggi regionali abruzzesi sul BURAT.

Il BURAT è la fonte di pubblicazione ufficiale; la ricerca nel suo indice non
garantisce esaustività né produce automaticamente un testo coordinato vigente.
Le funzioni NON devono essere usate per attestare l'assenza di modifiche.
"""

from __future__ import annotations

from io import BytesIO
import json
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from src.lib._http import retry_request
from src.server import mcp

BASE = "https://bura.regione.abruzzo.it"
SEARCH_PATH = "/cerca"
MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_PAGES = 150
MAX_TEXT_CHUNK = 18000
MAX_BULLETINS = 10
LAW_HEAD = re.compile(r"\blegge\s+regionale\b", re.I)
LAW_NUMBER = re.compile(r"\bn\s*[.°]?\s*(\d+)\b", re.I)


def _safe_url(href: str, *, allow_search: bool = False) -> str | None:
    """Accept only known BURAT HTTPS resources, never arbitrary remote URLs."""
    url = urljoin(BASE, href)
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "bura.regione.abruzzo.it":
        return None
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        return None
    paths = ("/bollettini/", "/sites/bura.regione.abruzzo.it/")
    if allow_search:
        paths += ("/cerca", "/en/cerca")
    if not any(parsed.path.startswith(path) for path in paths):
        return None
    return url


def _search_url(query: str) -> str:
    from urllib.parse import urlencode
    return BASE + SEARCH_PATH + "?" + urlencode({"cerca_testo": query})


def _bulletin_links(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    found = []
    seen = set()
    for a in soup.select("a[href]"):
        url = _safe_url(a.get("href", ""))
        if not url or "/bollettini/" not in url:
            continue
        # Avoid PDF file links here: those are not bulletin detail pages.
        if urlparse(url).path.lower().endswith((".pdf", ".html", ".htm")):
            continue
        if url in seen:
            continue
        seen.add(url)
        found.append({"titolo": a.get_text(" ", strip=True) or "Bollettino BURAT", "url": url})
    return found


def _law_entries(html: str, bulletin_url: str) -> list[dict[str, str]]:
    """Extract only acts actually identified as regional laws in a bulletin."""
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for heading in soup.find_all(["h3", "h4", "h5", "h6"]):
        title = heading.get_text(" ", strip=True)
        if not LAW_HEAD.search(title):
            continue
        text = []
        pdf_url = ""
        for sibling in heading.next_elements:
            if getattr(sibling, "name", None) in ("h3", "h4", "h5", "h6"):
                break
            if getattr(sibling, "name", None) in ("p", "div"):
                snippet = sibling.get_text(" ", strip=True)
                if snippet and len(snippet) < 1800:
                    text.append(snippet)
            if getattr(sibling, "name", None) == "a":
                candidate = _safe_url(sibling.get("href", ""))
                if candidate and urlparse(candidate).path.lower().endswith(".pdf"):
                    pdf_url = candidate
                    break
        found.append({
            "titolo": title,
            "descrizione": " ".join(dict.fromkeys(text))[:1200],
            "url_bollettino": bulletin_url,
            "url_documento": pdf_url,
        })
    return found


def _match_law(title: str, numero: int, anno: int) -> bool:
    if not LAW_HEAD.search(title) or str(anno) not in title:
        return False
    match = LAW_NUMBER.search(title)
    return bool(match and int(match.group(1)) == numero)


async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    if _safe_url(url, allow_search=True) is None:
        raise ValueError("URL non autorizzato")
    response = await retry_request(
        client, "GET", url, dataset="bura_abruzzo", max_retries=1
    )
    if response.is_redirect:
        raise ValueError("Il BURAT ha risposto con un reindirizzamento non verificato")
    return response


async def _lookup(query: str, *, max_bulletins: int = MAX_BULLETINS) -> dict:
    async with httpx.AsyncClient(timeout=22, follow_redirects=False, headers={
        "User-Agent": "mcp-legal-it/2.16 (consultazione BURAT)",
        "Accept-Language": "it-IT,it;q=0.9",
    }) as client:
        page = await _get(client, _search_url(query))
        if "html" not in page.headers.get("content-type", "").lower():
            raise ValueError("Risposta non HTML dalla ricerca BURAT")
        links = _bulletin_links(page.text)[:max_bulletins]
        acts = []
        errors = []
        for link in links:
            try:
                detail = await _get(client, link["url"])
                if "html" not in detail.headers.get("content-type", "").lower():
                    raise ValueError("Dettaglio bollettino non HTML")
                acts.extend(_law_entries(detail.text, link["url"]))
            except (httpx.HTTPError, ValueError) as exc:
                errors.append(f'{link["url"]}: {type(exc).__name__}')
    return {"bollettini": links, "leggi": acts, "errori_dettaglio": errors}


def _output(**data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool(tags={"normativa"})
async def cerca_leggi_regione_abruzzo(
    query: str,
    anno: int = 0,
    numero: int = 0,
    max_risultati: int = 10,
) -> str:
    """Cerca leggi e bollettini nel BURAT ufficiale per parole chiave ed estremi.

    Non certifica che la ricerca sia esaustiva e non calcola la vigenza.
    Le leggi elencate sono identificate dall'intestazione pubblicata nel bollettino.
    Se il BURAT è irraggiungibile, restituisce un errore, MAI zero risultati.
    """
    query = query.strip()
    if not query and not (anno and numero):
        return _output(esito="input_non_valido", errore="Indicare argomento o numero e anno")
    if anno and not 1970 <= anno <= 2100 or numero < 0:
        return _output(esito="input_non_valido", errore="Anno/numero non validi")
    if len(query) > 180:
        return _output(esito="input_non_valido", errore="Ricerca troppo lunga")
    terms = query or f"legge regionale {numero} {anno}"
    try:
        hits = await _lookup(terms, max_bulletins=min(max(max_risultati, 1), MAX_BULLETINS))
    except (httpx.HTTPError, ValueError) as exc:
        return _output(esito="fonte_non_disponibile", fonte=BASE, errore=str(exc))
    acts = hits["leggi"]
    if numero:
        acts = [act for act in acts if _match_law(act["titolo"], numero, anno)]
    elif anno:
        acts = [act for act in acts if str(anno) in act["titolo"]]
    return _output(
        esito="risultati" if acts else "nessuna_legge_identificata_nel_campione",
        fonte_ufficiale=BASE,
        ricerca=_search_url(terms),
        leggi=acts[:max(1, min(max_risultati, 10))],
        bollettini_da_verificare=hits["bollettini"][:max(1, min(max_risultati, 10))],
        errori_dettaglio=hits["errori_dettaglio"],
        avvertenza="L'indice BURAT e il campione di bollettini non garantiscono esaustività o testo vigente; verificare tutte le modifiche pubblicate.",
    )


async def _pdf_text(url: str) -> tuple[str, bool]:
    async with httpx.AsyncClient(timeout=35, follow_redirects=False) as client:
        response = await _get(client, url)
    content = response.content
    if len(content) > MAX_PDF_BYTES:
        raise ValueError("PDF oltre il limite di 15 MB")
    if not content.startswith(b"%PDF-"):
        raise ValueError("Il documento restituito non è un PDF valido")
    reader = PdfReader(BytesIO(content))
    parts = [(page.extract_text() or "") for page in reader.pages[:MAX_PAGES]]
    return "\n\n".join(parts).strip(), len(reader.pages) > MAX_PAGES


@mcp.tool(tags={"normativa"})
async def leggi_legge_regione_abruzzo(
    numero: int,
    anno: int,
    url_documento: str = "",
    da_carattere: int = 1,
) -> str:
    """Legge il testo PDF di una legge abruzzese dal BURAT (o cerca per estremi).

    Un URL esplicito deve appartenere al BURAT e puntare a PDF.
    Il PDF potrebbe contenere un bollettino con PIÙ atti: il testo restituito
    NON viene automaticamente isolato né presentato come testo coordinato vigente.
    Scansioni prive di testo estraibile sono segnalate, non inventate.
    """
    if not (1970 <= anno <= 2100 and numero > 0 and da_carattere > 0):
        return _output(esito="input_non_valido", errore="Estremi o pagina non validi")
    if url_documento:
        url = _safe_url(url_documento)
        if not url or not urlparse(url).path.lower().endswith(".pdf"):
            return _output(esito="input_non_valido", errore="È ammesso solo un PDF ufficiale BURAT")
    else:
        try:
            hits = await _lookup(f"legge regionale {numero} {anno}")
        except (httpx.HTTPError, ValueError) as exc:
            return _output(esito="fonte_non_disponibile", errore=str(exc))
        candidates = [act for act in hits["leggi"] if _match_law(act["titolo"], numero, anno)]
        if not candidates or not candidates[0]["url_documento"]:
            return _output(
                esito="documento_non_individuato",
                riferimento=f"L.R. Abruzzo {numero}/{anno}",
                ricerca=_search_url(f"legge regionale {numero} {anno}"),
                candidati=candidates,
                avvertenza="Il mancato reperimento non dimostra l'inesistenza della norma.",
            )
        url = candidates[0]["url_documento"]
    try:
        text, pages_truncated = await _pdf_text(url)
    except Exception as exc:
        return _output(esito="lettura_non_riuscita", url=url, errore=f"{type(exc).__name__}: {exc}")
    if not text:
        return _output(esito="pdf_senza_testo", url=url, avvertenza="Probabile scansione: estrazione testuale non possibile.")
    start = da_carattere - 1
    chunk = text[start:start + MAX_TEXT_CHUNK]
    return _output(
        esito="testo_estratto" if chunk else "fine_testo",
        riferimento_richiesto=f"L.R. Abruzzo {numero}/{anno}",
        url_documento=url,
        testo=chunk,
        da_carattere=da_carattere,
        prossimo_da_carattere=start + len(chunk) + 1 if start + len(chunk) < len(text) else None,
        pagine_troncate=pages_truncated,
        avvertenza="Testo estratto dal PDF (potrebbe includere altri atti). Non è il testo coordinato vigente; verificare articolo e successive modifiche.",
    )


@mcp.tool(tags={"normativa"})
async def verifica_modifiche_legge_abruzzo(numero: int, anno: int) -> str:
    """Cerca menzioni/modifiche di una L.R. Abruzzo nei bollettini BURAT.

    Ricerca indicativa: un esito vuoto NON significa assenza di modifiche,
    abrogazioni o sentenze costituzionali. Richiede verifica normativa ulteriore.
    """
    if not (numero > 0 and 1970 <= anno <= 2100):
        return _output(esito="input_non_valido", errore="Estremi non validi")
    query = f"modifiche alla legge regionale {numero}/{anno}"
    try:
        hits = await _lookup(query)
    except (httpx.HTTPError, ValueError) as exc:
        return _output(esito="fonte_non_disponibile", errore=str(exc))
    return _output(
        esito="ricerca_indicativa",
        riferimento=f"L.R. Abruzzo {numero}/{anno}",
        ricerca=_search_url(query),
        bollettini_da_esaminare=hits["bollettini"],
        leggi_identificate=hits["leggi"],
        errori_dettaglio=hits["errori_dettaglio"],
        avvertenza="NON è una verifica esaustiva della vigenza. Confrontare testi pubblicati sul BURAT e banca dati dei testi vigenti del Consiglio regionale.",
    )
