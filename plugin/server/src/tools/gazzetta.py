"""MCP tools for the Gazzetta Ufficiale della Repubblica Italiana.

TRIGGER: usare quando l'utente chiede di atti pubblicati in Gazzetta Ufficiale,
decreti, leggi, ordinanze ministeriali, comunicati, novita normative italiane,
testo di un atto pubblicato in GU, sommario di una gazzetta o il PDF ufficiale.

Workflow tipico:
- ultime_gazzette() per le novita normative (via RSS).
- cerca_gazzetta_ufficiale() per ricerca parametrica/full-text.
- leggi_atto_gazzetta(codice, data) per il testo completo di un atto.
- sommario_gazzetta(numero, data) per l'indice di un fascicolo.
- scarica_pdf_gazzetta(numero, data) per il PDF ufficiale (restituisce l'URL).
"""

from src.lib._paging import invalid_start
from src.lib._result import SearchResult
from src.lib._sources import note
from src.server import mcp
from src.lib.gazzetta.client import (
    RSS_CODE,
    SERIE,
    fetch_atto,
    fetch_latest,
    fetch_sommario,
    format_detail,
    format_result,
    format_sommario,
    pdf_url,
    search_atti,
)

_SOURCE = "gazzetta_ufficiale"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_serie_path(serie: str) -> str:
    """Map a human-friendly serie key to its URL path segment.

    Unknown keys default to serie_generale (the most common case).
    """
    return SERIE.get(serie.lower().strip().replace(" ", "_"), "serie_generale")


def _resolve_rss_code(serie: str) -> str:
    return RSS_CODE.get(serie.lower().strip().replace(" ", "_"), "SG")


# ---------------------------------------------------------------------------
# Impl functions (testable without MCP context) -> SearchResult
# ---------------------------------------------------------------------------

async def _cerca_gazzetta_ufficiale_impl(
    query: str = "",
    titolo: str = "",
    testo: str = "",
    tipo_provvedimento: str = "",
    emettitore: str = "",
    materia: str = "",
    serie: str = "serie_generale",
    anno_da: str = "",
    anno_a: str = "",
    max_risultati: int = 20,
) -> SearchResult:
    max_risultati = max(1, min(max_risultati, 100))
    serie_path = _resolve_serie_path(serie)

    # `query` is a convenience alias: search it in the title unless `titolo`/`testo`
    # are explicitly provided.
    titolo_q = titolo or query
    testo_q = testo

    try:
        total, docs = await search_atti(
            serie_path,
            titolo=titolo_q,
            testo=testo_q,
            descrizione_tipo_provvedimento=tipo_provvedimento,
            descrizione_emettitore=emettitore,
            descrizione_materia=materia,
            anno_da=anno_da,
            anno_a=anno_a,
            rows=max_risultati,
        )
    except Exception as exc:
        return SearchResult(
            success=False, source=_SOURCE, error_type="source_down",
            error_message=str(exc),
        )

    if not docs:
        q_desc = titolo_q or testo_q or query or "ricerca"
        return SearchResult(
            success=False, source=_SOURCE, error_type="no_results",
            results_text=f"Nessun atto trovato in Gazzetta Ufficiale per: _{q_desc}_",
        )

    head = f"**Trovati {total} atti in Gazzetta Ufficiale**"
    if total > len(docs):
        head += f" (mostrati i primi {len(docs)})"
    lines = [head + "\n"]
    for doc in docs:
        lines.append(format_result(doc))
        lines.append("")
    return SearchResult(
        success=True, source=_SOURCE, num_found=total, results_text="\n".join(lines),
    )


