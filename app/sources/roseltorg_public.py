"""Opt-in read-only Roseltorg public procedure adapter.

Do not infer 44-FZ/223-FZ classification, prices, dates or buyers from a heading.
A notice is returned only after same-host listing discovery and independent
official detail validation. No credentials, redirects, TLS exceptions or proxy.
"""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from html.parser import HTMLParser
import math
import re
from urllib.parse import urljoin, urlsplit

import httpx

from .http import FetchPolicy, bounded_fetch, _policy, source_client
from .models import TenderNotice
from .opportunities import validate_notice

SOURCE_ID = "roseltorg_public"
HOST = "www.roseltorg.ru"
LIST_URL = f"https://{HOST}/procedures/search"
MAX_BYTES = 1_800_000
MAX_DETAILS = 3
DETAIL_PATH = re.compile(r"/procedure/([A-Z0-9]{8,24})/1/?")


def _html(payload):
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_BYTES or b"\x00" in payload:
        raise ValueError("Invalid Roseltorg public HTML")
    return payload.decode("utf-8-sig", "replace")


def _canonical(raw):
    if (type(raw) is not str or not raw or len(raw) > 1500
            or chr(92) in raw or "%" in raw
            or any(c.isspace() or ord(c) < 32 for c in raw)):
        return None
    try:
        parsed = urlsplit(urljoin(LIST_URL, raw))
        match = DETAIL_PATH.fullmatch(parsed.path)
        if (not match or parsed.scheme != "https" or parsed.netloc != HOST
                or parsed.query or parsed.fragment or parsed.username or parsed.password
                or parsed.port is not None):
            return None
        return match.group(1), parsed.geturl()
    except ValueError:
        return None


class _Listing(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


class _Detail(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.headings = []
        self.current_heading = None
        self.visible = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "noscript", "svg"}:
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
        if tag in {"script", "style", "template", "noscript", "svg"} and self.hidden:
            self.hidden -= 1


def parse_roseltorg_links(payload, *, limit=MAX_DETAILS):
    if type(limit) is not int or not 1 <= limit <= MAX_DETAILS:
        raise ValueError("Invalid Roseltorg listing bound")
    listing = _Listing()
    listing.feed(_html(payload))
    listing.close()
    found, seen = [], {}
    for href in listing.links:
        record = _canonical(href)
        if record is None:
            continue
        identity, url = record
        if identity in seen:
            if seen[identity] != url:
                raise ValueError("Conflicting Roseltorg listing identity")
            continue
        seen[identity] = url
        found.append(record)
        if len(found) == limit:
            break
    if not found:
        raise ValueError("No independently discoverable public Roseltorg procedures")
    return found


def parse_roseltorg_detail(payload, *, identity, url):
    if type(identity) is not str:
        raise ValueError("Invalid Roseltorg identity")
    canonical = _canonical(url)
    if canonical != (identity, url):
        raise ValueError("Noncanonical Roseltorg detail URL")
    detail = _Detail()
    detail.feed(_html(payload))
    detail.close()
    visible = " ".join(" ".join(detail.visible).split())
    # Verified against the official public Roseltorg detail (RU3 live).
    # The same exact procedure ID must occur twice in the visible breadcrumb:
    # "Закупки <ID> Лот <number> <ID>". Arbitrary scripts/sidebar IDs are unsafe.
    breadcrumb = (r"Закупки\s+" + re.escape(identity) + r"\s+Лот\s+[0-9]{1,5}\s+"
                  + re.escape(identity) + r"(?![A-Z0-9])")
    if not re.search(breadcrumb, visible):
        raise ValueError("Official Roseltorg detail breadcrumb identity mismatch")
    titles = [name for name in detail.headings if 5 <= len(name) <= 1000]
    if len(titles) != 1:
        raise ValueError("Roseltorg official detail title is ambiguous")
    notice = TenderNotice(source=SOURCE_ID, external_id=identity, title=titles[0], url=url)
    validate_notice(notice, SOURCE_ID)
    return notice


@dataclass(frozen=True)
class RoseltorgPublicSource:
    timeout: float = 20
    name: str = SOURCE_ID

    def __post_init__(self):
        if (self.name != SOURCE_ID or type(self.timeout) not in (int, float)
                or not math.isfinite(self.timeout) or not 0 < self.timeout <= 30):
            raise ValueError("Invalid Roseltorg source configuration")

    async def fetch(self, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid Roseltorg source limit")
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
                    raise ValueError("Roseltorg listing is not public HTML")
                links = parse_roseltorg_links(listing.content, limit=cap)
                notices = []
                for identity, url in links:
                    try:
                        res = await client.get(url)
                        res.raise_for_status()
                        if "html" not in res.headers.get("content-type", "").lower():
                            raise ValueError("Roseltorg detail is not public HTML")
                        notices.append(parse_roseltorg_detail(res.content, identity=identity, url=url))
                    except (ValueError, httpx.HTTPStatusError):
                        continue
                if not notices:
                    raise ValueError("No independently verified Roseltorg public notices")
                return notices
