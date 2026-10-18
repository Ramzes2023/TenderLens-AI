"""Fail-closed NORTH CAUCASUS small-purchase original-notice research.

The five regional storefronts are CANDIDATES, not five integrated sources.
A successful homepage or a shared operator storefront is not original proof.
This standalone reader only uses the pinned public HTTPS hosts below; fixtures
are never used by live acceptance and the production source catalog is untouched.
"""
from __future__ import annotations

import argparse
import asyncio
from html.parser import HTMLParser
import re
from urllib.parse import parse_qsl, urljoin, urlsplit

import httpx

from app.sources.http import (
    ConnectorTransportError, FetchPolicy, bounded_fetch, source_client,
)

# Operator-hosted regional subdomains can share upstream inventory. They are
# independent REGIONAL VIEWS to investigate, not automatically new connectors.
REGIONS = {
    "north_ossetia": "15.portalregion.ru",
    "kbr": "kbr.sberb2b.ru",
    "nalchik": "nalchik.sberb2b.ru",
    "kchr": "kchr.sberb2b.ru",
    "dagestan_vitrine": "dagestan.sberb2b.ru",
}
REQUIRED_ORIGINALS = 2
MAX_BYTES = 1_500_000
MAX_LINK = 512
# Only original-detail routes; /news, /catalog, /login, /search or arbitrary
# scripts must never be counted as procurements.
DETAIL_ROUTE = re.compile(
    r"(?i)/(?:[a-z0-9_-]*/)*(?:purchase|purchases|tender|tenders|"
    r"notice|notices|order|orders|procedure|procedures|procurement|"
    r"procurements|zakupki|zakupka|bid|bids)/[a-z0-9_./-]*"
)
BLOCKED = re.compile(
    r"(?i)(?:^|/)(?:login|signin|auth|account|admin|cabinet|"
    r"registration|search|catalog|news|api)(?:/|$)"
)
NATIVE_NUMBER = re.compile(r"(?<!\d)(?:№\s*|#\s*)?(\d{6,16})(?!\d)")
PRICE = re.compile(
    r"(?i)(?:начальн\w*\s+цен\w*|цена\s+закупки|цена\s+контракта|"
    r"нмцк|стоимость\s+закупки)\s*[:—-]?\s*"
    r"[\d\s\u00a0,.]{2,20}\s*(?:руб(?:лей|ля|\.)?|₽)"
)
BUYER = re.compile(r"(?i)(?:заказчик|наименование\s+заказчика)\s*[:—-]?\s*[^\s:]{2,}")
CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def normalized(raw: str) -> str:
    return " ".join(raw.split())