async def _leggi_atto_gazzetta_impl(
    codice_redazionale: str,
    data_pubblicazione: str,
    serie: str = "serie_generale",
    solo_metadati: bool = False,
    da_carattere: int = 1,
) -> SearchResult:
    if (error := invalid_start(da_carattere)) is not None:
        return SearchResult(
            success=False, source=_SOURCE, error_type="bad_input",
            error_message=error, results_text=f"**Errore**: {error}",
        )
    serie_path = _resolve_serie_path(serie)
    if serie_path == "unione_europea":
        # The 2a Serie speciale has no atto pages (the ELI permalink answers HTTP 500):
        # its items exist only as pages of the fascicolo PDF.
        return SearchResult(
            success=False, source=_SOURCE, error_type="no_results",
            results_text=(
                "Gli atti della 2a Serie speciale (Unione europea) non hanno una pagina "
                "propria in Gazzetta Ufficiale: usare scarica_pdf_gazzetta(numero, data, "
                "serie=\"unione_europea\") per il fascicolo o cite_law() per l'atto UE."
            ),
        )
    try:
        detail = await fetch_atto(
            serie_path, data_pubblicazione, codice_redazionale,
            metadata_only=solo_metadati,
        )
    except ValueError as exc:
        return SearchResult(
            success=False, source=_SOURCE, error_type="bad_input",
            error_message=f"Data non valida: {exc}",
            results_text=f"**Errore**: data non valida. {exc}",
        )
    except Exception as exc:
        return SearchResult(
            success=False, source=_SOURCE, error_type="source_down",
            error_message=str(exc),
        )

    if not solo_metadati and not detail.text:
        return SearchResult(
            success=False, source=_SOURCE, error_type="no_results",
            results_text=(
                f"Testo non disponibile per l'atto {codice_redazionale} "
                f"({data_pubblicazione}). Metadati:\n\n{format_detail(detail)}"
            ),
        )

    return SearchResult(
        success=True, source=_SOURCE, num_found=1,
        results_text=format_detail(detail, da_carattere),
    )


async def _sommario_gazzetta_impl(
    numero_gazzetta: str,
    data_pubblicazione: str,
    serie: str = "serie_generale",
) -> SearchResult:
    serie_path = _resolve_serie_path(serie)
    try:
        heading, atti = await fetch_sommario(data_pubblicazione, numero_gazzetta, serie_path)
    except ValueError as exc:
        return SearchResult(
            success=False, source=_SOURCE, error_type="bad_input",
            error_message=f"Data non valida: {exc}",
            results_text=f"**Errore**: data non valida. {exc}",
        )
    except Exception as exc:
        return SearchResult(
            success=False, source=_SOURCE, error_type="source_down",
            error_message=str(exc),
        )

    if not atti:
        return SearchResult(
            success=False, source=_SOURCE, error_type="no_results",
            results_text=(
                f"Nessun atto trovato nel sommario della Gazzetta n. {numero_gazzetta} "
                f"del {data_pubblicazione}."
            ),
        )

    return SearchResult(
        success=True, source=_SOURCE, num_found=len(atti),
        results_text=format_sommario(heading, atti),
    )


async def _ultime_gazzette_impl(
    serie: str = "serie_generale",
    max_risultati: int = 10,
) -> SearchResult:
    max_risultati = max(1, min(max_risultati, 100))
    rss_code = _resolve_rss_code(serie)
    try:
        docs = await fetch_latest(rss_code, rows=max_risultati)
    except Exception as exc:
        return SearchResult(
            success=False, source=_SOURCE, error_type="source_down",
            error_message=str(exc),
        )

    if not docs:
        return SearchResult(
            success=False, source=_SOURCE, error_type="no_results",
            results_text="Nessun atto recente trovato nella Gazzetta Ufficiale.",
        )

    lines = ["**Ultimi atti pubblicati in Gazzetta Ufficiale**\n"]
    for doc in docs:
        lines.append(format_result(doc))
        lines.append("")
    return SearchResult(
        success=True, source=_SOURCE, num_found=len(docs), results_text="\n".join(lines),
    )


async def _scarica_pdf_gazzetta_impl(
    numero_gazzetta: str,
    data_pubblicazione: str,
    serie: str = "serie_generale",
) -> SearchResult:
    serie_path = _resolve_serie_path(serie)
    try:
        url = pdf_url(data_pubblicazione, numero_gazzetta, serie_path)
    except ValueError as exc:
        # A malformed date is the caller's mistake, not a source outage.
        return SearchResult(
            success=False, source=_SOURCE, error_type="bad_input",
            error_message=f"Data non valida: {exc}",
            results_text=f"**Errore**: data non valida. {exc}",
        )
    text = (
        f"**PDF ufficiale Gazzetta Ufficiale n. {numero_gazzetta} "
        f"del {data_pubblicazione}**\n\n[Scarica il PDF]({url})\n\n{url}"
    )
    #: The answer names a Gazzetta URL for the caller to download: that link is
    #: the consult, even though nothing is fetched server-side.
    note("gazzetta", url)
    return SearchResult(success=True, source=_SOURCE, num_found=1, results_text=text)


