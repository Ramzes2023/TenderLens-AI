"""Verify two original public Dagestan detail URLs observed in a live native list.

Fixed IDs come from HTTP 200 real first-party JSON list observed on GitHub
Actions 2026-10-18 (research run 39148567179). No arbitrary URL input,
redirect following, proxy, private session, cookies or production write.
"""
from __future__ import annotations

import asyncio
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit

import httpx
from app.sources.http import (
    ConnectorTransportError, FetchPolicy, bounded_fetch, source_client,
)

HOST = "goszakaz.e-dag.ru"
DETAIL_IDS = ("5611345", "5611196")
PATH = "/smallpurchases/GzwSP/"
MAX_BYTES = 1_800_000


def canonical_detail(item_id: str) -> str:
    if type(item_id) is not str or not re.fullmatch(r"[0-9]{6,12}", item_id):
        raise ValueError("Untrusted native detail ID")
    url = "https://" + HOST + PATH + item_id
    p = urlsplit(url)
    if (p.scheme != "https" or p.hostname != HOST or p.port
            or p.username or p.password or p.query or p.fragment):
        raise ValueError("Noncanonical original detail")
    return url


class Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden: list[str] = []
        self.visible: list[str] = []
        self.headings: list[str] = []
        self.heading: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "svg", "noscript", "template", "iframe"}:
            self.hidden.append(tag)
        if not self.hidden and tag in {"h1", "h2"} and self.heading is None:
            self.heading = []
    def handle_data(self, data):
        if not self.hidden:
            self.visible.append(data)
            if self.heading is not None:
                self.heading.append(data)

    def handle_endtag(self, tag):
        if self.hidden:
            if self.hidden[-1] == tag:
                self.hidden.pop()
            return
        if tag in {"h1", "h2"} and self.heading is not None:
            self.headings.append(" ".join(" ".join(self.heading).split()))
            self.heading = None


def original_detail_evidence(raw: bytes, item_id: str):
    canonical_detail(item_id)
    if type(raw) is not bytes or not 200 <= len(raw) <= MAX_BYTES or b"\x00" in raw:
        raise ValueError("Untrusted empty/oversized first-party detail")
    parsed = Visible()
    parsed.feed(raw.decode("utf-8-sig", "replace"))
    parsed.close()
    text = " ".join(" ".join(parsed.visible).split())
    headings = tuple(h for h in parsed.headings if len(h) >= 8)
    # A login shell, JavaScript-only placeholder or static portal title is not
    # evidence of a real, independently fetched original tender.
    has_native = bool(re.search(r"ИМЗ[-–\s]?20[0-9]{2}[-–][0-9]{4,9}", text, re.I))
    has_identity = bool(re.search(r"(?<![0-9])" + re.escape(item_id) + r"(?![0-9])", text))
    has_buyer = bool(re.search(r"(?:Заказчик|Наименование заказчика)\s*[:—]", text, re.I))
    has_price = bool(re.search(r"(?:Цена|НМЦК|Начальная \(\s*максимальная\s*\) цена)\s*[:—]", text, re.I))
    has_deadline = bool(re.search(r"(?:Окончани[ея] подачи заявок|Срок подачи заявок|Прием заявок)", text, re.I))
    flags = (bool(headings), has_native, has_identity, has_buyer, has_price, has_deadline)
    if not all((bool(headings), has_native, has_buyer, has_price, has_deadline)):
        raise ValueError("Public page does not prove original buyer/price/deadline")
    # Require the native number and the native row-route ID both visible.
    if not has_identity:
        raise ValueError("Original detail lacks independently verified list ID")
    return flags


async def prove_live():
    results = []
    with bounded_fetch(FetchPolicy(frozenset({HOST}), len(DETAIL_IDS),
                                   max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=23, trust_env=False, follow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"},
        ) as client:
            for original_id in DETAIL_IDS:
                response = await client.get(canonical_detail(original_id))
                response.raise_for_status()
                if "html" not in response.headers.get("content-type", "").lower():
                    raise ValueError("Official small-purchase detail is not HTML")
                flags = original_detail_evidence(response.content, original_id)
                print("RU_DAG_FIXED_NATIVE_DETAIL_ID=" + original_id)
                print("RU_DAG_DETAIL_PROOF_FLAGS=" + ",".join(str(x) for x in flags))
                results.append(original_id)
    if len(set(results)) != 2:
        raise ValueError("Original detail evidence not independent")
    print("RU_DAG_TWO_INDEPENDENT_ORIGINAL_DETAILS=PROVED_RESEARCH_ONLY")
    print("WORKER_SQL_USER_QUERY_PROVED=NO")
    return 0


def main():
    try:
        return asyncio.run(prove_live())
    except (ValueError, ConnectorTransportError, httpx.HTTPError,
            OSError, TimeoutError) as error:
        print("RU_DAG_TWO_ORIGINAL_DETAILS=BLOCKED_" + type(error).__name__)
        if isinstance(error, ConnectorTransportError):
            print("RU_DAG_RETRYABLE=" + str(error.retryable))
        return 2
    finally:
        print("PRODUCTION_CHANGED=NO")


if __name__ == "__main__":
    raise SystemExit(main())
