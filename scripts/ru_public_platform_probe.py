"""One GET per public Russian procurement listing, bounded and fail-closed.

Exploratory structural evidence only: a page shell or HTTP 200 does not prove
that a live procurement adapter can acquire or search notices.
"""
from __future__ import annotations

import asyncio
import json
from html.parser import HTMLParser
from urllib.parse import urlsplit

from app.sources.http import FetchPolicy, bounded_fetch, source_client


TARGETS = (
    ("tektorg", "www.tektorg.ru", "https://www.tektorg.ru/procedures/bi-procedures"),
    ("roseltorg", "www.roseltorg.ru", "https://www.roseltorg.ru/torgi"),
    ("fabrikant", "soap4.fabrikant.ru", "https://soap4.fabrikant.ru/44/catalog/procedure"),
)


class Structure(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = 0
        self.rows = 0
        self.fabrikant_detail_urls = 0
        self.anchor_hosts = set()
        self.table_count = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            self.table_count += 1
        if tag == "tr":
            self.rows += 1
        if tag != "a":
            return
        self.links += 1
        href = attrs.get("href")
        if not href or href.startswith("//") or "\\" in href:
            return
        parts = urlsplit(href)
        if parts.netloc:
            self.anchor_hosts.add(parts.hostname)
        if (parts.path.startswith("/44/procedure/")
                and parts.path != "/44/procedure/"):
            self.fabrikant_detail_urls += 1


async def probe(name, host, url):
    entry = {"state": "BLOCKED", "http_status": None,
             "bytes": 0, "tables": 0, "rows": 0,
             "links": 0, "fabrikant_detail_links": 0,
             "error_type": None}

    async def status_hook(response):
        entry["http_status"] = response.status_code

    try:
        with bounded_fetch(FetchPolicy(frozenset({host}), 1, max_bytes=2 * 1024 * 1024)):
            async with source_client(
                timeout=12, trust_env=False, follow_redirects=False,
                event_hooks={"response": [status_hook]},
                headers={"Accept": "text/html"},
            ) as client:
                response = await asyncio.wait_for(client.get(url), timeout=18)
                response.raise_for_status()
                if "html" not in response.headers.get("content-type", "").lower():
                    entry["state"] = "WRONG_CONTENT_TYPE"
                    return entry
                entry["bytes"] = len(response.content)
                parser = Structure()
                parser.feed(response.content.decode("utf-8-sig", errors="replace"))
                entry.update(tables=parser.table_count, rows=parser.rows,
                             links=parser.links,
                             fabrikant_detail_links=parser.fabrikant_detail_urls)
                entry["state"] = "HTML_RECEIVED_NOT_VERIFIED"
    except Exception as error:
        entry["error_type"] = type(error).__name__
    return entry


def main():
    report = {}
    for name, host, url in TARGETS:
        report[name] = asyncio.run(probe(name, host, url))
    print("RU_PUBLIC_PLATFORMS_SHAPE=" +
          json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    print("VERIFIED_LIVE_ADAPTERS_FROM_THIS_PROBE=0")
    print("NO_LOGIN_NO_CAPTCHA_BYPASS_NO_TLS_DISABLE=YES")
    print("PRODUCTION_CHANGED=NO")


if __name__ == "__main__":
    main()