# ---------------------------------------------------------------------------
# MCP tool wrappers
# ---------------------------------------------------------------------------

@mcp.tool(tags={"normativa"})
async def cerca_gazzetta_ufficiale(
    query: str = "",
    titolo: str = "",
    testo: str = "",
    tipo_provvedimento: str = "",
    emettitore: str = "",
    materia: str = "",
    serie: str = "serie_generale",
    anno_da: str = "",
    anno_a: str = "",
    max_risultati: int = 20,
) -> str:
    """Cerca atti pubblicati nella Gazzetta Ufficiale (ricerca parametrica/full-text).

    USARE quando si cerca: decreti, leggi, ordinanze, comunicati o altri atti
    pubblicati in GU per titolo, testo, tipo provvedimento, emettitore o periodo.
    Dopo aver trovato un atto, usare leggi_atto_gazzetta(codice, data) per il testo.
    Restituisce: lista atti con emettitore, tipo, oggetto, codice redazionale e link.

    Args:
        query: Parole da cercare nel titolo (alias rapido di `titolo`)
        titolo: Parole da cercare nel titolo dell'atto
        testo: Parole da cercare nel testo integrale dell'atto
        tipo_provvedimento: Descrizione tipo (es. "DECRETO", "LEGGE", "ORDINANZA")
        emettitore: Descrizione emettitore (es. "MINISTERO DELLA SALUTE")
        materia: Descrizione materia
        serie: Serie (serie_generale, unione_europea, regioni, corte_costituzionale,
            parte_seconda, contratti, concorsi)
        anno_da: Anno di pubblicazione iniziale (es. "2024")
        anno_a: Anno di pubblicazione finale (es. "2026")
        max_risultati: Numero massimo di risultati (default 20, max 100)
    """
    result = await _cerca_gazzetta_ufficiale_impl(
        query=query, titolo=titolo, testo=testo,
        tipo_provvedimento=tipo_provvedimento, emettitore=emettitore,
        materia=materia, serie=serie, anno_da=anno_da, anno_a=anno_a,
        max_risultati=max_risultati,
    )
    return result.to_str()


@mcp.tool(tags={"normativa"})
async def leggi_atto_gazzetta(
    codice_redazionale: str,
    data_pubblicazione: str,
    serie: str = "serie_generale",
    solo_metadati: bool = False,
    da_carattere: int = 1,
) -> str:
    """Legge il testo completo di un atto pubblicato in Gazzetta Ufficiale.

    Usare dopo cerca_gazzetta_ufficiale(), ultime_gazzette() o sommario_gazzetta()
    indicando il codice redazionale e la data di pubblicazione del risultato.
    Restituisce: estremi (es. "DECRETO LEGISLATIVO 10 ottobre 2022, n. 149"), oggetto,
    riferimento alla GU, metadati ELI (tipo, date) + testo integrale assemblato.
    Per un atto delle serie speciali (corte_costituzionale, regioni, concorsi, contratti,
    parte_seconda) indicare la serie: e' quella che determina la pagina dell'atto. Gli
    atti della 2a Serie speciale (unione_europea) non hanno una pagina propria.
    Il testo e' limitato a 25000 caratteri per chiamata: la parte omessa si legge
    ripetendo la chiamata con il da_carattere indicato nella nota. Le posizioni
    contano il testo integrale assemblato dell'atto (non i metadati in testa).
    Con da_carattere > 1 restituisce i 25000 caratteri che partono da quella posizione.

    Args:
        codice_redazionale: Codice dell'atto (es. "26A02808")
        data_pubblicazione: Data pubblicazione in formato YYYY-MM-DD (es. "2026-06-13")
        serie: Serie dell'atto (serie_generale, corte_costituzionale, regioni,
            concorsi, contratti, parte_seconda; default serie_generale)
        solo_metadati: Se True, restituisce solo i metadati senza scaricare il testo
        da_carattere: Carattere da cui leggere (1 = inizio, default). Se il testo supera il limite,
            la nota finale indica il valore con cui ripetere la chiamata per leggere il seguito
    """
    result = await _leggi_atto_gazzetta_impl(
        codice_redazionale=codice_redazionale,
        data_pubblicazione=data_pubblicazione,
        serie=serie, solo_metadati=solo_metadati,
        da_carattere=da_carattere,
    )
    return result.to_str()


