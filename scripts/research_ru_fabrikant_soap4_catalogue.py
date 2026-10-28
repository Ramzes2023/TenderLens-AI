"""Official soap4 public catalogue discovery research, distinct from details.

Open, bounded publisher catalogues are *not* interchangeable with a
third-party index of EIS IDs. Extract only true first-party same-host
anchor hrefs with 19-digit native EIS numbers. No JavaScript-origin
guesses, authenticated sections, redirects, proxies or fallback sources.
Output counts only. Never activate source from a cached historical row.
"""
from __future__ import annotations
import asyncio
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from app.sources.http import FetchPolicy, bounded_fetch, source_client, ConnectorTransportError

HOST="soap4.fabrikant.ru"
PATHS=("/44/catalog/procedure/requestOffer", "/44/catalog/procedure")
ID_PATH=re.compile(r"/44/procedure/[a-z0-9-]{2,18}/([0-9]{19})\Z")
CURRENT_SAMPLE_IDS=frozenset({
    "0114500000826002518", # independently confirmed firstparty detail
    "0194200000526005756", # independently confirmed firstparty detail
    "0194200000526005775", # independently confirmed firstparty detail
})


class OfficialAnchors(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids=set()
    def handle_starttag(self,tag,attrs):
        if tag!="a":
            return
        href=dict(attrs).get("href")
        if type(href) is not str or len(href)>1600:
            return
        if (not href.startswith("/") and not href.startswith("https://"+HOST+"/")):
            return
        try:
            p=urlsplit(urljoin("https://"+HOST+"/",href))
            matched=ID_PATH.fullmatch(p.path)
            if (p.scheme=="https" and p.hostname==HOST and p.port in (None,443)
                and not p.username and not p.password and not p.fragment
                and matched and (not p.query or (
                    len(p.query)<512 and p.query.startswith("backurl=")))):
                self.ids.add(matched.group(1))
        except ValueError:
            pass


def catalogue_ids(payload:bytes) -> set[str]:
    if type(payload) is not bytes or not 0<len(payload)<=1_800_000:
        raise ValueError("Invalid official catalogue")
    parser=OfficialAnchors()
    parser.feed(payload.decode("utf-8-sig","replace"))
    parser.close()
    return parser.ids


async def inspect():
    results=[]
    with bounded_fetch(FetchPolicy(frozenset({HOST}),len(PATHS),max_bytes=1_800_000)):
        async with source_client(timeout=25,follow_redirects=False,trust_env=False,
            headers={"Accept":"text/html","User-Agent":"Mozilla/5.0"}) as client:
            for path in PATHS:
                try:
                    r=await client.get("https://"+HOST+path)
                    r.raise_for_status()
                    if "html" not in r.headers.get("content-type","").lower():
                        raise ValueError("Not original official HTML")
                    ids=catalogue_ids(r.content)
                    results.append({
                        "catalogue":path,
                        "category":"public_original_links_visible",
                        "original_anchor_count":len(ids),
                        "sample_current_originals_discovered":len(ids & CURRENT_SAMPLE_IDS),
                    })
                except ConnectorTransportError as e:
                    reason=e.reason if e.reason in {
                        "network","tls_certificate","http_status","http_transient",
                        "policy","public_ip","response_size"} else "unclassified"
                    results.append({"catalogue":path,"category":reason})
                except Exception:
                    results.append({"catalogue":path,"category":"unclassified"})
    return results


def main():
    for row in asyncio.run(inspect()):
        print("FABRIKANT_OFFICIAL_CATALOGUE="+json.dumps(row,sort_keys=True))
    print("REGIONAL_CURRENT_DISCOVERY_AND_WORKER=NOT_PROVED")
    print("SOURCES_ACTIVATED=NO")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
