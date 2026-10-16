"""Opt-in JETRO's own Japanese competitive-bid RSS; not Japan-wide JETRO database.

The official feed concerns tenders issued by the Japan External Trade
Organization itself. It must not be represented as national procurement
coverage or enabled without independent live, persisted-search acceptance.
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

SOURCE_ID = "jp_jetro_bid"
RSS_URL = "https://www.jetro.go.jp/rss/proc_bid.xml"
MAX_BYTES = 1024 * 1024
_OFFICIAL = frozenset({"www.jetro.go.jp"})
# The page must identify an individual competitive-bid detail, not a category,
# general press release, procurement index, result listing, or other RSS.
_DETAIL = re.compile(r"/procurement/bid/[a-z0-9_-]+/[0-9a-f]{16}\.html", re.I)
_RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
_RSS1 = "{http://purl.org/rss/1.0/}"
_ATOM = "{http://www.w3.org/2005/Atom}"
_DC = "{http://purl.org/dc/elements/1.1/}"
_NON_TENDER = re.compile(
    r"(?:入札結果|落札|契約結果|結果発表|入札中止|入札取消|"
    r"contract awards?|award notices?|cancell?ed tenders?)", re.I
)


def parse_jetro_bid_rss(payload: bytes, *, limit: int = 20) -> list[TenderNotice]:
    """Accept only official, linked JETRO bid notices in RSS/Atom."""
    if not payload or len(payload) > MAX_BYTES:
        raise SourceError("JETRO bid feed empty or oversized.")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise SourceError("JETRO bid XML contains forbidden declarations.")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        raise SourceError("JETRO bid feed XML malformed.") from None
    if root.tag == "rss":
        entries = root.findall("./channel/item")
    elif root.tag == _RDF + "RDF":
        entries = root.findall(_RSS1 + "item")
    elif root.tag == _ATOM + "feed":
        entries = root.findall(_ATOM + "entry")
    else:
        raise SourceError("JETRO bid endpoint is not RSS or Atom.")

    records: list[TenderNotice] = []
    seen: set[str] = set()
    for item in entries:
        if root.tag == "rss":
            title = item.findtext("title")
            link = item.findtext("link")
            date = item.findtext("pubDate")
            description = item.findtext("description")
        elif root.tag == _RDF + "RDF":
            title = item.findtext(_RSS1 + "title")
            link = item.findtext(_RSS1 + "link")
            date = item.findtext(_DC + "date")
            description = item.findtext(_RSS1 + "description")
        else:
            title = item.findtext(_ATOM + "title")
            link = next((node.get("href") for node in item.findall(_ATOM + "link")
                         if node.get("rel", "alternate") == "alternate"), None)
            date = item.findtext(_ATOM + "published") or item.findtext(_ATOM + "updated")
            description = item.findtext(_ATOM + "summary")
        clean_title = _text(title)
        if not clean_title or not link or _NON_TENDER.search(clean_title):
            continue
        try:
            canonical = _safe_link(
                _text(link), _OFFICIAL, base=RSS_URL, upgrade_official_http=True
            )
        except SourceError:
            continue
        if not _DETAIL.fullmatch(urlsplit(canonical).path):
            continue
        external_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:40]
        if external_id in seen:
            continue
        seen.add(external_id)
        records.append(TenderNotice(
            source=SOURCE_ID,
            external_id=external_id,
            title=clean_title[:1000],
            url=canonical,
            published_at=_published(date),
            customer="Japan External Trade Organization (JETRO)",
            region="Japan",
            summary=_text(description)[:4000] or None,
        ))
        if len(records) >= max(1, min(int(limit), 100)):
            break
    if not records:
        raise SourceError("JETRO bid RSS contained no verified individual tender links.")
    return records


@dataclass(frozen=True)
class JetroBidRssSource:
    name: str = SOURCE_ID
    timeout: float = 25.0

    def __post_init__(self):
        if self.name != SOURCE_ID or not 0 < self.timeout <= 60:
            raise ValueError("Invalid JETRO bid source configuration.")

    async def fetch(self, limit: int = 20) -> list[TenderNotice]:
        payload = await _fetch(
            RSS_URL, self.timeout, "application/rss+xml,application/xml,text/xml"
        )
        return parse_jetro_bid_rss(payload, limit=limit)