@mcp.tool(tags={"normativa"})
async def sommario_gazzetta(
    numero_gazzetta: str,
    data_pubblicazione: str,
    serie: str = "serie_generale",
) -> str:
    """Restituisce il sommario (indice degli atti) di un fascicolo di Gazzetta Ufficiale.

    Usare per vedere tutti gli atti pubblicati in una specifica gazzetta.
    Da ogni atto del sommario si puo poi usare leggi_atto_gazzetta() per il testo.
    Restituisce: intestazione del fascicolo (serie, numero, data) e per ogni atto
    codice redazionale, estremi, emettitore e oggetto.

    Args:
        numero_gazzetta: Numero del fascicolo nella sua serie (es. "135")
        data_pubblicazione: Data pubblicazione in formato YYYY-MM-DD (es. "2026-06-13")
        serie: Serie della gazzetta (serie_generale, corte_costituzionale,
            unione_europea, regioni, concorsi, contratti, parte_seconda;
            default serie_generale). Il numero e' quello della serie indicata.
    """
    result = await _sommario_gazzetta_impl(
        numero_gazzetta=numero_gazzetta,
        data_pubblicazione=data_pubblicazione, serie=serie,
    )
    return result.to_str()


@mcp.tool(tags={"normativa"})
async def ultime_gazzette(
    serie: str = "serie_generale",
    max_risultati: int = 10,
) -> str:
    """Ultimi atti pubblicati nella Gazzetta Ufficiale (novita normative, via RSS).

    USARE per le novita normative italiane piu recenti. Percorso stabile (RSS).
    Da ogni risultato usare leggi_atto_gazzetta(codice, data) per il testo completo.
    Restituisce: lista cronologica degli ultimi atti con emettitore, tipo, oggetto e link.
    Le serie speciali seguono la numerazione ufficiale (1a Corte costituzionale, 2a Unione
    europea, 3a Regioni, 4a Concorsi ed esami, 5a Contratti pubblici).

    Args:
        serie: Serie (serie_generale, unione_europea, regioni, corte_costituzionale,
            parte_seconda, contratti, concorsi)
        max_risultati: Numero massimo di risultati (default 10, max 100)
    """
    result = await _ultime_gazzette_impl(serie=serie, max_risultati=max_risultati)
    return result.to_str()


@mcp.tool(tags={"normativa"})
async def scarica_pdf_gazzetta(
    numero_gazzetta: str,
    data_pubblicazione: str,
    serie: str = "serie_generale",
) -> str:
    """Restituisce l'URL del PDF ufficiale di un fascicolo di Gazzetta Ufficiale.

    Restituisce il link al PDF ufficiale (non scarica il file inline e non lo verifica:
    per una serie speciale il link e' quello della serie indicata, non della Serie generale).

    Args:
        numero_gazzetta: Numero del fascicolo nella sua serie (es. "135")
        data_pubblicazione: Data pubblicazione in formato YYYY-MM-DD (es. "2026-06-13")
        serie: Serie della gazzetta (serie_generale, corte_costituzionale,
            unione_europea, regioni, concorsi, contratti, parte_seconda;
            default serie_generale)
    """
    result = await _scarica_pdf_gazzetta_impl(
        numero_gazzetta=numero_gazzetta,
        data_pubblicazione=data_pubblicazione, serie=serie,
    )
    return result.to_str()


# MCP ABRUZZO LEGISLATION TOOLS (Gazzetta Ufficiale, Serie Regioni)
# This is a verified publication-text lookup, NOT a consolidated regional law database.
import re as _abruzzo_re

_ABRUZZO_OFFICIAL_SOURCES = (
    "\n**Per modifiche, abrogazioni e vigenza:** consultare la banca dati regionale "
    "accessibile da https://www.regione.abruzzo.it/leggi-atti-bandi/leggi-e-progetti-di-legge "
    "e il Bollettino ufficiale https://bura.regione.abruzzo.it/. "
    "Il testo pubblicato in GU NON e' automaticamente il testo vigente."
)
_ABRUZZO_ART_RX = _abruzzo_re.compile(
    r"(?im)^[ \t]*Art(?:icolo)?\.?[ \t]*(?P<num>\d+[a-z]?(?:[-/]\w+)?)[ \t]*\.?[ \t]*(?=\r?$)"
)


