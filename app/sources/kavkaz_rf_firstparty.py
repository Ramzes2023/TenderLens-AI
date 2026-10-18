"""First-party AO Kavkaz.RF Northern Caucasus procurement notices.

Research-gated independent originals; EIS/Fabrikant cross-posts are not new
procurement opportunities and need upstream dedup before broad activation.
No account, cookies, proxy, redirect, TLS bypass, or synthetic live fallback.
"""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
import math
import re
from urllib.parse import urljoin, urlsplit

import httpx

from .http import FetchPolicy, _policy, bounded_fetch, source_client
from .models import TenderNotice
from .opportunities import validate_notice

SOURCE_ID = "kavkaz_rf_firstparty"
HOST = "xn--80aafvlc.xn--p1ai"
LIST_URL = "https://" + HOST + "/purchases_sales/zakupki/tekushchie-/"
MAX_BYTES = 1_800_000
MAX_DETAILS = 2
NATIVE_NUMBER = re.compile(r"[А-ЯЁA-Z]{1,5}-[А-ЯЁA-Z]{2,8}-[0-9]{2,6}[А-ЯЁA-Z]{0,3}\Z")
DETAIL_PATH = re.compile(
    r"/purchases_sales/zakupki/tekushchie-/[a-z0-9-]+/[a-z0-9_%\-]+/\Z"
)


def _norm(value):
    return " ".join(str(value).split())


class _Doc(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.cell = None
        self.anchor = None
        self.heading = None
        self.headings = []
        self.visible = []
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "svg", "template", "noscript", "iframe"}:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag == "tr":
            self.row = {"cells": [], "links": []}
        if tag in {"td", "th"} and self.row is not None:
            self.cell = []
        if tag == "a" and self.row is not None:
            self.anchor = [dict(attrs).get("href"), []]
        if tag in {"h1", "h2"} and self.heading is None:
            self.heading = []

    def handle_data(self, data):
        if self.hidden:
            return
        self.visible.append(data)
        if self.cell is not None:
            self.cell.append(data)
        if self.anchor is not None:
            self.anchor[1].append(data)
        if self.heading is not None:
            self.heading.append(data)

    def handle_endtag(self, tag):
        if self.hidden:
            if self.hidden[-1] == tag:
                self.hidden.pop()
            return
        if tag == "a" and self.anchor is not None:
            href, words = self.anchor
            if self.row is not None:
                self.row["links"].append((href, _norm(" ".join(words))))
            self.anchor = None
        if tag in {"td", "th"} and self.cell is not None and self.row is not None:
            self.row["cells"].append(_norm(" ".join(self.cell)))
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        if tag in {"h1", "h2"} and self.heading is not None:
            self.headings.append(_norm(" ".join(self.heading)))
            self.heading = None


def _parse_html(data):
    if type(data) is not bytes or not 0 < len(data) <= MAX_BYTES or b"\x00" in data:
        raise ValueError("Unsafe first-party procurement HTML")
    doc = _Doc()
    doc.feed(data.decode("utf-8-sig", "replace"))
    doc.close()
    return doc


def _canonical(href):
    if (type(href) is not str or not 0 < len(href) <= 1300 or "\\" in href
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in href)):
        return None
    try:
        url = urlsplit(urljoin(LIST_URL, href))
        if (url.scheme != "https" or url.netloc != HOST or url.port is not None
                or url.username or url.password or url.fragment or url.query
                or not DETAIL_PATH.fullmatch(url.path)
                or re.search(r"%(?:2f|5c|2e|00)", url.path, re.I)):
            return None
        return url.geturl()
    except ValueError:
        return None


def parse_listing(data, *, limit=MAX_DETAILS):
    if type(limit) is not int or not 1 <= limit <= MAX_DETAILS:
        raise ValueError("Invalid first-party listing limit")
    doc = _parse_html(data)
    results, seen = [], {}
    for row in doc.rows:
        if not row["cells"] or len(row["cells"]) < 3:
            continue
        number = row["cells"][0]
        if not NATIVE_NUMBER.fullmatch(number):
            continue
        matches = [
            (title, url)
            for href, title in row["links"]
            if (url := _canonical(href)) is not None and 12 <= len(title) <= 1000
        ]
        if len(matches) != 1:
            raise ValueError("Ambiguous original Kavkaz.RF detail link")
        title, url = matches[0]
        if number in seen:
            if seen[number] != (title, url):
                raise ValueError("Conflicting Kavkaz.RF native notice number")
            continue
        seen[number] = (title, url)
        results.append((number, title, url))
        if len(results) == limit:
            break
    if not results:
        raise ValueError("No source-owned current Kavkaz.RF procurement notices")
    return results


