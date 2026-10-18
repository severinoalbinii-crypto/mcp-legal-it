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


# Discover stable HTML form controls used by the public Normattiva regional index.
from urllib.parse import urljoin
try:
    with httpx.Client(timeout=15, follow_redirects=True, headers={"User-Agent":"Mozilla/5.0"}) as c:
        base="https://www.normattiva.it/mfr/"
        page=c.get(base)
        soup=BeautifulSoup(page.text,"html.parser")
        form=soup.find("form",action=lambda v: bool(v and "/ricerca/semplice/" in v))
        if form:
            print("\nNORMATTIVA_FORM_ACTION",form.get("action"),flush=True)
            for el in form.find_all("input"):
                if el.get("name") in ("tipoLeggeList","containsType","regioneList","_regioneList","ricerca","annoProvvedimento","numeroProvvedimento"):
                    print("FIELD",el.get("name"),"TYPE",el.get("type"),"VALUE",el.get("value"),"ID",el.get("id"),"CHECKED",el.has_attr("checked"),flush=True)
            for el in form.find_all("button"):
                print("BUTTON",el.get("name"),el.get("value"),el.get_text(" ",strip=True)[:120],flush=True)
            # Try only one historical statute with its known number/year.
            region_values=[
                el.get("value","") for el in form.find_all("input",{"name":"regioneList"})
                if "ABRUZZO" in (el.get("value","")+" "+str(el.parent.get_text(" ",strip=True)[:100])).upper()
            ]
            print("ABRUZZO_CHECKBOX_VALUES",region_values,flush=True)
            # First region typically comes first, as in the public GUI.
            if not region_values:
                first=form.find("input",{"name":"regioneList"})
                if first:
                    region_values=[first.get("value","")]
                    print("ABRUZZO_VALUE_BY_UI_FIRST",region_values,flush=True)
            radio=form.find("input",{"name":"containsType","checked":True}) or form.find("input",{"name":"containsType"})
            payload={
                "numeroProvvedimento":"58",
                "giornoProvvedimento":"",
                "meseProvvedimento":"",
                "annoProvvedimento":"2023",
                "tipoLeggeList":(form.find("input",{"name":"tipoLeggeList"}) or {}).get("value",""),
                "containsType":radio.get("value") if radio else "",
                "ricerca":"",
                "regioneList": region_values[0] if region_values else "",
            }
            print("POST_FIELDS",payload,flush=True)
            result=c.post(urljoin(base,form.get("action")),data=payload)
            parsed=BeautifulSoup(result.text,"html.parser")
            print("POST_STATUS",result.status_code,"URL",result.url,"LENGTH",len(result.content),flush=True)
            print("POST_TITLE",parsed.title.get_text(" ",strip=True) if parsed.title else "",flush=True)
            print("POST_TEXT",parsed.get_text(" ",strip=True)[:2500],flush=True)
            for link in parsed.select("a[href]")[:35]:
                print("POST_LINK",link.get_text(" ",strip=True)[:80],link.get("href","")[:220],flush=True)
except Exception as exc:
    print("NORMATTIVA_PROBE_ERROR",str(exc)[:350],flush=True)
