"""Bounded and read-only official/portal-owned Russian procurement discovery.

These sites are CANDIDATES only. No auth, HTTP proxy, redirects, scripts,
mocks, or production ingestion. Only visible public link shapes are logged.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, ProxyHandler, HTTPRedirectHandler
from urllib.error import URLError, HTTPError
import json
import re
import ssl

URLS = {
    "sverdlovsk_small": "https://torgi.egov66.ru/smallpurchases/GzwSP/NoticesGrid",
    "tatarstan_trading": "https://etpzakupki.tatar/app/SearchLots/",
    "bashkortostan_small": "https://zakaz.bashkortostan.ru/quotation-requests/new",
    "lot_online": "https://tender.lot-online.ru/search",
    "etp_rt": "https://etp-rt.ru/search/open",
    "vologda_small": "https://szvo.gov35.ru/web/gz/em",
    "samara_small": "https://webtorgi.samregion.ru/smallpurchases",
    "yanao_small": "https://zakupki.yanao.ru/vitriny-zakupok/oos-rks-001-001",
    "moscow_suppliers": "https://zakupki.mos.ru/",
    "mobl_small": "https://easuz.mosreg.ru/for-business",
    "rftorgi": "https://rftorgi.ru/tenders",
    "rtstomsk": "https://region70.rts-tender.ru/",
    "rtsdagestan": "https://marketrd.rts-tender.ru/",
    "rtsomsk": "https://zmo-omsk.rts-tender.ru/",
    "rtsyaroslavl": "https://market-yaroslavl.rts-tender.ru/",
    "sber_berezka": "https://agregatoreat.ru/",
}
CAP = 1_500_000
DETAIL_HINT = re.compile(r"(?:notice|purchase|lot|tender|procedure|izve|zakup|notification|/trade/|/bid/)", re.I)
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class Anchors(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.current = None
        self.title = ""
        self.headings = []
        self._head = None
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "a":
            self.current = [d.get("href", ""), []]
        if tag in ("h1","h2","h3"):
            self._head = [tag, []]
    def handle_data(self, data):
        if self.current is not None: self.current[1].append(data)
        if self._head is not None: self._head[1].append(data)
    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            self.links.append((self.current[0], " ".join(" ".join(self.current[1]).split())[:110]))
            self.current = None
        if self._head is not None and self._head[0] == tag:
            self.headings.append(" ".join(" ".join(self._head[1]).split())[:140])
            self._head = None

def probe(item):
    key, url = item
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != parsed.hostname or parsed.query or parsed.fragment:
            raise ValueError("Unexpected input URL")
        req = Request(url, headers={"User-Agent":"Mozilla/5.0 (compatible; VALYQONSourceResearch/1.0)", "Accept":"text/html", "Accept-Encoding":"identity"})
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
        with opener.open(req, timeout=13) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            raw = response.read(CAP+1)
        if status != 200 or "html" not in content_type.lower() or not 0<len(raw)<=CAP:
            raise ValueError("Non-200/non-HTML/oversized")
        doc = Anchors()
        doc.feed(raw.decode("utf-8-sig","replace"))
        safe = {}
        for href,title in doc.links:
            try:
                full = urljoin(url,href)
                p = urlsplit(full)
                if p.scheme=="https" and p.hostname==parsed.hostname and p.netloc==parsed.netloc and DETAIL_HINT.search(p.path) and p.path not in ("", parsed.path):
                    safe.setdefault(p.path, (full[:260],title))
            except ValueError:
                pass
        return {"key":key,"state":"PUBLIC_HTML","bytes":len(raw),"public_anchors":len(doc.links),
                "candidate_detail_paths":len(safe),"examples":list(safe.values())[:3],
                "headings":doc.headings[:2]}
    except HTTPError as e:
        return {"key":key,"state":"HTTP_ERROR","status":e.code}
    except (URLError, OSError,TimeoutError,ValueError) as e:
        return {"key":key,"state":"BLOCKED","failure_class":type(e).__name__}

def main():
    results=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(probe,item) for item in URLS.items()]):
            results.append(f.result())
    for result in sorted(results, key=lambda p:p["key"]):
        print("RU_REGIONAL_PUBLIC_DIAGNOSTIC="+json.dumps(result,ensure_ascii=False,sort_keys=True))
    good=[p for p in results if p["state"]=="PUBLIC_HTML" and p["candidate_detail_paths"]>=2]
    print(f"RU_REGIONAL_CANDIDATES_WITH_LINKS={len(good)}/{len(URLS)}")
    print("PRODUCTION_CHANGED=NO")
    return 0 if good else 2

if __name__=="__main__":
    raise SystemExit(main())