def parse_detail(data, *, number, title, url):
    if (type(number) is not str or not NATIVE_NUMBER.fullmatch(number)
            or type(title) is not str or not 12 <= len(title) <= 1000
            or _canonical(url) != url):
        raise ValueError("Invalid independent procurement detail request")
    doc = _parse_html(data)
    headings = [item for item in doc.headings if item]
    if len(headings) != 1:
        raise ValueError("Unambiguous first-party procurement heading missing")
    real_title = headings[0]
    if not (real_title.casefold() == title.casefold()
            or (len(title) >= 40 and real_title.casefold().startswith(title.casefold()))):
        raise ValueError("Kavkaz.RF listing and detail title mismatch")
    visible = _norm(" ".join(doc.visible))
    if not re.search(r"№\s*извещения\s*:\s*" + re.escape(number) + r"(?![0-9А-ЯЁA-Z])", visible, re.I):
        raise ValueError("Kavkaz.RF native notice number absent from original detail")
    price_match = re.search(
        r"начальная\s*\(максимальная\)\s*цена\s*договора\s*:\s*"
        r"([0-9]{1,3}(?:\s+[0-9]{3})*,[0-9]{2})",
        visible, re.I,
    )
    if not price_match:
        raise ValueError("Kavkaz.RF original initial price missing")
    amount = float(price_match.group(1).replace(" ", "").replace(",", "."))
    pub = re.search(r"дата\s+опубликования\s*:\s*(\d{2}\.\d{2}\.\d{4})", visible, re.I)
    if not pub:
        raise ValueError("Kavkaz.RF original publication date missing")
    published = datetime.strptime(pub.group(1), "%d.%m.%Y").date().isoformat()
    due = re.search(r"при[её]м\s+заявок\s+до\s*(\d{2}\.\d{2}\.\d{4})", visible, re.I)
    deadline = (datetime.strptime(due.group(1), "%d.%m.%Y").date().isoformat()
                if due else None)
    notice = TenderNotice(
        source=SOURCE_ID,
        external_id=number,
        tender_number=number,
        title=real_title,
        url=url,
        published_at=published,
        deadline=deadline,
        customer="АО «КАВКАЗ.РФ»",
        initial_price=amount,
        currency="RUB",
        region="Северный Кавказ",
    )
    validate_notice(notice, SOURCE_ID)
    return notice


@dataclass(frozen=True)
class KavkazRfFirstpartySource:
    timeout: float = 25
    name: str = SOURCE_ID

    def __post_init__(self):
        if (self.name != SOURCE_ID or type(self.timeout) not in (int, float)
                or not math.isfinite(self.timeout) or not 0 < self.timeout <= 30):
            raise ValueError("Invalid first-party procurement source configuration")

    async def fetch(self, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid original procurement source limit")
        cap = min(limit, MAX_DETAILS)
        policy = (bounded_fetch(FetchPolicy(frozenset({HOST}), cap + 1, max_bytes=MAX_BYTES))
                  if _policy.get() is None else nullcontext())
        with policy:
            async with source_client(
                timeout=self.timeout, follow_redirects=False, trust_env=False,
                headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
            ) as client:
                index = await client.get(LIST_URL)
                index.raise_for_status()
                if "html" not in index.headers.get("content-type", "").lower():
                    raise ValueError("Kavkaz.RF public procurement index is not HTML")
                rows = parse_listing(index.content, limit=cap)
                result = []
                for number, title, url in rows:
                    detail = await client.get(url)
                    detail.raise_for_status()
                    if "html" not in detail.headers.get("content-type", "").lower():
                        raise ValueError("Kavkaz.RF original detail not HTML")
                    result.append(parse_detail(detail.content, number=number, title=title, url=url))
                if len({n.external_id for n in result}) != len(result):
                    raise ValueError("Duplicate Kavkaz.RF first-party tender identities")
                return result
