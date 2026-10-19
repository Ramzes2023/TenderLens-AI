"""Read-only official GPB Gos44 published-original transport research.

Two fixed publicly documented first-party original 44-FZ procurement pages.
Does NOT prove a current GPB list/API, external notification, live subscriber,
or distinct publication from EIS 44-FZ. No login, redirect, proxy, TLS bypass.
"""
from __future__ import annotations

import asyncio
import re
from html.parser import HTMLParser

import httpx

from app.sources.http import (
    ConnectorTransportError, FetchPolicy, bounded_fetch, source_client,
)

HOST = "gos.etpgpb.ru"
MAX_BYTES = 2_200_000
# These two *real* published October 2026 EIS-44 records were independently
# publicly indexed. Never count as new publications distinct from EIS.
ORIGINALS = (
    ("https://gos.etpgpb.ru/front/procedure/view/fee4820f-933b-4174-b61c-ddc66e7e0500",
     "0891200000626010069"),
    ("https://gos.etpgpb.ru/front/procedure/view/c774410d-b89d-415d-81e5-5445233930bc",
     "0358100002226000213"),
)


class Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.words = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "noscript", "svg", "iframe"}:
            self.hidden += 1

    def handle_data(self, data):
        if not self.hidden:
            self.words.append(data)

    def handle_endtag(self, tag):
        if tag in {"script", "style", "template", "noscript", "svg", "iframe"} and self.hidden:
            self.hidden -= 1


def verify_official_original(body: bytes, number: str) -> bool:
    if (type(body) is not bytes or not 0 < len(body) <= MAX_BYTES
            or b"\0" in body or type(number) is not str
            or re.fullmatch(r"[0-9]{19}", number) is None):
        raise ValueError("Invalid official GPB published original input")
    parser = Visible()
    parser.feed(body.decode("utf-8-sig", "replace"))
    parser.close()
    text = " ".join(" ".join(parser.words).split())
    if (not re.search(r"Сведения\s+о\s+процедуре", text)
            or "Номер извещения" not in text
            or number not in text
            or not any(term in text for term in (
                "Наименование объекта закупки", "Общая информация о закупке",
            ))
            or re.search(r"требуется\s+(?:вход|авторизация)", text, re.IGNORECASE)):
        raise ValueError("Not a genuine visible first-party 44-FZ notice")
    return True


async def proof() -> int:
    observed = 0
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 2, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=25, trust_env=False, follow_redirects=False,
            headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
        ) as client:
            for url, number in ORIGINALS:
                reply = await client.get(url)
                print("RU_GPB_GOS_ORIGINAL_HTTP_STATUS=" + str(reply.status_code))
                reply.raise_for_status()
                if "html" not in reply.headers.get("content-type", "").lower():
                    raise ValueError("Official original did not return HTML")
                verify_official_original(reply.content, number)
                observed += 1
    return observed


def main() -> int:
    try:
        count = asyncio.run(proof())
    except (ConnectorTransportError, ValueError, httpx.HTTPError, OSError, TimeoutError) as exc:
        print("RU_GPB_GOS_ORIGINALS=BLOCKED_" + type(exc).__name__)
        if isinstance(exc, ConnectorTransportError):
            print("RU_GPB_GOS_RETRYABLE=" + str(exc.retryable))
        print("CURRENT_LIST_VERIFIED=NO")
        print("SOURCE_INTEGRATED=NO")
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_GPB_GOS_DISTINCT_ORIGINALS=" + str(count))
    print("EIS_44_FZ_DUPLICATE_POTENTIAL=YES")
    print("CURRENT_LIST_VERIFIED=NO")
    print("SOURCE_INTEGRATED=NO")
    print("PRODUCTION_CHANGED=NO")
    return 0 if count == 2 else 2


if __name__ == "__main__":
    raise SystemExit(main())
