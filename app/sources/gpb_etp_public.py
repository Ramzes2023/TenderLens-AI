"""Opt-in Gazprombank ETP public procurement cards with detail verification.

Covers openly visible platform procedures, not a verified legal classification.
Strict same-host HTTPS, no redirects, credentials, cookies or TLS bypass.
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

SOURCE_ID = "gpb_etp_public"
HOST = "etpgpb.ru"
LIST_URL = f"https://{HOST}/procedures/"
MAX_BYTES = 1_800_000
MAX_DETAILS = 3
# Public index may contain stale procedures. Inspect a bounded surplus of
# first-party detail links, but publish only independently verified originals.
MAX_CANDIDATES = 9
# First-party GPB detail URLs include both <number>/ and <number>-<slug>/.
_PATH = re.compile(r"/procedures/etp/([0-9]{5,10})(?:-[a-z0-9-]+)?/")


class _Cards(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.headings = []
        self._heading = None
        self.visible = []
        self._hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {'head', 'title', 'script', 'style', 'template', 'noscript', 'svg'}:
            self._hidden += 1
        if self._hidden:
            return
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag == "h1" and self._heading is None:
            self._heading = []

    def handle_data(self, data):
        if self._hidden:
            return
        self.visible.append(data)
        if self._heading is not None:
            self._heading.append(data)

    def handle_endtag(self, tag):
        if tag in {'head', 'title', 'script', 'style', 'template', 'noscript', 'svg'}:
            self._hidden = max(0, self._hidden - 1)
            return
        if self._hidden:
            return
        if tag == "h1" and self._heading is not None:
            self.headings.append(" ".join(" ".join(self._heading).split()))
            self._heading = None


def _html(payload):
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_BYTES or b"\x00" in payload:
        raise ValueError("Invalid official GPB public HTML")
    return payload.decode("utf-8-sig", "replace")


def parse_gpb_public_links(payload, limit=MAX_DETAILS):
    if type(limit) is not int or not 1 <= limit <= MAX_CANDIDATES:
        raise ValueError("Invalid GPB public fetch limit")
    parser = _Cards()
    parser.feed(_html(payload))
    parser.close()
    records = []
    seen = {}
    for href in parser.links:
        if (type(href) is not str or not href or len(href) > 1500
                or chr(92) in href
                or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in href)):
            continue
        try:
            url = urlsplit(urljoin(LIST_URL, href))
        except ValueError:
            continue
        match = _PATH.fullmatch(url.path)
        if (not match or url.scheme != "https" or url.netloc != HOST
                or url.fragment or url.query or url.username or url.password or url.port is not None):
            continue
        identity = match.group(1)
        if identity in seen:
            if seen[identity] != url.geturl():
                raise ValueError("Conflicting GPB public procedure URLs")
            continue
        seen[identity] = url.geturl()
        records.append((identity, url.geturl()))
        if len(records) == limit:
            break
    if not records:
        raise ValueError("No public GPB procedure URLs")
    return records


def parse_gpb_verified_detail(payload, identity, detail_url):
    if type(identity) is not str or not re.fullmatch(r"[0-9]{5,10}", identity):
        raise ValueError("Invalid GPB procedure identity")
    parts = urlsplit(detail_url)
    if (parts.scheme != "https" or parts.netloc != HOST
            or not _PATH.fullmatch(parts.path)
            or _PATH.fullmatch(parts.path).group(1) != identity
            or parts.query or parts.fragment):
        raise ValueError("Noncanonical GPB procedure detail")
    page = _html(payload)
    parser = _Cards()
    parser.feed(page)
    parser.close()
    headings = [name for name in parser.headings if name and len(name) <= 1000]
    # Demand the numeric public procedure identity in the detail document and
    # exactly one unambiguous nonempty H1 title.
    # An identifier only inside a hidden script/style is NOT an independently
    # verified native original. Require a first-party human-readable occurrence.
    if (not re.search(r"(?<![0-9])" + re.escape(identity) + r"(?![0-9])",
                      " ".join(parser.visible)) or len(set(headings)) != 1):
        raise ValueError("GPB official public detail identity or title mismatch")
    title = headings[0]
    notice = TenderNotice(
        source=SOURCE_ID, external_id=identity, title=title, url=detail_url,
    )
    validate_notice(notice, SOURCE_ID)
    return notice



def parse_gpb_official_rss(payload, *, limit=MAX_CANDIDATES):
    """Accept only exact-origin procurement originals in GPB's documented RSS.

    An XML title/link is only a candidate; independently fetched HTML detail
    must still corroborate the exact native procedure number and visible H1.
    """
    import xml.etree.ElementTree as ET

    if type(limit) is not int or not 1 <= limit <= MAX_CANDIDATES:
        raise ValueError("Invalid GPB RSS candidate bound")
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_BYTES:
        raise ValueError("Invalid official GPB RSS size")
    upper = payload.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper or bytes([0]) in payload:
        raise ValueError("Unsafe official GPB RSS XML")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        raise ValueError("Malformed official GPB RSS XML") from None
    if root.tag != "rss" or root.find("channel") is None:
        raise ValueError("Not an official GPB RSS channel")
    seen, entries = {}, []
    for item in root.find("channel").findall("item"):
        raw = (item.findtext("link") or "").strip()
        title = " ".join((item.findtext("title") or "").split())
        if not 8 <= len(title) <= 1000 or not raw or len(raw) > 1500:
            continue
        if chr(92) in raw or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in raw):
            continue
        try:
            parsed = urlsplit(raw)
        except ValueError:
            continue
        match = _PATH.fullmatch(parsed.path)
        if (not match or parsed.scheme != "https" or parsed.netloc != HOST
                or parsed.query or parsed.fragment or parsed.username
                or parsed.password or parsed.port is not None):
            continue
        identity = match.group(1)
        if identity in seen:
            if seen[identity] != raw:
                raise ValueError("Conflicting official GPB RSS original ID")
            continue
        seen[identity] = raw
        entries.append((identity, raw))
        if len(entries) >= limit:
            break
    if not entries:
        raise ValueError("No original GPB procurement URLs in official RSS")
    return entries


@dataclass(frozen=True)
class GpbEtpPublicSource:
    timeout: float = 20
    name: str = SOURCE_ID

    def __post_init__(self):
        if (self.name != SOURCE_ID or type(self.timeout) not in (float, int)
                or not math.isfinite(self.timeout) or not 0 < self.timeout <= 30):
            raise ValueError("Invalid public GPB source configuration")

    async def fetch(self, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid GPB source limit")
        cap = min(limit, MAX_DETAILS)
        candidate_count = min(MAX_CANDIDATES, cap * 3)
        # Two independent official candidate routes, plus at most a bounded
        # number of independently fetched exact-host original detail pages.
        policy = (bounded_fetch(FetchPolicy(frozenset({HOST}), candidate_count + 2, max_bytes=MAX_BYTES))
                  if _policy.get() is None else nullcontext())
        with policy:
            async with source_client(
                timeout=self.timeout, follow_redirects=False, trust_env=False,
                # Official host answers with a 200/empty binary payload to Python's
                # default UA; a conventional browser UA returns the real HTML.
                # Keep normal TLS verification, strict host policy and no redirects.
                headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
            ) as client:
                from .http import ConnectorTransportError
                records = None
                try:
                    res = await client.get(LIST_URL)
                    res.raise_for_status()
                    if "html" not in res.headers.get("content-type", "").lower():
                        raise ValueError("Public GPB listing is not HTML")
                    records = parse_gpb_public_links(res.content, limit=candidate_count)
                except (ConnectorTransportError, httpx.HTTPStatusError, ValueError,
                        httpx.TransportError, TimeoutError, OSError):
                    # The publisher officially documents /procedures.rss as a
                    # separate list channel. Never follow a redirect or use an
                    # unapproved third-party mirror.
                    feed = await client.get(f"https://{HOST}/procedures.rss",
                                            headers={"Accept": "application/rss+xml, application/xml"})
                    feed.raise_for_status()
                    if not any(x in feed.headers.get("content-type", "").lower()
                               for x in ("rss", "xml")):
                        raise ValueError("Official GPB RSS was not XML")
                    records = parse_gpb_official_rss(feed.content, limit=candidate_count)
                verified = []
                for identity, detail_url in records:
                    try:
                        item = await client.get(detail_url)
                        item.raise_for_status()
                        if "html" not in item.headers.get("content-type", "").lower():
                            raise ValueError("Public GPB detail is not HTML")
                        verified.append(parse_gpb_verified_detail(item.content, identity, detail_url))
                        if len(verified) >= cap:
                            break
                    except (ValueError, httpx.HTTPStatusError):
                        # Fail closed for stale individual notices; never store an
                        # unverified card or substitute a fabricated fallback.
                        continue
                if not verified:
                    raise ValueError("No independently verified public GPB tenders")
                return verified
