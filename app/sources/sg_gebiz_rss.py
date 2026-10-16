"""Singapore GeBIZ's own open business-opportunity RSS; TWO official categories.

Anonymous official RSS category feeds discovered by an isolated real HTTP probe.
They are *not* award feeds and do not cover all Singapore procurement.
Strict official HTTPS origin, exact individual GeBIZ opportunity detail,
document code identity and no guessed deadlines/prices. Operator opt-in only.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from .asia_public import _fetch, _published, _safe_link, _text
from .eis_rss import SourceError
from .models import TenderNotice

FEEDS = {
    "sg_gebiz_professional": "https://www.gebiz.gov.sg/rss/Professional_Services-CREATE_BO_FEED.xml",
    "sg_gebiz_misc": "https://www.gebiz.gov.sg/rss/OthersMiscellaneous-CREATE_BO_FEED.xml",
}
_HOSTS = frozenset({"www.gebiz.gov.sg"})
_MAX_BYTES = 1024 * 1024
_DOCUMENT = re.compile(r"^[A-Za-z0-9]{8,64}$")
_DETAIL_PATH = "/ptn/opportunity/opportunityDetails.xhtml"
_QUERY_KEYS = frozenset({"code", "status", "type", "OPPORTUNITY_ID", "origin"})
_NON_BID = re.compile(r"\b(?:tender awards?|award notices?|awarded|results?|cancelled tenders?)\b", re.I)
_RSS1 = "{http://purl.org/rss/1.0/}"
_DC = "{http://purl.org/dc/elements/1.1/}"
_RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
_ATOM = "{http://www.w3.org/2005/Atom}"


def parse_gebiz_business_rss(payload: bytes, *, source: str, limit: int = 20) -> list[TenderNotice]:
    if source not in FEEDS or not payload or len(payload) > _MAX_BYTES:
        raise SourceError("Unknown, empty or oversized Singapore GeBIZ feed.")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise SourceError("Singapore GeBIZ feed contains forbidden XML declarations.")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        raise SourceError("Singapore GeBIZ feed XML malformed.") from None
    if root.tag == "rss":
        entries = root.findall("./channel/item")
    elif root.tag == _RDF + "RDF":
        entries = root.findall(_RSS1 + "item")
    elif root.tag == _ATOM + "feed":
        entries = root.findall(_ATOM + "entry")
    else:
        raise SourceError("Singapore GeBIZ endpoint is not RSS or Atom.")
    notices = []
    seen = set()
    for item in entries:
        if root.tag == "rss":
            title = item.findtext("title")
            url = item.findtext("link")
            published = item.findtext("pubDate")
            summary = item.findtext("description")
        elif root.tag == _RDF + "RDF":
            title = item.findtext(_RSS1 + "title")
            url = item.findtext(_RSS1 + "link")
            published = item.findtext(_DC + "date")
            summary = item.findtext(_RSS1 + "description")
        else:
            title = item.findtext(_ATOM + "title")
            url = next((node.get("href") for node in item.findall(_ATOM + "link")
                        if node.get("rel", "alternate") == "alternate"), None)
            published = item.findtext(_ATOM + "published") or item.findtext(_ATOM + "updated")
            summary = item.findtext(_ATOM + "summary")
        clean_title = _text(title)
        if not clean_title or not url or _NON_BID.search(clean_title):
            continue
        try:
            detail = _safe_link(_text(url), _HOSTS, base=FEEDS[source],
                                upgrade_official_http=True)
        except SourceError:
            continue
        parsed = urlsplit(detail)
        if parsed.path != _DETAIL_PATH:
            continue
        params = parse_qs(parsed.query, keep_blank_values=True)
        if not params or not set(params).issubset(_QUERY_KEYS):
            continue
        values = params.get("code")
        # Government document code, not an arbitrary page identifier or index.
        if not values or len(values) != 1 or not _DOCUMENT.fullmatch(values[0]):
            continue
        # A business opportunity with an official item ID, not an award row.
        ids = params.get("OPPORTUNITY_ID")
        if not ids or len(ids) != 1 or not ids[0] or len(ids[0]) > 256:
            continue
        code = values[0]
        external_id = hashlib.sha256(code.encode("utf-8")).hexdigest()[:40]
        if external_id in seen:
            continue
        seen.add(external_id)
        notices.append(TenderNotice(
            source=source,
            external_id=external_id,
            title=clean_title[:1000],
            url=detail,
            tender_number=code,
            published_at=_published(published),
            customer="Government Electronic Business (GeBIZ), Singapore",
            region="Singapore",
            summary=_text(summary)[:4000] or None,
        ))
        if len(notices) >= max(1, min(int(limit), 100)):
            break
    if not notices:
        raise SourceError("GeBIZ official RSS contains no verified individual open opportunities.")
    return notices


@dataclass(frozen=True)
class SingaporeGeBizRssSource:
    name: str
    timeout: float = 25.0

    def __post_init__(self):
        if self.name not in FEEDS or not 0 < self.timeout <= 60:
            raise ValueError("Unapproved Singapore GeBIZ source configuration.")

    async def fetch(self, limit: int = 20) -> list[TenderNotice]:
        payload = await _fetch(FEEDS[self.name], self.timeout,
                               "application/rss+xml,application/xml,text/xml")
        return parse_gebiz_business_rss(payload, source=self.name, limit=limit)
