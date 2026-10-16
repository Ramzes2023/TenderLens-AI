"""Read-only real Fabrikant 44-FZ public procurement notices.

Each candidate is discovered on the HTTPS public 44-FZ registry and independently
matched to the canonical exact-ID detail H1 and listing title. The platform's
navigation-only ?&backurl is discarded, never forwarded. No invented metadata.
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

SOURCE_ID = "fabrikant_44_public"
HOST = "44.fabrikant.ru"
LIST_URL = "https://" + HOST + "/44/catalog/procedure"
MAX_BYTES = 1_600_000
MAX_DETAILS = 3
_PATH = re.compile(r"/44/procedure/([a-z0-9-]{2,18})/([0-9]{19})")


def _html(payload):
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_BYTES or b"\x00" in payload:
        raise ValueError("Invalid official Fabrikant public HTML")
    return payload.decode("utf-8-sig", "replace")


def _canonical_link(raw):
    if (type(raw) is not str or not 0 < len(raw) <= 1400 or "\\" in raw
            or any(ch.isspace() or ord(ch) < 32 for ch in raw)):
        return None
    try:
        p = urlsplit(urljoin(LIST_URL, raw))
        m = _PATH.fullmatch(p.path)
        if (not m or p.scheme != "https" or p.netloc != HOST or p.port is not None
                or p.username is not None or p.password is not None or p.fragment):
            return None
        if p.query:
            # Observed official listing hrefs contain ?&backurl=<encoded nav>.
            # The query is not a data source and is never sent in GET requests.
            nav = p.query.removeprefix("&")
            if (len(nav) > 500 or not nav.startswith("backurl=")
                    or "&" in nav):
                return None
        return m.group(2), "https://" + HOST + p.path
    except ValueError:
        return None


class _Listing(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if self.current is not None:
            if tag in {"script", "style", "iframe", "svg", "object", "template"}:
                raise ValueError("Active markup in Fabrikant public title")
            return
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.current = (href, [])

    def handle_data(self, data):
        if self.current is not None:
            self.current[1].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            href, pieces = self.current
            self.links.append((href, " ".join(" ".join(pieces).split())))
            self.current = None


class _Detail(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.heading = None
        self.headings = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "noscript", "svg"}:
            self.hidden += 1
        elif not self.hidden and tag == "h1" and self.heading is None:
            self.heading = []

    def handle_data(self, value):
        if not self.hidden:
            self.parts.append(value)
            if self.heading is not None:
                self.heading.append(value)

    def handle_endtag(self, tag):
        if tag == "h1" and self.heading is not None:
            self.headings.append(" ".join(" ".join(self.heading).split()))
            self.heading = None
        if tag in {"script", "style", "template", "noscript", "svg"} and self.hidden:
            self.hidden -= 1


def parse_fabrikant44_listing(payload, *, limit=MAX_DETAILS):
    if type(limit) is not int or not 1 <= limit <= MAX_DETAILS:
        raise ValueError("Invalid Fabrikant public listing limit")
    reader = _Listing()
    reader.feed(_html(payload))
    reader.close()
    found, seen = [], {}
    for href, title in reader.links:
        record = _canonical_link(href)
        if record is None:
            continue
        identity, url = record
        if not 5 <= len(title) <= 1000 or "<" in title or "\x00" in title:
            raise ValueError("Invalid Fabrikant public tender title")
        if identity in seen:
            if seen[identity] != (url, title):
                raise ValueError("Conflicting Fabrikant public procurement identity")
            continue
        seen[identity] = (url, title)
        found.append((identity, url, title))
        if len(found) >= limit:
            break
    if not found:
        raise ValueError("No genuine public Fabrikant procurement links")
    return found


def parse_fabrikant44_detail(payload, *, identity, url, title):
    if (type(identity) is not str or not re.fullmatch(r"[0-9]{19}", identity)
            or type(url) is not str or type(title) is not str
            or _canonical_link(url) != (identity, url)):
        raise ValueError("Noncanonical official Fabrikant detail request")
    reader = _Detail()
    reader.feed(_html(payload))
    reader.close()
    # Official live H1: "Сведения о закупке <exact-number>".
    if len(reader.headings) != 1 or reader.headings[0] != "Сведения о закупке " + identity:
        raise ValueError("Fabrikant detail official H1 identity mismatch")
    visible = " ".join(" ".join(reader.parts).split())
    if title not in visible:
        raise ValueError("Fabrikant detail did not independently confirm listing title")
    notice = TenderNotice(
        source=SOURCE_ID, external_id=identity, tender_number=identity,
        title=title, url=url,
    )
    validate_notice(notice, SOURCE_ID)
    return notice


@dataclass(frozen=True)
class Fabrikant44PublicSource:
    timeout: float = 20
    name: str = SOURCE_ID

    def __post_init__(self):
        if (self.name != SOURCE_ID or type(self.timeout) not in (float, int)
                or not math.isfinite(self.timeout) or not 0 < self.timeout <= 30):
            raise ValueError("Invalid Fabrikant44 public source configuration")

    async def fetch(self, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid Fabrikant public source limit")
        cap = min(limit, MAX_DETAILS)
        ctx = (bounded_fetch(FetchPolicy(frozenset({HOST}), cap + 1, max_bytes=MAX_BYTES))
               if _policy.get() is None else nullcontext())
        with ctx:
            async with source_client(
                timeout=self.timeout, follow_redirects=False, trust_env=False,
                headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
            ) as client:
                listing = await client.get(LIST_URL)
                listing.raise_for_status()
                if "html" not in listing.headers.get("content-type", "").lower():
                    raise ValueError("Fabrikant 44-FZ listing was not HTML")
                records = parse_fabrikant44_listing(listing.content, limit=cap)
                verified = []
                for identity, url, title in records:
                    try:
                        response = await client.get(url)
                        response.raise_for_status()
                        if "html" not in response.headers.get("content-type", "").lower():
                            raise ValueError("Fabrikant 44-FZ detail was not HTML")
                        verified.append(parse_fabrikant44_detail(
                            response.content, identity=identity, url=url, title=title,
                        ))
                    except (ValueError, httpx.HTTPStatusError):
                        # Never store an unverified or stale card.
                        continue
                if not verified:
                    raise ValueError("No independently verified Fabrikant official tenders")
                return verified
