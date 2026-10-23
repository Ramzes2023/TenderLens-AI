"""Leningrad Oblast official small-purchase requests, read-only public HTML.

A candidate is accepted only when discovered via /Search/NewRequests and its
individual exact-host detail shows the same numeric request-group ID and a
strong lexical corroboration of the listing's title in the official H1.
No guessed tender law, EIS regNumber, prices, buyer or deadline.
"""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from html.parser import HTMLParser
import math
import re
from urllib.parse import urljoin, urlsplit

import httpx

from .http import FetchPolicy, _policy, bounded_fetch, source_client
from .models import TenderNotice
from .opportunities import validate_notice

SOURCE_ID = "lenobl_small_public"
HOST = "zakupki.lenreg.ru"
LIST_URL = "https://" + HOST + "/Search/NewRequests"
MAX_BYTES = 1_200_000
MAX_DETAILS = 3
DETAIL_PATH = re.compile(r"/ProductRequestGroup/Index/([0-9]{4,16})/?")


def _html(payload):
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_BYTES or b"\x00" in payload:
        raise ValueError("Invalid official Lenobl procurement HTML")
    return payload.decode("utf-8-sig", "replace")


def _canonical(raw):
    if type(raw) is not str or not 0 < len(raw) <= 1400 or "\\" in raw:
        return None
    try:
        p = urlsplit(urljoin(LIST_URL, raw))
        match = DETAIL_PATH.fullmatch(p.path)
        if (not match or p.scheme != "https" or p.netloc != HOST or p.port is not None
                or p.username is not None or p.password is not None
                or p.query or p.fragment or any(ord(ch) < 32 or ch.isspace() for ch in raw)):
            return None
        return match.group(1), "https://" + HOST + p.path
    except ValueError:
        return None


class _Listing(HTMLParser):
    # An official procurement candidate must be a visible list link, not a
    # prototype anchor nested in head, scripts, styles, or HTML templates.
    _HIDDEN = frozenset({"head", "script", "style", "svg", "iframe",
                         "object", "template", "noscript"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.current = None
        self.links = []
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if self.current is not None:
            if tag in self._HIDDEN:
                raise ValueError("Active markup in Lenobl tender listing card")
            return
        if tag in self._HIDDEN:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.current = [href, []]

    def handle_data(self, data):
        if self.current is not None and not self.hidden:
            self.current[1].append(data)

    def handle_endtag(self, tag):
        if self.hidden:
            if self.hidden[-1] == tag:
                self.hidden.pop()
            return
        if tag == "a" and self.current is not None:
            href, words = self.current
            self.links.append((href, " ".join(" ".join(words).split())))
            self.current = None


class _Detail(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.current_heading = None
        self.headings = []
        self.visible = []

    def handle_starttag(self, tag, attrs):
        if tag in {"head", "title", "script", "style", "template", "noscript", "svg"}:
            self.hidden += 1
        if not self.hidden and tag == "h1" and self.current_heading is None:
            self.current_heading = []

    def handle_data(self, data):
        if not self.hidden:
            self.visible.append(data)
            if self.current_heading is not None:
                self.current_heading.append(data)

    def handle_endtag(self, tag):
        if tag == "h1" and self.current_heading is not None:
            self.headings.append(" ".join(" ".join(self.current_heading).split()))
            self.current_heading = None
        if tag in {"head", "title", "script", "style", "template", "noscript", "svg"} and self.hidden:
            self.hidden -= 1


def _tokens(value):
    return set(re.findall(r"[А-Яа-яЁёA-Za-z0-9]{3,}", value.lower()))


def parse_lenobl_listing(payload, *, limit=MAX_DETAILS):
    if type(limit) is not int or not 1 <= limit <= MAX_DETAILS:
        raise ValueError("Invalid Lenobl listing limit")
    reader = _Listing()
    reader.feed(_html(payload))
    reader.close()
    records, unique = [], {}
    for href, title in reader.links:
        result = _canonical(href)
        if result is None:
            continue
        identity, url = result
        if not 5 <= len(title) <= 1000 or "\x00" in title or re.search(r"<\s*/?\s*[a-zA-Z][^>]*>", title):
            raise ValueError("Invalid Lenobl listing title")
        if identity in unique:
            if unique[identity] != (url, title):
                raise ValueError("Conflicting public Lenobl request identity")
            continue
        unique[identity] = (url, title)
        records.append((identity, url, title))
        if len(records) >= limit:
            break
    if not records:
        raise ValueError("No public Lenobl procurement request cards")
    return records


def parse_lenobl_detail(payload, *, identity, url, listing_title):
    if (type(identity) is not str or type(url) is not str
            or _canonical(url) != (identity, url) or type(listing_title) is not str
            or not 5 <= len(listing_title) <= 1000):
        raise ValueError("Noncanonical Lenobl tender detail request")
    detail = _Detail()
    detail.feed(_html(payload))
    detail.close()
    visible = " ".join(" ".join(detail.visible).split())
    if not re.search(r"(?<![0-9])" + re.escape(identity) + r"(?![0-9])", visible):
        raise ValueError("Lenobl official request-group ID not visible on detail")
    if len(detail.headings) != 1 or not 5 <= len(detail.headings[0]) <= 1000:
        raise ValueError("Lenobl official detail heading unavailable")
    heading = detail.headings[0]
    listed, actual = _tokens(listing_title), _tokens(heading)
    if len(listed) < 2 or len(listed & actual) / len(listed) < 0.75:
        raise ValueError("Lenobl official listing/detail titles do not corroborate")
    notice = TenderNotice(source=SOURCE_ID, external_id=identity, title=heading, url=url)
    validate_notice(notice, SOURCE_ID)
    return notice


@dataclass(frozen=True)
class LenoblSmallPublicSource:
    timeout: float = 20
    name: str = SOURCE_ID

    def __post_init__(self):
        if (self.name != SOURCE_ID or type(self.timeout) not in (int, float)
                or not math.isfinite(self.timeout) or not 0 < self.timeout <= 30):
            raise ValueError("Invalid Lenobl source configuration")

    async def fetch(self, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid Lenobl source limit")
        cap = min(limit, MAX_DETAILS)
        policy = (bounded_fetch(FetchPolicy(frozenset({HOST}), cap + 1,
                                             max_bytes=MAX_BYTES))
                  if _policy.get() is None else nullcontext())
        with policy:
            async with source_client(
                timeout=self.timeout, trust_env=False, follow_redirects=False,
                headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
            ) as client:
                listing = await client.get(LIST_URL)
                listing.raise_for_status()
                if "html" not in listing.headers.get("content-type", "").lower():
                    raise ValueError("Lenobl official listing is not public HTML")
                items = parse_lenobl_listing(listing.content, limit=cap)
                verified = []
                for identity, url, title in items:
                    try:
                        page = await client.get(url)
                        page.raise_for_status()
                        if "html" not in page.headers.get("content-type", "").lower():
                            raise ValueError("Lenobl official detail is not HTML")
                        verified.append(parse_lenobl_detail(
                            page.content, identity=identity, url=url, listing_title=title,
                        ))
                    except (ValueError, httpx.HTTPStatusError):
                        continue
                if not verified:
                    raise ValueError("No independently verified Lenobl public tenders")
                return verified