def _abruzzo_is_law(detail) -> bool:
    """Require evidence for BOTH Abruzzo and a regional law, not just user labels."""
    header = (detail.estremi or "") + " " + (detail.tipo or "")
    intro = (detail.text or "")[:4000]
    issuer = (detail.emettitore or "").replace("_", " ")
    return bool(
        _abruzzo_re.search(r"legge[\s_]*regionale", header, _abruzzo_re.I)
        and (
            "regione abruzzo" in issuer.casefold()
            or "regione abruzzo" in intro.casefold()
        )
    )


def _abruzzo_article(text: str, number: str) -> str | None:
    """Return only the requested complete article when headings can be identified."""
    matches = list(_ABRUZZO_ART_RX.finditer(text))
    target = number.lower().strip()
    for pos, match in enumerate(matches):
        if match.group("num").lower() == target:
            end = matches[pos + 1].start() if pos + 1 < len(matches) else len(text)
            return text[match.start():end].strip()
    return None



from urllib.parse import urlsplit as _abruzzo_urlsplit
import httpx as _abruzzo_httpx
from bs4 import BeautifulSoup as _abruzzo_bs4
from src.lib._http import retry_request as _abruzzo_request

_ABRUZZO_MFR = "https://www.normattiva.it/mfr/"
_ABRUZZO_MFR_SEARCH = "https://www.normattiva.it/mfr/ricerca/semplice/1"


def _parse_abruzzo_federated(html: str) -> list[dict[str, str]]:
    """Parse regional law links only on the verified Abruzzo Council domains."""
    soup = _abruzzo_bs4(html, "html.parser")
    matches = []
    seen = set()
    for a in soup.select("a[href]"):
        url = a.get("href", "").strip()
        parts = _abruzzo_urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme not in ("http", "https") or not (
            host.endswith(".consiglio.regione.abruzzo.it")
            or host == "consiglio.regione.abruzzo.it"
            or host == "leggi.regione.abruzzo.it"
        ):
            continue
        label = _abruzzo_re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
        if not (
            _abruzzo_re.search(r"\bABRUZZO\b", label, _abruzzo_re.I)
            and _abruzzo_re.search(r"LEGGE\s+REGIONALE", label, _abruzzo_re.I)
        ):
            continue
        match = _abruzzo_re.search(
            r"LEGGE\s+REGIONALE\s+n\.?\s*(\d+)\s+del\s+"
            r"(?:\d{1,2}\s+[\wàèìòù]+\s+)?(\d{4})",
            label, _abruzzo_re.I
        )
        parent_text = a.parent.get_text(" ", strip=True) if a.parent else label
        context = _abruzzo_re.sub(r"\s+", " ", parent_text).strip()
        extra = context[len(label):].lstrip(" -:") if context.startswith(label) else ""
        if url in seen:
            continue
        seen.add(url)
        matches.append({
            "numero": match.group(1) if match else "",
            "anno": match.group(2) if match else "",
            "descrizione": label[:600],
            "titolo": extra[:350],
            "stato": (
                "VIGENTE secondo indice Normattiva Regioni"
                if "TESTO VIGENTE" in label.upper()
                else "Stato non verificato nell'indice"
            ),
            "url": url,
        })
    return matches


async def _query_abruzzo_federated(parole: str, numero: str, anno: str) -> list[dict[str, str]]:
    """POST to official Normattiva regional index; one request per search."""
    async with _abruzzo_httpx.AsyncClient(
        follow_redirects=True, timeout=_abruzzo_httpx.Timeout(25, connect=10),
        headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "it-IT,it;q=0.9"},
    ) as client:
        landing = await _abruzzo_request(client, "GET", _ABRUZZO_MFR, dataset="normattiva")
        soup = _abruzzo_bs4(landing.text, "html.parser")
        form = soup.find("form", action=lambda a: bool(a and "/ricerca/semplice/" in a))
        region = form.find("input", {"name": "regioneList", "id": "regioneList1"}) if form else None
        types = form.find("input", {"name": "tipoLeggeList"}) if form else None
        if region is None or region.get("value") != "1" or types is None:
            raise RuntimeError("Il filtro Abruzzo nel portale Normattiva e' cambiato")
        payload = {
            "numeroProvvedimento": numero, "giornoProvvedimento": "",
            "meseProvvedimento": "", "annoProvvedimento": anno,
            "tipoLeggeList": types.get("value", ""),
            "containsType": "ALL_WORDS", "ricerca": parole,
            "regioneList": "1", "_regioneList": "on",
        }
        reply = await _abruzzo_request(
            client, "POST", _ABRUZZO_MFR_SEARCH, dataset="normattiva", data=payload
        )
        return _parse_abruzzo_federated(reply.text)


