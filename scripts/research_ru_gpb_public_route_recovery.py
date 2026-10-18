"""Bounded, read-only diagnostic of both published GPB corporate listing hosts.

No credentials, cookies, redirects, proxy, retries, mutations, URL guessing,
source registration, production database, or fabricated tender evidence.
"""
from __future__ import annotations

import asyncio
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit

import httpx

from app.sources.http import FetchPolicy, ConnectorTransportError, bounded_fetch, source_client
from app.sources.gpb_etp_public import _PATH

HOSTS = ("etpgpb.ru", "new.etpgpb.ru")
LISTINGS = tuple("https://" + hostname + "/procedures/" for hostname in HOSTS)
MAX_BYTES = 1_800_000


def first_party_numeric_links(raw: bytes, listing: str) -> tuple[str, ...]:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES or b"\x00" in raw:
        raise ValueError("Unsafe public GPB diagnostic HTML")
    base = urlsplit(listing)
    if base.scheme != "https" or base.netloc not in HOSTS or base.path != "/procedures/":
        raise ValueError("Unapproved GPB listing")
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.hrefs = []
        def handle_starttag(self, tag, attrs):
            if tag == "a":
                href = dict(attrs).get("href")
                if type(href) is str and len(href) < 1300:
                    self.hrefs.append(href)
    parser = Links()
    parser.feed(raw.decode("utf-8-sig", "replace"))
    parser.close()
    ids = set()
    for value in parser.hrefs:
        if "\\" in value or any(ord(c) < 32 or c.isspace() for c in value):
            continue
        try:
            parsed = urlsplit(urljoin(listing, value))
            if (parsed.scheme != "https" or parsed.netloc not in HOSTS
                    or parsed.query or parsed.fragment or parsed.username or parsed.password
                    or parsed.port is not None):
                continue
            match = _PATH.fullmatch(parsed.path)
            if match:
                ids.add(match.group(1))
        except ValueError:
            continue
    return tuple(sorted(ids))[:15]


async def probe():
    success = 0
    with bounded_fetch(FetchPolicy(frozenset(HOSTS), 2, max_bytes=MAX_BYTES)):
        for host, url in zip(HOSTS, LISTINGS):
            try:
                # New client per host, so no guest cookies can carry over.
                async with source_client(
                    timeout=22, follow_redirects=False, trust_env=False,
                    headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
                ) as client:
                    response = await client.get(url)
                    print("RU_GPB_HOST=" + host)
                    print("RU_GPB_STATUS=" + str(response.status_code))
                    mime = response.headers.get("content-type", "").lower()
                    print("RU_GPB_HTML=" + str("html" in mime))
                    print("RU_GPB_BYTES=" + str(len(response.content)))
                    destination = response.headers.get("location", "")
                    if 300 <= response.status_code < 400:
                        try:
                            redirect = urlsplit(urljoin(url, destination))
                            permitted = (redirect.scheme == "https"
                                         and redirect.netloc in HOSTS
                                         and redirect.username is None
                                         and redirect.password is None)
                        except ValueError:
                            permitted = False
                        print("RU_GPB_REDIRECT_TO_ALLOWED_HOST=" + str(permitted))
                    if response.status_code == 200 and "html" in mime:
                        ids = first_party_numeric_links(response.content, url)
                        print("RU_GPB_NATIVE_PUBLIC_LINK_COUNT=" + str(len(ids)))
                        success += int(len(ids) >= 2)
            except (ConnectorTransportError, httpx.HTTPError, ValueError,
                    OSError, TimeoutError) as exc:
                print("RU_GPB_HOST=" + host)
                print("RU_GPB_DIAGNOSTIC=BLOCKED_" + type(exc).__name__)
                if isinstance(exc, ConnectorTransportError):
                    print("RU_GPB_RETRYABLE=" + str(exc.retryable))
    print("RU_GPB_DIAGNOSTIC=" + ("INDEX_POSSIBLE_NOT_REAL_DETAIL_PROOF" if success
                                   else "NO_TWO_ORIGINAL_LINKS"))
    print("PRODUCTION_CHANGED=NO")
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(probe()))
