"""One-shot technical probe of public, official regional law search forms.

Only page structure is printed; no cookies, user data, response bodies or tokens.
Not part of production and not used for legal conclusions.
"""
import re
import httpx
from bs4 import BeautifulSoup

SITES = (
    "https://www.normattiva.it/mfr/",
    "https://www.affariregionali.gov.it/it/banche-dati/leggi-regionali/",
    "https://www2.consiglio.regione.abruzzo.it/affassweb/leggi-provvedimenti.asp",
    "https://www.regione.abruzzo.it/leggi-atti-bandi/leggi-e-progetti-di-legge",
)
for url in SITES:
    print("\nSOURCE", url, flush=True)
    try:
        r = httpx.get(url, timeout=12.0, follow_redirects=True, headers={"User-Agent":"Mozilla/5.0"})
        print("STATUS", r.status_code, "FINAL",r.url,"LEN",len(r.content),flush=True)
        soup = BeautifulSoup(r.text,"html.parser")
        for f in soup.select("form")[:5]:
            fields = [
                (tag.name,tag.get("name", ""),tag.get("id",""),tag.get("type",""))
                for tag in f.select("input, select, textarea")[:35]
            ]
            print("FORM",f.get("method","GET"),f.get("action",""),"FIELDS",fields,flush=True)
        for a in soup.select("a[href]"):
            if re.search(r"leggi|vigent|ricerc|normativ", a.get_text(" ", strip=True), re.I):
                href=a.get("href","")
                if href.startswith("/") or href.startswith("https://"):
                    print("LINK",a.get_text(" ",strip=True)[:100],href[:180],flush=True)
                    if len(soup.select("a[href]"))>100: break
        print("SCRIPT_PATHS",[x.get("src","")[:160] for x in soup.select("script[src]")[:15]],flush=True)
    except Exception as e:
        print("UNREACHABLE",str(e)[:300],flush=True)