async def _cerca_leggi_regione_abruzzo_impl(
    parole: str = "", numero: str = "", anno_da: str = "", anno_a: str = "",
    max_risultati: int = 20,
) -> SearchResult:
    """Look up Abruzzo legislation in Normattiva's official federated index."""
    source = "normattiva_regioni"
    if not any(x.strip() for x in (parole, numero, anno_da, anno_a)):
        return SearchResult(success=False, source=source, error_type="bad_input",
                            results_text="Specificare parole, numero o anno della legge.")
    if (numero and not numero.isdigit()) or any(
        y and not _abruzzo_re.fullmatch(r"\d{4}", y) for y in (anno_da, anno_a)
    ):
        return SearchResult(success=False, source=source, error_type="bad_input",
                            results_text="Numero numerico e anno nel formato AAAA.")
    if anno_da and anno_a and anno_da != anno_a:
        return SearchResult(success=False, source=source, error_type="bad_input",
                            results_text="La ricerca federata accetta un solo anno alla volta.")
    try:
        matches = await _query_abruzzo_federated(parole.strip(), numero.strip(), anno_da or anno_a)
    except Exception as exc:
        return SearchResult(success=False, source=source, error_type="source_down",
                            error_message=str(exc))
    if not matches:
        return SearchResult(success=False, source=source, error_type="no_results",
                            results_text=(
                                "Nessun risultato verificabile nell'indice: NON prova "
                                "che la legge non esista." + _ABRUZZO_OFFICIAL_SOURCES
                            ))
    limit = max(1, min(max_risultati, 30))
    lines = [
        f"## Regione Abruzzo: {len(matches)} riferimenti identificati nel portale Normattiva Regioni",
        "Fonte ufficiale di indicizzazione: https://www.normattiva.it/mfr/",
        "Anno = anno della legge; gli atti elencati rinviano al Consiglio regionale. "
        "La dicitura vigente riportata dal catalogo NON equivale a verifica "
        "autonoma di ogni modifica o abrogazione.",
    ]
    for result in matches[:limit]:
        lines += [
            "", f"**L.R. Abruzzo {result['numero'] or '?'}"
                f"/{result['anno'] or '?'}** — {result['stato']}",
            result["titolo"] or result["descrizione"],
            f"Testo sul sito regionale: {result['url']}",
        ]
    if len(matches) > limit:
        lines.append(f"Mostrati {limit} riferimenti della prima pagina; affinare la ricerca.")
    lines.append(_ABRUZZO_OFFICIAL_SOURCES)
    return SearchResult(success=True, source=source, num_found=len(matches),
                        results_text="\n".join(lines))


