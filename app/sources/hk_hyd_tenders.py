"""Official Hong Kong Highways Department tender RSS, independent opt-in.

One bounded, fixed HTTPS RSS request; no login, redirects to other origins,
detail-page crawling, scraped awards, invented budgets or deadlines.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urlsplit

from .asia_public import _fetch, _published, _safe_link, _text
from .eis_rss import SourceError
from .models import TenderNotice

SOURCE_ID = "hk_hyd_tenders"
RSS_URL = "https://www.hyd.gov.hk/en/information_corner/rss/tender_notices.php"
_OFFICIAL = frozenset({"www.hyd.gov.hk"})
_MAX_BYTES = 1024 * 1024
_RSS1 = "{http://purl.org/rss/1.0/}"
_RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
_ATOM = "{http://www.w3.org/2005/Atom}"
_DC = "{http://purl.org/dc/elements/1.1/}"
_NOT_TENDER = re.compile(
    r"(?:\b(?:awards?|awarded|forecast|results?|closed tenders?)\b"
    r"|consultancies awarded|contracts awarded|briefing sessions)", re.I
)


def parse_hyd_tenders(payload: bytes, *, limit: int = 20) -> list[TenderNotice]:
    if not payload or len(payload) > _MAX_BYTES:
        raise SourceError("Highways Department RSS is empty or oversized.")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise SourceError("Highways Department RSS contained forbidden XML declarations.")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        raise SourceError("Highways Department RSS malformed.") from None
    if root.tag == "rss":
        entries = root.findall("./channel/item")
    elif root.tag == _RDF + "RDF":
        entries = root.findall(_RSS1 + "item")
    elif root.tag == _ATOM + "feed":
        entries = root.findall(_ATOM + "entry")
    else:
        raise SourceError("Highways Department endpoint is not RSS/Atom.")
    results: list[TenderNotice] = []
    seen: set[str] = set()
    for item in entries:
        if root.tag == "rss":
            title, link, date = (item.findtext("title"), item.findtext("link"),
                                 item.findtext("pubDate"))
            summary = item.findtext("description")
        elif root.tag == _RDF + "RDF":
            title, link, date = (item.findtext(_RSS1 + "title"), item.findtext(_RSS1 + "link"),
                                 item.findtext(_DC + "date"))
            summary = item.findtext(_RSS1 + "description")
        else:
            title = item.findtext(_ATOM + "title")
            link = next((x.get("href") for x in item.findall(_ATOM + "link")
                         if x.get("rel", "alternate") == "alternate"), None)
            date = item.findtext(_ATOM + "published") or item.findtext(_ATOM + "updated")
            summary = item.findtext(_ATOM + "summary")
        clean_title = _text(title)
        if not clean_title or not link or _NOT_TENDER.search(clean_title):
            continue
        try:
            canonical = _safe_link(
                _text(link), _OFFICIAL, base=RSS_URL, upgrade_official_http=True
            )
        except SourceError:
            continue
        path = urlsplit(canonical).path
        # A verified individual procurement page, not a news, award,
        # forecast, index or generic "what's new" landing page.
        if (not path.startswith("/en/tender_notices/")
                or path.endswith("/index.html") or path.endswith("/index.php")
                or re.search(r"/(?:awards?|forecasts?|contracts_awarded|consultancies_awarded)/", path, re.I)):
            continue
        identity = hashlib.sha256((canonical + "\n" + clean_title).encode("utf-8")).hexdigest()[:40]
        if identity in seen:
            continue
        seen.add(identity)
        results.append(TenderNotice(
            source=SOURCE_ID, external_id=identity,
            title=clean_title[:1000], url=canonical,
            published_at=_published(date),
            customer="Hong Kong Highways Department",
            region="Hong Kong",
            summary=_text(summary)[:4000] or None,
        ))
        if len(results) >= max(1, min(int(limit), 100)):
            break
    if not results:
        raise SourceError("Highways Department RSS contains no verified linked tender notices.")
    return results


@dataclass(frozen=True)
class HighwaysTendersSource:
    name: str = SOURCE_ID
    timeout: float = 25.0

    def __post_init__(self):
        if self.name != SOURCE_ID or not 0 < self.timeout <= 60:
            raise ValueError("Invalid Highways Department RSS configuration.")

    async def fetch(self, limit: int = 20) -> list[TenderNotice]:
        payload = await _fetch(
            RSS_URL, self.timeout, "application/rss+xml,application/xml,text/xml"
        )
        return parse_hyd_tenders(payload, limit=limit)
