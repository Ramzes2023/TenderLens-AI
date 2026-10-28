"""Publisher-controlled Fabrikant regional catalogue matrix, read-only.

Checks the *official* published-list path, including the organizer filter,
on both known official Fabrikant hostnames. Earlier probes checked the soap4
requestOffer/base catalogue (HTTP non-2xx), not the precise published path
shown in the first-party original's backurl.

Even if HTML is visible, this only verifies the list. Source activation
still requires same-host first-party originals, future submission deadlines,
fenced Worker, disposable SQL, deduplication and the guest search.
"""
from __future__ import annotations

import asyncio
import json
from html.parser import HTMLParser
from urllib.parse import urlsplit

from app.sources.http import ConnectorTransportError, FetchPolicy, bounded_fetch, source_client

HOSTS = ("soap4.fabrikant.ru", "44.fabrikant.ru")
ORGANIZERS = (("ingushetia","0608058533"),("chechnya","2016014690"))
PATH = "/44/catalog/procedure/published"
MAX_BYTES = 1_800_000


class OfficialOriginalAnchors(HTMLParser):
    def __init__(self, host):
        super().__init__(convert_charrefs=True)
        self.host = host
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        raw = dict(attrs).get("href")
        if type(raw) is not str or not 0 < len(raw) <= 1500 or "\\" in raw:
            return
        if raw.startswith("/"):
            raw = "https://" + self.host + raw
        try:
            p = urlsplit(raw)
            import re
            match = re.fullmatch(r"/44/procedure/[a-z0-9-]{2,18}/([0-9]{19})",p.path)
            if (p.scheme=="https" and p.hostname in HOSTS and
                    p.port in (None,443) and not p.username and not p.password and
                    not p.fragment and match and (not p.query or
                        (p.query.startswith("backurl=") and "&" not in p.query
                         and len(p.query) < 512))):
                self.ids.add(match.group(1))
        except ValueError:
            return


def official_list_ids(body: bytes, host: str) -> set[str]:
    if host not in HOSTS or type(body) is not bytes or not 0 < len(body) <= MAX_BYTES:
        raise ValueError("Invalid official publisher response")
    p = OfficialOriginalAnchors(host)
    p.feed(body.decode("utf-8-sig","replace"))
    p.close()
    return p.ids


def safe_category(exc):
    if isinstance(exc,ConnectorTransportError):
        v=getattr(exc,"reason","policy")
        return v if v in {"network","http_status","http_transient",
                          "tls_certificate","public_ip","response_size","policy"} else "unclassified"
    if isinstance(exc,ValueError):
        return "source_contract"
    return "unclassified"


async def inspect():
    records=[]
    with bounded_fetch(FetchPolicy(frozenset(HOSTS),len(HOSTS)*len(ORGANIZERS),
                                   max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=25,trust_env=False,follow_redirects=False,
            headers={"Accept":"text/html","User-Agent":"Mozilla/5.0"},
        ) as client:
            for host in HOSTS:
                for region,inn in ORGANIZERS:
                    url=("https://"+host+PATH+"?placer_search_str="+inn+
                         "&order=publication_datetime&dir=desc")
                    try:
                        resp=await client.get(url)
                        resp.raise_for_status()
                        if "html" not in resp.headers.get("content-type","").lower():
                            raise ValueError("Official list HTML required")
                        ids=official_list_ids(resp.content,host)
                        records.append({
                            "publisher_host":host,"region":region,
                            "category":"published_html_with_anchors" if ids else "published_html_no_valid_anchors",
                            "canonical_original_ids":len(ids),
                        })
                    except Exception as exc:
                        records.append({"publisher_host":host,"region":region,
                                        "category":safe_category(exc),
                                        "canonical_original_ids":0})
    return records


def main():
    for record in asyncio.run(inspect()):
        print("FABRIKANT_REGION_PUBLISHED_ROUTE="+json.dumps(record,sort_keys=True))
    print("INDIVIDUAL_LIVE_DETAIL_AND_WORKER=NOT_VERIFIED")
    print("REGIONAL_SOURCES_ACTIVATED=NO")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
