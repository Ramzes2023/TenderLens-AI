"""Konya municipality independently published current ORIGINAL procurement detail pages.

A government buyer-controlled regional discovery stream (not Turkey-wide EKAP).
One current HTTPS list plus <=4 separately GET'd, exact-host original tender
pages per leased worker sync. Original EKAP KIK identity is preserved for global
cross-source deduplication; no property auctions, invented prices or ICB date
guesses. International IsDB reference IDB-KON-G01 requires separate independently
parsed signed addendum and is NOT admitted by this adapter.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from .asia_public import _fetch, _safe_link
from .eis_rss import SourceError
from .models import TenderNotice

SOURCE_ID = "tr_konya_municipality"
INDEX_URL = "https://www.konya.bel.tr/ihale"
_HOSTS = frozenset({"www.konya.bel.tr"})
_TRT = timezone(timedelta(hours=3))
_MAX_BYTES = 1024 * 1024
_MAX_DETAILS = 4
_LINK = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
_PATH = re.compile(r"^/ihale/[a-z0-9-]{12,180}$")
_KIK = re.compile(r"İhale\s+Kayıt\s+Numarası\s*\(\s*İKN\s*\)\s*:?\s*(20\d\d/[1-9]\d{3,10})", re.I)
_DATE = re.compile(r"Son\s+Müracaat\s+Tarihi\s*:?\s*(\d\d\.\d\d\.20\d\d)\s*-\s*(\d\d:\d\d)", re.I)
_BUYER = re.compile(r"İhale\s+Sahibi\s*:?\s*(.{4,200}?)\s+İhalenin\s+Yapılacağı\s+Yer", re.I)
_EXCLUDE = re.compile(r"(?:gayrimenkul|yikim-ihale|satış\s+ihale|satışı|mesken\s+satış|kira\s+ihale|pazarlığa|ihale\s+iptali|ihale\s+sonucu)", re.I)

def _plain(payload: bytes) -> str:
    if not payload or len(payload) > _MAX_BYTES:
        raise SourceError("Konya official page empty or oversized.")
    text = payload.decode("utf-8", "replace")
    text = re.sub(r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", text))).strip()

def original_detail_links(payload: bytes, *, limit: int = _MAX_DETAILS) -> tuple[str, ...]:
    if "İhaleler" not in _plain(payload):
        raise SourceError("Konya official index missing procurement heading.")
    if type(limit) is not int or not 1 <= limit <= _MAX_DETAILS:
        raise ValueError("Invalid Konya detail limit.")
    result = []
    seen = set()
    for raw in _LINK.findall(payload.decode("utf-8", "replace")):
        try:
            link = _safe_link(html.unescape(raw), _HOSTS, base=INDEX_URL)
        except SourceError:
            continue
        parts = urlsplit(link)
        if (not _PATH.fullmatch(parts.path) or parts.query
                or link in seen or _EXCLUDE.search(parts.path)
                or "procurement-of-goods-and-related-services-for-4-electrical" in parts.path):
            continue
        seen.add(link)
        result.append(link)
        if len(result) >= limit:
            break
    if not result:
        raise SourceError("Konya current procurement listing has no approved original detail links.")
    return tuple(result)

def parse_original_detail(payload: bytes, *, link: str, as_of: datetime | None = None) -> TenderNotice | None:
    try:
        safe = _safe_link(link, _HOSTS)
    except SourceError:
        raise SourceError("Konya detail origin not approved.") from None
    path = urlsplit(safe)
    if not _PATH.fullmatch(path.path) or path.query:
        raise SourceError("Konya detail path invalid.")
    text = _plain(payload)
    if "İhale Detay" not in text or "İhale Sahibi" not in text:
        raise SourceError("Konya page does not contain an original municipal tender.")
    if _EXCLUDE.search(path.path):
        return None
    match_id = _KIK.search(text)
    match_date = _DATE.search(text)
    match_buyer = _BUYER.search(text)
    if not (match_id and match_date and match_buyer):
        return None  # No invented tender IDs, buyer or deadline.
    buyer = match_buyer.group(1).strip()
    marker = text.rfind("Arama Yap", 0, match_buyer.start())
    title = text[marker + len("Arama Yap"):match_buyer.start()].strip() if marker >= 0 else ""
    if not title or len(title) > 1000 or len(buyer) > 200 or _EXCLUDE.search(title):
        return None
    try:
        due = datetime.strptime(" ".join(match_date.groups()), "%d.%m.%Y %H:%M").replace(tzinfo=_TRT)
    except ValueError:
        return None
    now = as_of or datetime.now(_TRT)
    if now.tzinfo is None:
        raise ValueError("Konya source requires timezone-aware time.")
    if not now.astimezone(_TRT) < due <= now.astimezone(_TRT) + timedelta(days=366):
        return None
    original_id = match_id.group(1)
    # Body must actually be an original public government competitive bid,
    # not a sale/lease result, generic page or mirrored search shell.
    if "KONYA BÜYÜKŞEHİR" not in text.upper() or "EKAP" not in text.upper():
        return None
    return TenderNotice(
        source=SOURCE_ID, external_id=original_id.replace("/", "-"),
        tender_number=original_id, title=title, url=safe,
        customer=buyer, deadline=due.isoformat(), region="Türkiye, Konya",
        published_at=None, initial_price=None, currency=None,
    )

@dataclass(frozen=True)
class KonyaMunicipalitySource:
    name: str = SOURCE_ID
    timeout: float = 25.0

    def __post_init__(self):
        if self.name != SOURCE_ID or not 0 < self.timeout <= 40:
            raise ValueError("Invalid Konya procurement source configuration.")

    async def fetch(self, limit: int = 20) -> list[TenderNotice]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid Konya maximum results.")
        original = await _fetch(INDEX_URL, self.timeout, "text/html")
        links = original_detail_links(original, limit=min(limit, _MAX_DETAILS))
        output = []
        seen = set()
        for link in links:
            notice = parse_original_detail(await _fetch(link, self.timeout, "text/html"), link=link)
            if notice and notice.tender_number not in seen:
                seen.add(notice.tender_number)
                output.append(notice)
        if not output:
            raise SourceError("Konya real first-party listing had no eligible live numbered tenders.")
        return output
