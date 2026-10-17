"""Official Ankara Metropolitan Municipality PUBLIC active tender detail notices.

Fixed first-page index and up to FOUR verified official detail GETs, within
the leased connector transport budget of 5. No authorization, pagination,
third-party hosts, hidden services, arbitrary upstream query or credentials.
Only live tender details with printed IKN, buyer, title and future deadline.
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

SOURCE_ID="tr_ankara_municipality"
INDEX_URL="https://www.ankara.bel.tr/ihaleler"
_HOSTS=frozenset({"www.ankara.bel.tr"})
_MAX_BYTES=1024*1024
_MAX_DETAIL_REQUESTS=4
_TRT=timezone(timedelta(hours=3))
_LINK=re.compile(r"""href\s*=\s*["']([^"']+)["']""",re.I)
_DETAIL_PATH=re.compile(r"^/ihaleler/detay/([1-9][0-9]{1,9})$")
_KIK=re.compile(r"^[0-9]{4}/[1-9][0-9]{2,10}$")
_DATE_FMT="%d.%m.%Y %H:%M"
_EXPIRED=re.compile(r"\b(?:İptal Edildi|İhale İptal|İptal İlanı|Sonuç İlanı|İhale Sonucu)\b",re.I)


def _plain(body:bytes)->str:
    if not body or len(body)>_MAX_BYTES:
        raise SourceError("Ankara official tender page empty or oversized.")
    text=body.decode("utf-8","replace")
    # Remove JavaScript/styles so embedded templates and scripts cannot masquerade
    # as visible bidding information. No hidden API calls.
    text=re.sub(r"<(?:script|style)\b[^>]*>.*?</(?:script|style)\s*>"," ",text,flags=re.I|re.S)
    text=re.sub(r"<!--.*?-->"," ",text,flags=re.S)
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]*>"," ",text))).strip()


def listing_detail_links(payload:bytes,*,limit:int=_MAX_DETAIL_REQUESTS)->tuple[str,...]:
    text=payload.decode("utf-8","replace")
    if len(payload)>_MAX_BYTES or "İhaleler" not in _plain(payload):
        raise SourceError("Ankara municipality has no official tender listing.")
    out=[]
    seen=set()
    for href in _LINK.findall(text):
        try:
            checked=_safe_link(html.unescape(href),_HOSTS,base=INDEX_URL)
        except SourceError:
            continue
        parts=urlsplit(checked)
        match=_DETAIL_PATH.fullmatch(parts.path)
        if not match or parts.query or checked in seen:
            continue
        seen.add(checked)
        out.append(checked)
        if len(out)>=min(_MAX_DETAIL_REQUESTS,max(1,int(limit))):
            break
    if not out:
        raise SourceError("Ankara public tender listing has no verifiable detail links.")
    return tuple(out)


def _field(text:str,left:str,right:str)->str|None:
    pattern=r"\b"+re.escape(left)+r"\s+(.{1,1800}?)\s+"+re.escape(right)+r"\b"
    m=re.search(pattern,text,re.I|re.S)
    return m.group(1).strip() if m else None


def parse_ankara_tender(payload:bytes,*,detail_url:str,as_of:datetime|None=None)->TenderNotice|None:
    try:
        checked=_safe_link(detail_url,_HOSTS)
    except SourceError:
        raise SourceError("Unapproved Ankara government tender detail URL.") from None
    parsed=urlsplit(checked)
    match=_DETAIL_PATH.fullmatch(parsed.path)
    if not match or parsed.query:
        raise SourceError("Unapproved Ankara government tender detail route.")
    text=_plain(payload)
    if "İhale Detayı" not in text or "İhale Konusu" not in text:
        raise SourceError("Ankara tender detail page structure missing.")
    title=_field(text,"İhale Konusu","İhale Birimi")
    buyer=_field(text,"İhale Birimi","İhale Kısa Özeti")
    ikn_match=re.search(r"\bKİK Kayıt No\s+([0-9]{4}/[0-9]{3,12})\b",text)
    date_match=re.search(r"\bİhale Tarihi/Saati\s+([0-9]{2}\.[0-9]{2}\.[0-9]{4}\s+[0-9]{2}:[0-9]{2})\b",text)
    if (not title or not buyer or len(title)>1000 or len(buyer)>2000
            or not ikn_match or not date_match or not _KIK.fullmatch(ikn_match.group(1))
            or _EXPIRED.search(title)):
        return None
    try:
        deadline=datetime.strptime(date_match.group(1),_DATE_FMT).replace(tzinfo=_TRT)
    except ValueError:
        return None
    now=as_of or datetime.now(_TRT)
    if now.tzinfo is None:
        raise ValueError("Ankara comparison time must be timezone-aware.")
    # No invented publication timestamp and no pretending an expired tender is open.
    if deadline<=now.astimezone(_TRT) or deadline>now.astimezone(_TRT)+timedelta(days=366):
        return None
    return TenderNotice(
        source=SOURCE_ID,
        external_id=match.group(1),
        title=title,
        url=checked,
        tender_number=ikn_match.group(1),
        customer=buyer,
        deadline=deadline.isoformat(),
        published_at=None,
        region="Türkiye — Ankara Metropolitan Municipality",
    )


@dataclass(frozen=True)
class AnkaraMunicipalitySource:
    name:str=SOURCE_ID
    timeout:float=25.0

    def __post_init__(self):
        if self.name!=SOURCE_ID or not 0<self.timeout<=60:
            raise ValueError("Ankara municipality source configuration is invalid.")

    async def fetch(self,limit:int=20)->list[TenderNotice]:
        listing=await _fetch(INDEX_URL,self.timeout,"text/html,application/xhtml+xml")
        links=listing_detail_links(listing,limit=min(_MAX_DETAIL_REQUESTS,max(1,int(limit))))
        result=[]
        seen=set()
        for url in links:
            page=await _fetch(url,self.timeout,"text/html,application/xhtml+xml")
            item=parse_ankara_tender(page,detail_url=url)
            if item is not None and item.external_id not in seen:
                seen.add(item.external_id)
                result.append(item)
        if not result:
            raise SourceError("Ankara official listing had no verified still-open tender details.")
        return result
