"""Murmansk regional small-purchase first-party list→details research.

No historic search hits/known detail URLs count as live inventory. At least two
original detail URLs must originate in a fresh *first-party registry* response.
This is RESEARCH ONLY: never enables a connector or writes production.
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

HOST = "gz-murman.ru"
INDEX = "https://gz-murman.ru/site/GzwSP/NoticesGrid"
DETAIL_PATH = "/site/GzwSP/Notice"
MAX_BYTES = 1_800_000
REQUIRED = 2
ID = re.compile(r"[0-9]{7,9}\Z")
NATIVE = re.compile(r"ИМЗ-20[0-9]{2}-[0-9]{6}\b")


def compact(s):
    return " ".join(s.split())


class Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.cell = None
        self.anchor = None
        self.visible = []
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "svg", "template", "noscript", "iframe"):
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag == "tr":
            self.row = {"cells": [], "links": []}
        if tag in ("td", "th") and self.row is not None:
            self.cell = []
        if tag == "a":
            self.anchor = [dict(attrs).get("href"), []]

    def handle_data(self, text):
        if self.hidden:
            return
        self.visible.append(text)
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
            if self.row is not None:
                self.row["links"].append(
                    (self.anchor[0], compact(" ".join(self.anchor[1])))
                )
            self.anchor = None
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row["cells"].append(compact(" ".join(self.cell)))
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def document(body):
    if type(body) is not bytes or not 0 < len(body) <= MAX_BYTES or b"\0" in body:
        raise ValueError("Untrusted Murmansk registry HTML")
    p = Visible()
    p.feed(body.decode("utf-8-sig", "replace"))
    p.close()
    return p


def canonical(href):
    if (type(href) is not str or not 0 < len(href) <= 400
            or "\\" in href or any(ch.isspace() or ord(ch) < 32 for ch in href)):
        return None
    try:
        parsed = urlsplit(urljoin(INDEX, href))
        query = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
        if (parsed.scheme != "https" or parsed.netloc != HOST or parsed.port is not None
                or parsed.username is not None or parsed.password is not None
                or parsed.fragment or parsed.path != DETAIL_PATH
                or len(query) != 1 or query[0][0] != "noticeLink"
                or not ID.fullmatch(query[0][1])):
            return None
        number = query[0][1]
        return number, "https://" + HOST + DETAIL_PATH + "?noticeLink=" + number
    except ValueError:
        return None


def listing(body):
    found, seen = [], set()
    parsed = document(body)
    for row in parsed.rows:
        native = set(NATIVE.findall(" ".join(row["cells"])))
        if len(native) != 1:
            continue
        notice_id = next(iter(native))
        for href, title in row["links"]:
            target = canonical(href)
            if target is None or target[0] in seen:
                continue
            # Require the visible original procurement subject from the row.
            if not 8 <= len(title) <= 600 or not re.search(r"[А-Яа-яЁё]", title):
                continue
            seen.add(target[0])
            found.append((target[0], notice_id, title, target[1]))
            break
    if len(found) < REQUIRED:
        raise ValueError("No two current independently linked Murmansk ZMO notices")
    return found[:REQUIRED]


def verify_detail(body, internal_id, native_id, title, url):
    if canonical(url) != (internal_id, url) or not NATIVE.fullmatch(native_id):
        raise ValueError("Murmansk detail identity not canonical")
    parsed = document(body)
    visible = compact(" ".join(parsed.visible))
    if not re.search(r"Номер и дата извещения\s+" + re.escape(native_id) + r"\b", visible):
        raise ValueError("Original Murmansk purchase number absent")
    if not re.search(r"Объект закупки\s+" + re.escape(title) + r"(?:\s|$)", visible, re.I):
        raise ValueError("Independent first-party Murmansk subject mismatch")
    if not re.search(r"Начальная \(максимальная\) цена закупки", visible):
        raise ValueError("Independent first-party price field missing")
    if not re.search(r"Заказчик\s+[^\s]", visible):
        raise ValueError("Independent first-party buyer missing")
    return native_id, title, url


async def live():
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 3, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=25, trust_env=False, follow_redirects=False,
            headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
        ) as client:
            response = await client.get(INDEX)
            response.raise_for_status()
            if "html" not in response.headers.get("content-type", "").lower():
                raise ValueError("Official Murmansk current registry not HTML")
            rows = listing(response.content)
            confirmed = []
            for internal_id, native_id, title, url in rows:
                detail = await client.get(url)
                detail.raise_for_status()
                if "html" not in detail.headers.get("content-type", "").lower():
                    raise ValueError("Original Murmansk detail not HTML")
                confirmed.append(verify_detail(detail.content, internal_id, native_id, title, url))
            if len({x[0] for x in confirmed}) != REQUIRED:
                raise ValueError("Murmansk first-party original IDs not independent")
            return confirmed


def main():
    try:
        notices = asyncio.run(live())
        print("RU_MURMANSK_GENUINE_FIRSTPARTY=" + str(len(notices)))
        print("RU_MURMANSK_ZMO=PASS_RESEARCH_ONLY")
        print("PRODUCTION_CHANGED=NO")
        return 0 if len(notices) == REQUIRED else 2
    except (ValueError, ConnectorTransportError, httpx.HTTPError, OSError, TimeoutError) as error:
        print("RU_MURMANSK_ZMO=BLOCKED_" + type(error).__name__)
        if isinstance(error, ConnectorTransportError):
            print("RU_MURMANSK_RETRYABLE=" + str(error.retryable))
        print("PRODUCTION_CHANGED=NO")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
