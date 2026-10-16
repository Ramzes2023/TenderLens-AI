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
_PATH = re.compile(r"/procedures/etp/([0-9]{5,10})-[a-z0-9-]+/")


class _Cards(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.headings = []
        self._heading = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag == "h1" and self._heading is None:
            self._heading = []

    def handle_data(self, data):
        if self._heading is not None:
            self._heading.append(data)

    def handle_endtag(self, tag):
        if tag == "h1" and self._heading is not None:
            self.headings.append(" ".join(" ".join(self._heading).split()))
            self._heading = None


def _html(payload):
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_BYTES or b"\x00" in payload:
        raise ValueError("Invalid official GPB public HTML")
    return payload.decode("utf-8-sig", "replace")


def parse_gpb_public_links(payload, limit=MAX_DETAILS):
    if type(limit) is not int or not 1 <= limit <= MAX_DETAILS:
        raise ValueError("Invalid GPB public fetch limit")
    parser = _Cards()
    parser.feed(_html(payload))
    parser.close()
    records = []
    seen = {}
    for href in parser.links:
        if type(href) is not str or len(href) > 1500 or "\\" in href:
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
    if identity not in page or len(set(headings)) != 1:
        raise ValueError("GPB official public detail identity or title mismatch")
    title = headings[0]
    notice = TenderNotice(
        source=SOURCE_ID, external_id=identity, title=title, url=detail_url,
    )
    validate_notice(notice, SOURCE_ID)
    return notice


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
        policy = (bounded_fetch(FetchPolicy(frozenset({HOST}), cap + 1, max_bytes=MAX_BYTES))
                  if _policy.get() is None else nullcontext())
        with policy:
            async with source_client(
                timeout=self.timeout, follow_redirects=False, trust_env=False,
                headers={"Accept": "text/html"},
            ) as client:
                res = await client.get(LIST_URL)
                res.raise_for_status()
                if "html" not in res.headers.get("content-type", "").lower():
                    raise ValueError("Public GPB listing is not HTML")
                records = parse_gpb_public_links(res.content, limit=cap)
                verified = []
                for identity, detail_url in records:
                    try:
                        item = await client.get(detail_url)
                        item.raise_for_status()
                        if "html" not in item.headers.get("content-type", "").lower():
                            raise ValueError("Public GPB detail is not HTML")
                        verified.append(parse_gpb_verified_detail(item.content, identity, detail_url))
                    except (ValueError, httpx.HTTPStatusError):
                        # Fail closed for stale individual notices; never store an
                        # unverified card or substitute a fabricated fallback.
                        continue
                if not verified:
                    raise ValueError("No independently verified public GPB tenders")
                return verified
