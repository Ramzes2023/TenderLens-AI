"""Opt-in *accredited EIS mirror* for Ingushetia committee 44-FZ purchases.

The public vendor catalogue is NOT a second independent publisher. Every
published record must have an actual current list row PLUS an independently
fetched official detail H1, matching title, organizer and exact INN.
The targeted query is unverified until a real live CI worker proves results.
"""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from html.parser import HTMLParser
import math
import re
from urllib.parse import urlsplit

from .http import FetchPolicy, _policy, bounded_fetch, source_client
from .models import TenderNotice
from .opportunities import validate_notice

SOURCE_ID = "ru_ingushetia_fabrikant44"
REGION = "Республика Ингушетия"
ORGANIZER = "КОМИТЕТ ГОСУДАРСТВЕННОГО ЗАКАЗА РЕСПУБЛИКИ ИНГУШЕТИЯ"
INN = "0608058533"
HOST = "44.fabrikant.ru"
# This q filter exists in the indexed first-party search UI, but whether it
# filters organizer by INN MUST be established on the live first-party server.
LIST_URL = "https://44.fabrikant.ru/44/catalog/procedure?q=" + INN
_DETAIL = re.compile(r"/44/procedure/([a-z0-9-]{2,18})/([0-9]{19})\Z")
MAX_BYTES = 1_800_000
MAX_DETAILS = 5


def _text(chunks):
    return " ".join(" ".join(chunks).split())


def canonical_detail(raw):
    if (type(raw) is not str or not raw or len(raw) > 1500
            or "\\" in raw or any(ch.isspace() or ord(ch) < 32 for ch in raw)):
        return None
    try:
        p = urlsplit(raw)
        match = _DETAIL.fullmatch(p.path)
        if (not match or p.scheme != "https" or p.netloc != HOST
                or p.fragment or p.query or p.username or p.password or p.port is not None):
            return None
        return match.group(2), raw
    except ValueError:
        return None


class _TableRows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = {"cells": [], "links": []}
        elif self.row is not None and tag == "td":
            self.cell = []
        elif self.row is not None and tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.row["links"].append(href)

    def handle_data(self, value):
        if self.cell is not None:
            self.cell.append(value)

    def handle_endtag(self, tag):
        if tag == "td" and self.row is not None and self.cell is not None:
            self.row["cells"].append(_text(self.cell))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def extract_regional_listing(payload):
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_BYTES or b"\x00" in payload:
        raise ValueError("Untrusted Fabrikant regional listing")
    parser = _TableRows()
    parser.feed(payload.decode("utf-8-sig", "replace"))
    parser.close()
    found = []
    seen = set()
    for row in parser.rows:
        cells = row["cells"]
        if len(cells) < 6:
            continue
        # The first-party 44-FZ listing schema is Type | Number | Title |
        # Price | Organizer | Customer ... . Query-string filters alone are
        # never regional evidence: the organizer must actually match the row.
        organizer = cells[4].upper()
        if ORGANIZER not in organizer:
            continue
        title = cells[2]
        if not 5 <= len(title) <= 1000:
            continue
        identities = []
        for raw in row["links"]:
            # Official list may carry navigation-only backurl. Strip the
            # navigation parameter, never send it in subsequent GET requests.
            if not raw.startswith("https://" + HOST + "/44/procedure/"):
                continue
            p = urlsplit(raw)
            original = canonical_detail("https://" + HOST + p.path)
            if original is not None:
                identities.append(original)
        identities = list(dict.fromkeys(identities))
        if len(identities) != 1:
            continue
        number, url = identities[0]
        if number not in cells[1] or number in seen:
            continue
        seen.add(number)
        found.append((number, url, title))
        if len(found) >= MAX_DETAILS:
            break
    if not found:
        raise ValueError("No source-owned Ingushetia committee tenders in live Fabrikant list")
    return found


class _Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.h1 = None
        self.headings = []
        self.content = []
    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "template", "svg"}:
            self.hidden += 1
        elif tag == "h1" and not self.hidden:
            self.h1 = []
    def handle_data(self, value):
        if not self.hidden:
            self.content.append(value)
            if self.h1 is not None:
                self.h1.append(value)
    def handle_endtag(self, tag):
        if tag == "h1" and self.h1 is not None:
            self.headings.append(_text(self.h1))
            self.h1 = None
        elif tag in {"script", "style", "noscript", "template", "svg"} and self.hidden:
            self.hidden -= 1


def verified_fabrikant_notice(payload, *, number, url, title):
    if canonical_detail(url) != (number, url):
        raise ValueError("Noncanonical Fabrikant procurement original")
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_BYTES or b"\x00" in payload:
        raise ValueError("Invalid official first-party card HTML")
    reader = _Visible()
    reader.feed(payload.decode("utf-8-sig", "replace"))
    reader.close()
    body = _text(reader.content).upper()
    if (reader.headings != ["Сведения о закупке " + number]
            or title.upper() not in body
            or ORGANIZER not in body
            or INN not in body):
        raise ValueError("Independent original detail fails Ingushetia publisher/identity/title checks")
    notice = TenderNotice(
        source=SOURCE_ID, external_id=number, tender_number=number,
        title=title, url=url, customer=ORGANIZER, region=REGION,
    )
    validate_notice(notice, SOURCE_ID)
    return notice


@dataclass(frozen=True)
class IngushetiaFabrikant44Source:
    timeout: float = 25.0
    name: str = SOURCE_ID

    def __post_init__(self):
        if (self.name != SOURCE_ID or type(self.timeout) not in {float, int}
                or not math.isfinite(self.timeout) or not 0 < self.timeout <= 30):
            raise ValueError("Invalid Ingushetia Fabrikant source settings")

    async def fetch(self, limit: int = 20) -> list[TenderNotice]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid Ingushetia Fabrikant limit")
        cap = min(MAX_DETAILS, limit)
        policy = (bounded_fetch(FetchPolicy(frozenset({HOST}), MAX_DETAILS + 1,
                                         max_bytes=MAX_BYTES))
                  if _policy.get() is None else nullcontext())
        with policy:
            async with source_client(
                timeout=self.timeout, follow_redirects=False, trust_env=False,
                headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
            ) as client:
                listing = await client.get(LIST_URL)
                listing.raise_for_status()
                if "html" not in listing.headers.get("content-type", "").lower():
                    raise ValueError("First-party regional listing was not HTML")
                candidates = extract_regional_listing(listing.content)
                valid = []
                for number, url, title in candidates:
                    card = await client.get(url)
                    card.raise_for_status()
                    if "html" not in card.headers.get("content-type", "").lower():
                        raise ValueError("First-party original card was not HTML")
                    valid.append(verified_fabrikant_notice(
                        card.content, number=number, url=url, title=title,
                    ))
                    if len(valid) >= cap:
                        break
                if not valid:
                    raise ValueError("No independently verified regional original cards")
                return valid