class VisibleTable(HTMLParser):
    """Only visible anchor/row/cell text. JS-embedded synthetic data is ignored."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[dict] = []
        self.links: list[tuple[str | None, str]] = []
        self.text: list[str] = []
        self.row = None
        self.cell = None
        self.anchor = None
        self.hidden: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "iframe", "svg", "noscript"}:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag == "tr":
            self.row = {"cells": [], "links": []}
        elif tag in {"td", "th"} and self.row is not None:
            self.cell = []
        elif tag == "a":
            self.anchor = [dict(attrs).get("href"), []]

    def handle_data(self, data):
        if self.hidden:
            return
        self.text.append(data)
        if self.cell is not None:
            self.cell.append(data)
        if self.anchor is not None:
            self.anchor[1].append(data)

    def handle_endtag(self, tag):
        if self.hidden:
            if self.hidden[-1] == tag:
                self.hidden.pop()
            return
        if tag == "a" and self.anchor is not None:
            pair = (self.anchor[0], normalized(" ".join(self.anchor[1])))
            self.links.append(pair)
            if self.row is not None:
                self.row["links"].append(pair)
            self.anchor = None
        elif tag in {"th", "td"} and self.cell is not None and self.row is not None:
            self.row["cells"].append(normalized(" ".join(self.cell)))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def parse_html(body: bytes) -> VisibleTable:
    if type(body) is not bytes or not 0 < len(body) <= MAX_BYTES or b"\x00" in body:
        raise ValueError("Invalid public procurement HTML document")
    doc = VisibleTable()
    doc.feed(body.decode("utf-8-sig", "replace"))
    doc.close()
    return doc


def safe_detail(href: str | None, host: str) -> str | None:
    """Same-origin public detail only: never follow auth/redirect/query URLs."""
    if (not isinstance(href, str) or not 0 < len(href) <= MAX_LINK
            or "\\" in href or any(ch.isspace() or ord(ch) < 32 for ch in href)):
        return None
    try:
        u = urlsplit(urljoin("https://" + host + "/", href))
        args = parse_qsl(u.query, keep_blank_values=False, strict_parsing=True)
    except ValueError:
        return None
    if (u.scheme != "https" or u.netloc != host or u.username or u.password
            or u.port is not None or u.fragment
            or len(args) > 1 or BLOCKED.search(u.path)
            or not DETAIL_ROUTE.fullmatch(u.path)
            or not re.search(r"\d{5,16}", u.path + "?" + u.query)
            or any(key.lower() not in {"id", "noticeid", "purchaseid", "tenderid"}
                   or not re.fullmatch(r"\d{5,16}", value)
                   for key, value in args)):
        return None
    return u.geturl()


def listing_originals(body: bytes, host: str):
    doc = parse_html(body)
    cards = []
    seen = set()
    for row in doc.rows:
        numbers = {
            m.group(1)
            for cell in row["cells"]
            for m in NATIVE_NUMBER.finditer(cell)
        }
        if len(numbers) != 1:
            continue
        number = next(iter(numbers))
        for href, title in row["links"]:
            url = safe_detail(href, host)
            if (url is None or number in seen or not 8 <= len(title) <= 500
                    or not CYRILLIC.search(title)):
                continue
            seen.add(number)
            cards.append((number, title, url))
            break
    if len(cards) < REQUIRED_ORIGINALS:
        raise ValueError("No two unique native small-purchase rows with direct original links")
    return cards[:REQUIRED_ORIGINALS]


def verify_original(body: bytes, number: str, title: str, url: str, host: str):
    if safe_detail(url, host) != url or not re.fullmatch(r"\d{6,16}", number):
        raise ValueError("Unsafe regional original identity")
    visible = normalized(" ".join(parse_html(body).text))
    if (number not in visible or title.casefold() not in visible.casefold()
            or not BUYER.search(visible) or not PRICE.search(visible)):
        raise ValueError("Independent source number/title/buyer/price not confirmed")
    return number, title, url


async def check_region(region: str):
    host = REGIONS[region]
    index = "https://" + host + "/"
    verified = []
    with bounded_fetch(FetchPolicy(frozenset({host}), 3, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=20, trust_env=False, follow_redirects=False,
            headers={"Accept": "text/html", "User-Agent": "VALYQON-ReadOnly-Research/1.0"},
        ) as client:
            listing = await client.get(index)
            listing.raise_for_status()
            if "html" not in listing.headers.get("content-type", "").lower():
                raise ValueError("Public regional homepage is not HTML")
            cards = listing_originals(listing.content, host)
            for number, title, detail_url in cards:
                detail = await client.get(detail_url)
                detail.raise_for_status()
                if "html" not in detail.headers.get("content-type", "").lower():
                    raise ValueError("Original regional detail is not HTML")
                verified.append(verify_original(
                    detail.content, number, title, detail_url, host,
                ))
    if len({number for number, _, _ in verified}) != REQUIRED_ORIGINALS:
        raise ValueError("Original notices not independently distinct")
    return verified


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", choices=tuple(REGIONS), required=True)
    args = parser.parse_args()
    try:
        records = asyncio.run(check_region(args.region))
        print("RU_NC_ORIGINALS=" + str(len(records)))
        print("RU_NC_" + args.region.upper() + "=PASS_RESEARCH_ONLY")
        return 0 if len(records) == REQUIRED_ORIGINALS else 2
    except (ValueError, ConnectorTransportError, httpx.HTTPError, OSError,
            TimeoutError) as exc:
        print("RU_NC_" + args.region.upper() + "=BLOCKED_" + type(exc).__name__)
        if isinstance(exc, ConnectorTransportError):
            print("RU_NC_RETRYABLE=" + str(exc.retryable))
        return 2
    finally:
        print("PRODUCTION_CHANGED=NO")


if __name__ == "__main__":
    raise SystemExit(main())
