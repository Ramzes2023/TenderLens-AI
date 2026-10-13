"""Isolated, unregistered EIS 223-FZ RSS candidate adapter."""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from .eis_rss import (
    EIS_EXTENDED_RSS_URL, SourceError, _child_text, _local_name,
    parse_eis_feed,
)
from .http import ConnectorTransportError, page_limit, source_client
from .models import TenderNotice

SOURCE_NAME = "eis_223"
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_SEARCH_TERMS = 100
MAX_TERM_CHARS = 500


def build_eis_223_rss_url(search_term: str) -> str:
    term = " ".join(search_term.split())
    if not term or len(term) > MAX_TERM_CHARS:
        raise ValueError("search_term must contain 1..500 characters")
    return EIS_EXTENDED_RSS_URL + "?" + urlencode({
        "searchString": term, "morphology": "on",
        "pageNumber": "1", "fz223": "on",
    })


def build_eis_223_rss_urls(
    search_terms: Iterable[str], *, max_feeds: int = 5,
) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    cap = max(1, min(int(max_feeds), 20))
    for index, raw in enumerate(search_terms):
        if index >= MAX_SEARCH_TERMS:
            break
        term = " ".join(str(raw).split())
        if not term or term.casefold() in seen:
            continue
        seen.add(term.casefold())
        result.append(build_eis_223_rss_url(term))
        if len(result) >= cap:
            break
    return tuple(result)


@dataclass(frozen=True)
class Eis223Notice(TenderNotice):
    """Filter intent and observed text are never independent legal verification."""

    requested_law: str = "223-FZ"
    observed_law: str | None = None
    independently_verified_law: str | None = None
    feed_url: str | None = None
    raw_guid: str | None = None
    raw_description: str | None = None


def parse_eis_223_feed(
    payload: bytes, *, feed_url: str | None = None,
) -> list[Eis223Notice]:
    if len(payload) > MAX_RESPONSE_BYTES:
        raise SourceError("EIS 223 RSS exceeds 5 MiB")
    # Reject declarations even in UTF-16/32; no DTD/entity expansion is needed.
    probe = payload.replace(b"\x00", b"").lower()
    if b"<!doctype" in probe or b"<!entity" in probe:
        raise SourceError("EIS 223 RSS DTD/entities are not supported")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        raise SourceError("EIS 223 returned malformed RSS/Atom XML") from None
    if _local_name(root.tag) not in {"rss", "feed", "rdf"}:
        raise SourceError("EIS 223 response is not RSS/Atom XML")
    result: list[Eis223Notice] = []
    seen: set[tuple[str, str]] = set()
    for entry in root.iter():
        if _local_name(entry.tag) not in {"item", "entry"}:
            continue
        base = parse_eis_feed(ET.tostring(entry), source_name=SOURCE_NAME)[0]
        guid = _child_text(entry, {"guid", "id"})
        description = _child_text(entry, {"description", "summary", "content"})
        # Only an explicit result-level label counts as observed law evidence.
        match = re.search(
            r"Размещение\s+выполняется\s+по\s*:\s*(44|223)\s*[-–]?\s*ФЗ\b",
            description, re.I,
        )
        # Reuse normalized core fields, but do not interpret search-form numbers
        # or monetary keyword matches as procurement business fields.
        number = re.search(r"(?<!\d)(\d{11,20})(?!\d)", base.title + " " + base.url)
        tender_number = number.group(1) if number else None
        external_id = guid or tender_number or hashlib.sha256(
            (base.url or f"{base.title}|{base.published_at or ''}|{description}").encode("utf-8")
        ).hexdigest()
        if len(external_id) > 500:
            external_id = "sha256:" + hashlib.sha256(external_id.encode("utf-8")).hexdigest()
        values = asdict(base)
        values.update(external_id=external_id, tender_number=tender_number,
                      customer=None, initial_price=None, currency=None,
                      deadline=None, region=None)
        notice = Eis223Notice(
            **values, observed_law=f"{match.group(1)}-FZ" if match else None,
            feed_url=feed_url, raw_guid=guid or None,
            raw_description=description or None,
        )
        if notice.identity not in seen:
            seen.add(notice.identity)
            result.append(notice)
    return result


def _validate_feed_url(url: str) -> None:
    parts = urlsplit(url)
    query = parse_qs(parts.query, keep_blank_values=True)
    if (parts.scheme != "https" or parts.netloc != "zakupki.gov.ru"
            or parts.path != urlsplit(EIS_EXTENDED_RSS_URL).path or parts.fragment
            or query.get("fz223") != ["on"]
            or any(key.casefold() == "fz44" for key in query)):
        raise ValueError("Expected public EIS HTTPS RSS URL with fz223=on and no fz44")


@dataclass(frozen=True)
class Eis223RssSource:
    urls: tuple[str, ...] = ()
    timeout: float = 30.0
    ca_bundle_file: Path | None = None
    name: str = field(default=SOURCE_NAME, init=False)

    def __post_init__(self) -> None:
        for url in self.urls:
            _validate_feed_url(url)
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")

    def for_search_terms(
        self, search_terms: Iterable[str], *, max_feeds: int = 5,
    ) -> Eis223RssSource:
        return Eis223RssSource(
            urls=build_eis_223_rss_urls(search_terms, max_feeds=max_feeds) or self.urls,
            timeout=self.timeout, ca_bundle_file=self.ca_bundle_file,
        )

    async def fetch(self, limit: int = 20) -> list[Eis223Notice]:
        limit = max(1, min(int(limit), 100))
        if not self.urls:
            return []
        seen: set[tuple[str, str]] = set()
        merged: list[Eis223Notice] = []
        verify: bool | str = str(self.ca_bundle_file) if self.ca_bundle_file else True
        try:
            async with source_client(
                timeout=self.timeout, follow_redirects=False, verify=verify,
                trust_env=True, headers={"User-Agent": "TenderLensAI/0.9 (+RSS monitor)"},
            ) as client:
                for url in self.urls[:page_limit(min(len(self.urls), 20))]:
                    async with client.stream("GET", url) as response:
                        response.raise_for_status()
                        if "html" in response.headers.get("content-type", "").lower():
                            raise SourceError("EIS 223 returned HTML instead of RSS")
                        chunks: list[bytes] = []
                        size = 0
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            size += len(chunk)
                            if size > MAX_RESPONSE_BYTES:
                                raise SourceError("EIS 223 RSS exceeds 5 MiB")
                            chunks.append(chunk)
                    for notice in parse_eis_223_feed(b"".join(chunks), feed_url=url):
                        if notice.identity in seen:
                            continue
                        seen.add(notice.identity)
                        merged.append(notice)
                        if len(merged) >= limit:
                            return merged
        except (httpx.HTTPError, OSError, ConnectorTransportError):
            raise SourceError("Could not fetch EIS 223 RSS; check HTTP, timeout and TLS CA") from None
        return merged
