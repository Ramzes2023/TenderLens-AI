"""Bounded opt-in live TEK-Torg 223-FZ public listing + detail verifier.

No credentials, guessed SOAP interface, invented fields, redirects or TLS bypass.
Each normalized public notice must match its own same-host detail h1.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import math
import httpx
import re
from urllib.parse import urljoin, urlsplit

from .http import ConnectorTransportError, FetchPolicy, bounded_fetch, _policy, source_client
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
    """Only visible, independently linked first-party procurement candidates."""

    _HIDDEN = frozenset({"head", "script", "style", "iframe",
                         "svg", "object", "template", "noscript"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.current = None
        self.records = []
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if self.current is not None:
            # Active markup inside a first-party candidate is suspicious;
            # fail closed instead of silently repairing an invalid title.
            if tag in self._HIDDEN:
                raise ValueError("Active markup inside public procurement title")
            return
        if tag in self._HIDDEN:
            self.hidden.append(tag)
            return
        if self.hidden or tag != "a":
            return
        raw = dict(attrs).get("href", "")
        if (type(raw) is not str or not raw or len(raw) > 2000
                or chr(92) in raw or "%" in raw
                or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in raw)):
            return
        try:
            p = urlsplit(urljoin(LIST_URL, raw))
        except ValueError:
            return
        m = _PATH.fullmatch(p.path)
        if (m and p.scheme == "https" and p.netloc == HOST
                and not p.query and not p.fragment and not p.username
                and not p.password and p.port is None):
            self.current = [m.group(1), p.geturl(), []]

    def handle_data(self, data):
        if self.current is not None and not self.hidden:
            self.current[2].append(data)

    def handle_endtag(self, tag):
        if self.hidden:
            if self.hidden[-1] == tag:
                self.hidden.pop()
            return
        if tag == "a" and self.current is not None:
            identity, url, parts = self.current
            self.records.append((identity, url, _text(parts)))
            self.current = None


class _DetailHeading(HTMLParser):
    """Independently verify visible official detail, not script/header metadata."""

    _HIDDEN = frozenset({"head", "script", "style", "noscript",
                         "template", "svg", "iframe", "object"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active = False
        self.parts = []
        self.headings = []
        self.visible = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._HIDDEN:
            self.hidden += 1
            return
        if tag == "h1" and not self.hidden and not self.active:
            self.active = True
            self.parts = []

    def handle_data(self, data):
        if self.hidden:
            return
        self.visible.append(data)
        if self.active:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag in self._HIDDEN:
            self.hidden = max(0, self.hidden - 1)
            return
        if tag == "h1" and self.active and not self.hidden:
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
    # The URL ends with an internal platform ID (e.g. 11993106), while the
    # official visible notice can identify the actual procurement as
    # "Извещение о процедуре ЗП409589" and separately "№ ЗП409589".
    # Both must be first-party visible (not <head>, script, template, etc.).
    # A second detail on the exact discovered URL still has to corroborate
    # the independently observed listing H1; never invent an external ID.
    visible = " ".join(" ".join(reader.visible).split())
    identity_pattern = r"(?<![0-9])" + re.escape(identity) + r"(?![0-9])"
    internal_visible = bool(re.search(identity_pattern, visible))
    published = re.findall(
        r"Извещение\s+о\s+процедуре\s+([А-ЯЁA-Z]{1,6}[0-9]{3,12})(?![А-ЯЁA-Z0-9])",
        visible, flags=re.IGNORECASE,
    )
    native = published[0].upper() if len(set(x.upper() for x in published)) == 1 and published else None
    # The official "Общие сведения: № <native>" must match the breadcrumb.
    native_confirmed = (native is not None and bool(re.search(
        r"(?<![А-ЯЁA-Z0-9])№\s*" + re.escape(native) + r"(?![А-ЯЁA-Z0-9])",
        visible, flags=re.IGNORECASE,
    )))
    if (title not in reader.headings or len(reader.headings) != 1
            or not (internal_visible or native_confirmed)):
        raise ValueError("TEK-Torg detail title/identity mismatch")
    return native if native_confirmed else None


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
                follow_redirects=False,
                # The official host returned an incomplete page to HTTPX default UA.
                # A normal browser UA exposed real same-host procedure anchors on RU3.
                headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
            ) as client:
                listing = await client.get(LIST_URL)
                listing.raise_for_status()
                if "html" not in listing.headers.get("content-type", "").lower():
                    raise ValueError("TEK-Torg listing not HTML")
                public = parse_public_listing(listing.content, limit=cap)
                notices = []
                for identity, url, title in public:
                    try:
                        detail = await client.get(url)
                        detail.raise_for_status()
                        if "html" not in detail.headers.get("content-type", "").lower():
                            raise ValueError("TEK-Torg detail not HTML")
                        published_number = validate_public_detail(detail.content, identity=identity, title=title)
                    except (ValueError, httpx.HTTPStatusError):
                        # A changed/removed public card is not reliable tender data.
                        # Drop only that card; do not ingest it or bypass redirects.
                        continue
                    except ConnectorTransportError as error:
                        # Only a transient single original DETAIL failure may
                        # be skipped to inspect later independent originals.
                        # Policy, public-IP and TLS failure must not be hidden.
                        if not error.retryable:
                            raise
                        continue
                    notice = TenderNotice(
                        source=SOURCE_ID, external_id=identity,
                        tender_number=published_number, title=title, url=url,
                    )
                    validate_notice(notice, SOURCE_ID)
                    notices.append(notice)
                if not notices:
                    raise ValueError("No independently verified public TEK-Torg notice")
                return notices