async def _leggi_legge_regione_abruzzo_impl(
    codice_redazionale: str,
    data_pubblicazione: str,
    articolo: str = "",
    da_carattere: int = 1,
) -> SearchResult:
    """Read original text with positive Abruzzo validation from GU 3a Serie."""
    if invalid_start(da_carattere):
        return SearchResult(
            success=False, source=_SOURCE, error_type="bad_input",
            results_text="da_carattere deve essere >= 1.",
        )
    if articolo and not _abruzzo_re.fullmatch(r"\d+[a-z]?(?:[-/]\w+)?", articolo.strip(), _abruzzo_re.I):
        return SearchResult(
            success=False, source=_SOURCE, error_type="bad_input",
            results_text="Numero articolo non valido.",
        )
    if not _abruzzo_re.fullmatch(r"\d{2}[A-Za-z]\d{5}", codice_redazionale.strip()):
        return SearchResult(
            success=False, source=_SOURCE, error_type="bad_input",
            results_text="Codice redazionale GU non valido.",
        )
    try:
        detail = await fetch_atto(
            "regioni", data_pubblicazione, codice_redazionale, metadata_only=False,
        )
    except ValueError as exc:
        return SearchResult(
            success=False, source=_SOURCE, error_type="bad_input",
            results_text=f"Data o codice non validi: {exc}",
        )
    except Exception as exc:
        return SearchResult(
            success=False, source=_SOURCE, error_type="source_down",
            error_message=str(exc),
        )

    if not detail.text or not _abruzzo_is_law(detail):
        return SearchResult(
            success=False, source=_SOURCE, error_type="no_results",
            results_text=(
                "L'atto non contiene evidenza sufficiente di essere una "
                "legge regionale abruzzese, oppure non e' disponibile il testo "
                "nella GU 3a Serie speciale. Non restituisco testi di altre regioni."
            ),
        )

    text = detail.text
    label = "Testo originario pubblicato in Gazzetta Ufficiale"
    if articolo:
        selected = _abruzzo_article(text, articolo)
        if selected is None:
            return SearchResult(
                success=False, source=_SOURCE, error_type="no_results",
                results_text=(
                    f"Articolo {articolo} non individuato con certezza nel testo; "
                    "consultare il link ufficiale senza dedurre che l'articolo non esista."
                ),
            )
        text = selected
        label += f" — articolo {articolo}"

    # The offset applies to selected article when articolo is set, otherwise to the act.
    if da_carattere > len(text):
        return SearchResult(
            success=False, source=_SOURCE, error_type="bad_input",
            results_text=f"da_carattere supera la lunghezza di {len(text)} caratteri.",
        )
    segment = text[da_carattere - 1:da_carattere - 1 + 25000]
    next_at = da_carattere - 1 + len(segment) + 1
    header = [
        f"# {detail.estremi or 'Legge regionale Abruzzo'}",
        f"**Oggetto**: {detail.title}",
        f"**Fonte**: GU, 3a Serie Speciale - Regioni, pubblicazione {data_pubblicazione}",
        f"**URL ufficiale**: {detail.eli_url}",
        f"**Codice redazionale**: {codice_redazionale}",
        f"**Tipo di testo**: {label}. **Vigenza NON verificata**.",
        "",
        segment,
    ]
    if next_at <= len(text):
        header.append(
            f"\nTesto parziale: {len(text)} caratteri totali. "
            f"Ripetere con da_carattere={next_at} per proseguire."
        )
    header.append(_ABRUZZO_OFFICIAL_SOURCES)
    return SearchResult(
        success=True, source=_SOURCE, num_found=1,
        results_text="\n".join(header),
    )


@mcp.tool(tags={"normativa"})
async def cerca_leggi_regione_abruzzo(
    parole: str = "",
    numero: str = "",
    anno_da: str = "",
    anno_a: str = "",
    max_risultati: int = 20,
) -> str:
    """Cerca leggi della REGIONE ABRUZZO nel catalogo Normattiva Regioni.

    Ricerca per numero, parole e anno di promulgazione della legge (non per
    data di pubblicazione in Gazzetta). Restituisce il collegamento al
    Consiglio regionale e lo stato di vigenza indicato dal catalogo.
    La dicitura VIGENTE non accerta autonomamente modifiche e abrogazioni.
    Un risultato vuoto non dimostra che la legge non esista.
    Per leggere il testo originario nella GU 3a Serie speciale, usare
    leggi_legge_regione_abruzzo con il CODICE REDAZIONALE GU e la data di
    pubblicazione GU (non restituiti necessariamente dalla ricerca federata).
    """
    result = await _cerca_leggi_regione_abruzzo_impl(
        parole, numero, anno_da, anno_a, max_risultati,
    )
    return result.to_str()


@mcp.tool(tags={"normativa"})
async def leggi_legge_regione_abruzzo(
    codice_redazionale: str,
    data_pubblicazione: str,
    articolo: str = "",
    da_carattere: int = 1,
) -> str:
    """Legge il testo PUBBLICATO di una legge regionale ABRUZZO dalla GU Regioni.

    Richiede codice redazionale e data di pubblicazione GU YYYY-MM-DD.
    Con articolo (es. "1") restituisce solo l'articolo, se individuato.
    Controlla che l'atto sia una legge abruzzese; non spaccia il testo
    originario per testo vigente. Per modifiche, abrogazioni e multivigenza
    verificare il repertorio regionale e il BURAT prima di usarlo in perizie.
    """
    result = await _leggi_legge_regione_abruzzo_impl(
        codice_redazionale, data_pubblicazione, articolo, da_carattere,
    )
    return result.to_str()
