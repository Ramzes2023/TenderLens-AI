"""Bounded opt-in live TEK-Torg 223-FZ public listing + detail verifier.

No credentials, guessed SOAP interface, invented fields, redirects or TLS bypass.
Each normalized public notice must match its own same-host detail h1.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import math
import re
from urllib.parse import urljoin, urlsplit

from .http import FetchPolicy, bounded_fetch, _policy, source_client
from .models import TenderNotice
from .opportunities import validate_notice

SOURCE_ID = "tektorg"
HOST = "www.tektorg.ru"
LIST_URL = f"https://{HOST}/223-fz/procedures"
MAX_BYTES = 1_600_000
MAX_PER_FETCH = 5
_PATH = re.compile(r"/223-fz/procedures/([0-9]{5,15})/?")


def _text(parts):
    return " ".join(" ".join(parts).split())


class _PublicListing(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.current = None
        self.records = []
    
    def handle_starttag(self, tag, attrs):
        if self.current is not None:
            return
        if tag != "a":
            return
        raw = dict(attrs).get("href", "")
        if type(raw) is not str or len(raw) > 2000:
            return
        p = urlsplit(urljoin(LIST_URL, raw))
        m = _PATH.fullmatch(p.path)
        if (m and p.scheme == "https" and p.netloc == HOST
                and not p.query and not p.fragment and not p.username
                and not p.password and p.port is None):
            self.current = [m.group(1), p.geturl(), []]
    
    def handle_data(self, data):
        if self.current is not None:
            self.current[2].append(data)

    def handle_endtag(self, tag):
        if self.current is None:
            return
        if tag == 'a':
            identity, url, parts = self.current
            self.records.append((identity, url, _text(parts)))
            self.current = None


class _DetailHeading(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active = False
        self.parts = []
        self.headings = []

    def handle_starttag(self, tag, attrs):
        if tag == "h1" and not self.active:
            self.active = True
            self.parts = []

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "h1" and self.active:
            self.headings.append(_text(self.parts))
            self.active = False


def _document(payload):
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_BYTES:
        raise ValueError("Invalid TEK-Torg HTML response size")
    if b"\x00" in payload:
        raise ValueError("Invalid TEK-Torg HTML bytes")
    return payload.decode("utf-8-sig", "replace")


def parse_public_listing(payload, *, limit=MAX_PER_FETCH):
    if type(limit) is not int or not 1 <= limit <= MAX_PER_FETCH:
        raise ValueError("Invalid TEK-Torg request limit")
    reader = _PublicListing()
    reader.feed(_document(payload))
    reader.close()
    records = []
    seen = {}
    for identity, url, title in reader.records:
        if identity in seen:
            if seen[identity] != (url, title):
                raise ValueError("Conflicting TEK-Torg procurement identity")
            continue
        seen[identity] = (url, title)
        if not title or len(title) > 1000 or "<" in title or "\x00" in title:
            raise ValueError("Invalid TEK-Torg procurement title")
        records.append((identity, url, title))
        if len(records) >= limit:
            break
    if not records:
        raise ValueError("No public TEK-Torg procurement cards")
    return records


def validate_public_detail(payload, *, identity, title):
    body = _document(payload)
    reader = _DetailHeading()
    reader.feed(body)
    reader.close()
    if (type(identity) is not str or not _PATH.fullmatch(f"/223-fz/procedures/{identity}")
            or type(title) is not str or not title):
        raise ValueError("Invalid TEK-Torg detail request")
    if identity not in body or title not in reader.headings:
        raise ValueError("TEK-Torg detail title/identity mismatch")


@dataclass(frozen=True)
class TekTorgPublicSource:
    name: str = SOURCE_ID
    timeout: float = 20

    def __post_init__(self):
        if (self.name != SOURCE_ID or type(self.timeout) not in (float, int)
                or not math.isfinite(self.timeout) or not 0 < self.timeout <= 30):
            raise ValueError("Invalid TEK-Torg configuration")

    async def fetch(self, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid TEK-Torg fetch bound")
        cap = min(limit, MAX_PER_FETCH)
        policy = (bounded_fetch(FetchPolicy(frozenset({HOST}), cap + 1,
                                       max_bytes=MAX_BYTES))
                  if _policy.get() is None else None)
        from contextlib import nullcontext
        with policy if policy is not None else nullcontext():
            async with source_client(
                timeout=self.timeout, trust_env=False,
                follow_redirects=False, headers={"Accept": "text/html"},
            ) as client:
                listing = await client.get(LIST_URL)
                listing.raise_for_status()
                if "html" not in listing.headers.get("content-type", "").lower():
                    raise ValueError("TEK-Torg listing not HTML")
                public = parse_public_listing(listing.content, limit=cap)
                notices = []
                for identity, url, title in public:
                    detail = await client.get(url)
                    detail.raise_for_status()
                    if "html" not in detail.headers.get("content-type", "").lower():
                        raise ValueError("TEK-Torg detail not HTML")
                    validate_public_detail(detail.content, identity=identity, title=title)
                    notice = TenderNotice(
                        source=SOURCE_ID, external_id=identity,
                        title=title, url=url,
                    )
                    validate_notice(notice, SOURCE_ID)
                    notices.append(notice)
                return notices
