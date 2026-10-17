"""Public first-party NMCK small-purchase source; strict independent detail evidence.

Only first-party entries are accepted. The public catalog also syndicates
external SPEСTENDER cards; NEVER count/copy those as native NMCK notices.
This probe proves list->detail identity only, NOT SQL/tenant integration.
"""
from __future__ import annotations
from dataclasses import dataclass
from contextlib import nullcontext
import math
import httpx

import asyncio
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit, parse_qsl

from .http import FetchPolicy, bounded_fetch, source_client, _policy
from .models import TenderNotice
from .opportunities import validate_notice

SOURCE_ID = "nmck_native_public"
HOST = "xn--j1adc1b.xn--p1ai"
LIST_URL = f"https://{HOST}/procedures"
MAX_BYTES = 1_800_000
SLUG = re.compile(r"[a-z0-9-]{6,140}-(\d{11})m")
NUMBER = re.compile(r"№\s*(\d{11})\s*[МM]")
MAX_DETAILS = 2


class PublicHtml(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self._current = None
        self.headings = []
        self._h1 = None
        self.visible = []
        self._hidden = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"style", "script", "svg", "template"}:
            self._hidden += 1
        if self._hidden:
            return
        if tag == "a":
            self._current = (attrs.get("href"), [])
        if tag == "h1":
            self._h1 = []

    def handle_data(self, data):
        if self._hidden:
            return
        self.visible.append(data)
        if self._current is not None:
            self._current[1].append(data)
        if self._h1 is not None:
            self._h1.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._current is not None:
            href, parts = self._current
            self.links.append((href, " ".join(" ".join(parts).split())))
            self._current = None
        if tag == "h1" and self._h1 is not None:
            self.headings.append(" ".join(" ".join(self._h1).split()))
            self._h1 = None
        if tag in {"style", "script", "svg", "template"} and self._hidden:
            self._hidden -= 1


def safe_slug(href: str):
    if type(href) is not str or not 0 < len(href) <= 500:
        return None
    if "\\" in href or any(ch.isspace() or ord(ch) < 32 for ch in href):
        return None
    try:
        p = urlsplit(urljoin(LIST_URL, href))
        if (p.scheme != "https" or p.netloc != HOST
                or p.username is not None or p.password is not None or p.port is not None
                or p.fragment or p.path.rstrip("/") != "/procedures"):
            return None
        q = parse_qsl(p.query, keep_blank_values=True)
        if len(q) != 1 or q[0][0] != "procedure":
            return None
        slug = q[0][1]
        return (slug, SLUG.fullmatch(slug).group(1)) if SLUG.fullmatch(slug) else None
    except ValueError:
        return None


def parse_list(data: bytes, *, limit=MAX_DETAILS):
    if type(data) is not bytes or not 0 < len(data) <= MAX_BYTES or b"\0" in data:
        raise ValueError("Invalid native NMCK listing")
    page = PublicHtml()
    page.feed(data.decode("utf-8-sig", "replace"))
    page.close()
    found, ids = [], set()
    for href, title in page.links:
        parsed = safe_slug(href)
        if parsed is None or not 5 <= len(title) <= 260:
            continue
        slug, num = parsed
        if num in ids:
            continue
        ids.add(num)
        # Rebuild a canonical, fixed-host official URL, NEVER follow the source href.
        found.append((slug, num, title, LIST_URL + "?procedure=" + slug))
        if len(found) >= limit:
            break
    if len(found) < limit:
        raise ValueError("Insufficient independently identifiable native NMCK notices")
    return found


def verify_detail(data: bytes, *, slug: str, identity: str, title: str):
    if type(data) is not bytes or not 0 < len(data) <= MAX_BYTES or b"\0" in data:
        raise ValueError("Invalid native NMCK detail")
    match = SLUG.fullmatch(slug)
    if match is None or identity != match.group(1):
        raise ValueError("Native NMCK detail identity malformed")
    doc = PublicHtml()
    doc.feed(data.decode("utf-8-sig", "replace"))
    doc.close()
    headings = [s for s in doc.headings if s]
    if len(headings) != 1 or not headings[0].casefold().startswith(title.casefold()):
        raise ValueError("Independent native NMCK detail title mismatch")
    # NMCK detail must display the same procurement number encoded in the
    # first-party slug. A matching title alone is not enough.
    visible = " ".join(" ".join(doc.visible).split())
    numbers = NUMBER.findall(visible)
    if identity not in numbers:
        raise ValueError("Independent native NMCK procurement number mismatch")
    return {"identity": identity, "title": headings[0], "title_confirmed": True, "number_confirmed": True}



@dataclass(frozen=True)
class NmckNativePublicSource:
    timeout: float = 20
    name: str = SOURCE_ID

    def __post_init__(self):
        if (self.name != SOURCE_ID or type(self.timeout) not in (int, float)
                or not math.isfinite(self.timeout) or not 0 < self.timeout <= 30):
            raise ValueError("Invalid NMCK source configuration")

    async def fetch(self, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid NMCK record limit")
        cap = min(limit, MAX_DETAILS)
        ctx = (bounded_fetch(FetchPolicy(frozenset({HOST}), cap + 1, max_bytes=MAX_BYTES))
               if _policy.get() is None else nullcontext())
        with ctx:
            async with source_client(
                timeout=self.timeout, trust_env=False, follow_redirects=False,
                headers={"Accept":"text/html","User-Agent":"Mozilla/5.0"},
            ) as client:
                listing = await client.get(LIST_URL)
                listing.raise_for_status()
                if "html" not in listing.headers.get("content-type", "").lower():
                    raise ValueError("NMCK listing is not public HTML")
                entries = parse_list(listing.content, limit=cap)
                verified = []
                for slug, identity, title, url in entries:
                    try:
                        detail = await client.get(url)
                        detail.raise_for_status()
                        if "html" not in detail.headers.get("content-type", "").lower():
                            raise ValueError("NMCK detail is not public HTML")
                        match = verify_detail(detail.content, slug=slug, identity=identity, title=title)
                        notice = TenderNotice(
                            source=SOURCE_ID, external_id=identity, tender_number=identity + "М",
                            title=match["title"], url=url,
                        )
                        validate_notice(notice, SOURCE_ID)
                        verified.append(notice)
                    except (ValueError, httpx.HTTPStatusError):
                        # Never persist unverified or stale first-party cards.
                        continue
                if not verified:
                    raise ValueError("No independently verified NMCK first-party notices")
                return verified
