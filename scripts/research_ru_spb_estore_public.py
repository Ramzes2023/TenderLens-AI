"""Official Saint Petersburg electronic shop: first-party public small purchases.

Read-only discovery requiring real registry links and independent details.
No auth/cookies, fallback fixtures, arbitrary host, redirects or TLS bypass.
"""
from __future__ import annotations

import asyncio
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit

import httpx
from app.sources.http import FetchPolicy, bounded_fetch, source_client, ConnectorTransportError

HOST = "estore.gz-spb.ru"
INDEX = "https://estore.gz-spb.ru/electronicshop/catalog/procedure/"
BYTES = 2_000_000
LIMIT = 2
DETAIL = re.compile(r"/electronicshop/procedure/form/view/([0-9]{5,8})/?\Z")
NUMBER = re.compile(r"20[0-9]{11}\Z")


def cleaned(value):
    return " ".join(value.split())


class PublicHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.visible, self.headings = [], [], []
        self.row = None
        self.cell = self.heading = self.anchor = None
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "svg", "template", "noscript", "iframe"}:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag == "tr":
            self.row = {"cells": [], "links": []}
        if tag in ("td", "th") and self.row is not None:
            self.cell = []
        if tag == "a":
            self.anchor = [dict(attrs).get("href"), []]
        if tag in ("h1", "h2"):
            self.heading = []

    def handle_data(self, text):
        if self.hidden:
            return
        self.visible.append(text)
        for item in (self.cell, self.anchor[1] if self.anchor is not None else None, self.heading):
            if item is not None:
                item.append(text)

    def handle_endtag(self, tag):
        if self.hidden:
            if self.hidden[-1] == tag:
                self.hidden.pop()
            return
        if tag == "a" and self.anchor is not None:
            href, pieces = self.anchor
            if self.row is not None:
                self.row["links"].append((href, cleaned(" ".join(pieces))))
            self.anchor = None
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row["cells"].append(cleaned(" ".join(self.cell)))
            self.cell = None
        if tag in ("h1", "h2") and self.heading is not None:
            self.headings.append(cleaned(" ".join(self.heading)))
            self.heading = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def doc(body):
    if type(body) is not bytes or not 0 < len(body) <= BYTES or b"\0" in body:
        raise ValueError("Empty or oversized official public HTML")
    result = PublicHTML()
    result.feed(body.decode("utf-8-sig", "replace"))
    result.close()
    return result


def canonical(href):
    if (type(href) is not str or not 0 < len(href) <= 400
            or "\\" in href or any(ch.isspace() or ord(ch) < 32 for ch in href)):
        return None
    try:
        u = urlsplit(urljoin(INDEX, href))
        match = DETAIL.fullmatch(u.path)
        if (u.scheme != "https" or u.netloc != HOST or u.username is not None
                or u.password is not None or u.port is not None or u.query or u.fragment
                or match is None):
            return None
        return INDEX.replace("/catalog/procedure/", "/procedure/form/view/") + match.group(1) + "/"
    except ValueError:
        return None


def listing(body):
    parsed = doc(body)
    cards = []
    seen = set()
    for row in parsed.rows:
        numbers = {cell for cell in row["cells"] if NUMBER.fullmatch(cell)}
        if len(numbers) != 1:
            continue
        num = next(iter(numbers))
        for href, anchor_title in row["links"]:
            target = canonical(href)
            if target is None or target in seen:
                continue
            title = anchor_title.strip()
            if not 8 <= len(title) <= 500 or not re.search(r"[А-Яа-яЁё]", title):
                continue
            seen.add(target)
            cards.append((num, title, target))
            break
    if len(cards) < LIMIT or len({x[0] for x in cards}) < LIMIT:
        raise ValueError("Two distinct public official store purchases not indexed")
    return cards[:LIMIT]


def validate_detail(body, number, title, url):
    if canonical(url) != url or not NUMBER.fullmatch(number):
        raise ValueError("Noncanonical Saint Petersburg shop identity")
    parsed = doc(body)
    visible = cleaned(" ".join(parsed.visible))
    if number not in visible:
        raise ValueError("Official notice number missing in independently fetched page")
    if not re.search(r"Объект закупки\s*:?\s*" + re.escape(title) + r"(?:\s|$)", visible, re.I):
        raise ValueError("Official procurement object different from public registry")
    return (number, title, url)


async def probe():
    with bounded_fetch(FetchPolicy(frozenset({HOST}), LIMIT+1, max_bytes=BYTES)):
        async with source_client(timeout=25, trust_env=False, follow_redirects=False,
            headers={"Accept":"text/html","User-Agent":"Mozilla/5.0"}) as client:
            page = await client.get(INDEX)
            page.raise_for_status()
            if "html" not in page.headers.get("content-type", "").lower():
                raise ValueError("Public registry not HTML")
            selected = listing(page.content)
            verified = []
            for number, title, url in selected:
                detail = await client.get(url)
                detail.raise_for_status()
                if "html" not in detail.headers.get("content-type", "").lower():
                    raise ValueError("Official detail not HTML")
                verified.append(validate_detail(detail.content, number, title, url))
            return verified


def main():
    try:
        records = asyncio.run(probe())
        print("RU_SPB_ESTORE_REAL_INDEPENDENT_DETAILS=" + str(len(records)))
        print("RU_SPB_ESTORE_DISCOVERY=PASS_RESEARCH_ONLY")
        print("PRODUCTION_CHANGED=NO")
        return 0 if len(records) == LIMIT else 2
    except (ValueError, ConnectorTransportError, httpx.HTTPError, OSError, TimeoutError) as error:
        print("RU_SPB_ESTORE_DISCOVERY=BLOCKED_" + type(error).__name__)
        if isinstance(error, ConnectorTransportError):
            print("RU_SPB_ESTORE_RETRYABLE=" + str(error.retryable))
        print("PRODUCTION_CHANGED=NO")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
