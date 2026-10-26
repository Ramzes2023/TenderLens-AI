"""Stavropol official small-purchase portal: fail-closed original-procurement proof.

Read-only research. No source registration, fixture-as-live, production writes,
login, redirects, proxies, TLS bypass or crawling arbitrary links.
"""
from __future__ import annotations
import asyncio
from html.parser import HTMLParser
import re
from urllib.parse import parse_qsl, urljoin, urlsplit

import httpx
from app.sources.http import (
    FetchPolicy, bounded_fetch, source_client, ConnectorTransportError,
)

HOST = "market26.rts-tender.ru"
INDEX = "https://" + HOST + "/"
MAX_BYTES = 1_800_000
REQUIRED = 2
NATIVE = re.compile(r"(?<!\d)(?:ИМЗ[-–]?)?[0-9]{2,4}[-/][0-9]{4,12}(?!\d)")


class PublicList(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.links = [], []
        self.row = self.cell = self.anchor = None
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "iframe", "svg", "noscript"}:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag == "tr":
            self.row = {"cells": [], "links": []}
        if tag in {"td", "th"} and self.row is not None:
            self.cell = []
        if tag == "a":
            self.anchor = [dict(attrs).get("href"), []]

    def handle_data(self, text):
        if self.hidden:
            return
        if self.cell is not None:
            self.cell.append(text)
        if self.anchor is not None:
            self.anchor[1].append(text)

    def handle_endtag(self, tag):
        if self.hidden:
            if self.hidden[-1] == tag:
                self.hidden.pop()
            return
        if tag == "a" and self.anchor is not None:
            pair = (self.anchor[0], " ".join(" ".join(self.anchor[1]).split()))
            self.links.append(pair)
            if self.row is not None:
                self.row["links"].append(pair)
            self.anchor = None
        if tag in {"td", "th"} and self.cell is not None and self.row is not None:
            self.row["cells"].append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def document(data):
    if type(data) is not bytes or not 0 < len(data) <= MAX_BYTES or b"\x00" in data:
        raise ValueError("Untrusted Stavropol registry HTML")
    doc = PublicList()
    doc.feed(data.decode("utf-8-sig", "replace"))
    doc.close()
    return doc


def canonical(href):
    if (type(href) is not str or not 0 < len(href) <= 400 or "\\" in href
            or any(c.isspace() or ord(c) < 32 for c in href)):
        return None
    try:
        part = urlsplit(urljoin(INDEX, href))
        args = parse_qsl(part.query, keep_blank_values=False, strict_parsing=True)
    except ValueError:
        return None
    if (part.scheme != "https" or part.netloc != HOST or part.username or part.password
            or part.port is not None or part.fragment or len(part.path) < 6
            or any(section in part.path.lower() for section in ("/login", "/auth", "/account"))
            or not re.fullmatch(r"/[A-Za-z0-9_./-]{5,220}", part.path)
            or len(args) > 1 or any(key.lower() not in {"id", "noticeid", "purchaseid"} or
                                     not re.fullmatch(r"[0-9]{4,15}", value)
                                     for key, value in args)):
        return None
    return part.geturl()


def current_cards(body):
    doc = document(body)
    print("RU_STAVROPOL_OFFICIAL_ROWS=" + str(len(doc.rows)))
    print("RU_STAVROPOL_OFFICIAL_ANCHORS=" + str(len(doc.links)))
    cards = []
    seen = set()
    for row in doc.rows:
        numbers = set()
        for cell in row["cells"]:
            numbers.update(NATIVE.findall(cell))
        if len(numbers) != 1:
            continue
        number = next(iter(numbers))
        for href, title in row["links"]:
            url = canonical(href)
            if not url or number in seen or not 8 <= len(title) <= 600:
                continue
            if not re.search("[А-Яа-яЁё]", title):
                continue
            seen.add(number)
            cards.append((number, title, url))
            break
    if len(cards) < REQUIRED:
        raise ValueError("Official Stavropol registry has no two current linked originals")
    return cards[:REQUIRED]


def verify_original(body, number, title, url):
    if canonical(url) != url or not NATIVE.fullmatch(number):
        raise ValueError("Unsafe original regional notice identity")
    visible = document(body)
    # Require independent first-party numbered detail, subject, buyer and price.
    text = " ".join(" ".join(visible.links[i][1] for i in range(len(visible.links))).split())
    # Links alone cannot prove a notice; visible table cells are authoritative.
    text += " " + " ".join(" ".join(row["cells"]) for row in visible.rows)
    normalized = " ".join(text.split())
    if (number not in normalized or title.casefold() not in normalized.casefold()
            or not re.search(r"заказчик", normalized, re.I)
            or not re.search(r"(?:цен[аы]|стоимост|НМЦК)", normalized, re.I)):
        raise ValueError("Unverified official Stavropol original notice detail")
    return number, title, url


async def research():
    with bounded_fetch(FetchPolicy(frozenset({HOST}), REQUIRED + 1, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=25, follow_redirects=False, trust_env=False,
            headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
        ) as client:
            listing = await client.get(INDEX)
            listing.raise_for_status()
            if "html" not in listing.headers.get("content-type", "").lower():
                raise ValueError("Stavropol official public registry not HTML")
            cards = current_cards(listing.content)
            proof = []
            for number, title, url in cards:
                detail = await client.get(url)
                detail.raise_for_status()
                if "html" not in detail.headers.get("content-type", "").lower():
                    raise ValueError("Stavropol original detail not HTML")
                proof.append(verify_original(detail.content, number, title, url))
            if len({n for n, _, _ in proof}) != REQUIRED:
                raise ValueError("Non-independent original Stavropol regional notices")
            return proof


def main():
    try:
        verified = asyncio.run(research())
        print("RU_STAVROPOL_REAL_ORIGINALS=" + str(len(verified)))
        print("RU_STAVROPOL_RESULT=PASS_RESEARCH_ONLY")
        return 0 if len(verified) == REQUIRED else 2
    except (ValueError, httpx.HTTPError, ConnectorTransportError, OSError,
            TimeoutError) as e:
        print("RU_STAVROPOL_RESULT=BLOCKED_" + type(e).__name__)
        if isinstance(e, ConnectorTransportError):
            print("RU_STAVROPOL_RETRYABLE=" + str(e.retryable))
        return 2
    finally:
        print("PRODUCTION_CHANGED=NO")


if __name__ == "__main__":
    raise SystemExit(main())
