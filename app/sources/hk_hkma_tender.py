"""HKMA official tender-invitation open API; no award feed and no login.

Reads ONLY https://api.hkma.gov.hk/public/tender-invitations?lang=en&segment=tender
from the government's free public API. Each link is a vetted official
government Gazette notice, never fetched by this adapter. Opening/closing
dates and prices are unknown when the government record does not provide them.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import urlsplit, parse_qs

from .asia_public import _fetch, _safe_link, _text
from .eis_rss import SourceError
from .models import TenderNotice

SOURCE_ID="hk_hkma_tender"
API_URL="https://api.hkma.gov.hk/public/tender-invitations?lang=en&segment=tender&pagesize=30"
_GAZETTE=frozenset({"egazette.gld.gov.hk"})
_ALLOWED_QUERY=frozenset({"extra","gno","notice_no","type","volume","year"})
_MAX_BYTES=1024*1024
_MAX_ITEMS=30
_DATE=re.compile(r"20\d{2}-\d{2}-\d{2}")


def parse_hkma_tenders(payload: bytes, *, limit=20, as_of=None) -> list[TenderNotice]:
    if not payload or len(payload)>_MAX_BYTES:
        raise SourceError("HKMA government tender API response empty or oversized.")
    try:
        content=json.loads(payload)
    except (ValueError,UnicodeDecodeError):
        raise SourceError("HKMA government tender API did not return JSON.") from None
    if not isinstance(content,dict) or not isinstance(content.get("result"),dict):
        raise SourceError("HKMA tender API schema invalid.")
    result=content["result"]
    rows=result.get("records")
    if not isinstance(rows,list) or len(rows)>1000:
        raise SourceError("HKMA tender API record list invalid.")
    if not rows:
        raise SourceError("HKMA tender API returned no invitation records.")
    today=as_of if as_of is not None else date.today()
    if not isinstance(today,date):
        raise ValueError("Invalid evaluation day.")
    found=[]
    seen=set()
    for raw in rows:
        if not isinstance(raw,dict):
            continue
        title=_text(raw.get("title") if isinstance(raw.get("title"),str) else None)
        source_url=raw.get("link")
        published=raw.get("date")
        if not title or not isinstance(source_url,str) or not isinstance(published,str):
            continue
        if not _DATE.fullmatch(published):
            continue
        try:
            day=date.fromisoformat(published)
        except ValueError:
            continue
        # Omit clearly archived or future entries; no invented active deadline.
        if not today-timedelta(days=120)<=day<=today+timedelta(days=1):
            continue
        try:
            safe_url=_safe_link(source_url,_GAZETTE)
        except SourceError:
            continue
        parts=urlsplit(safe_url)
        if parts.path!="/pdf" or len(parts.query)>800:
            continue
        params=parse_qs(parts.query,keep_blank_values=True)
        if (not params or not set(params).issubset(_ALLOWED_QUERY)
                or not {"notice_no","year","type"}.issubset(params)
                or any(len(values)!=1 or len(values[0])>100 or
                       any(ord(ch)<32 or ord(ch)==127 for ch in values[0])
                       for values in params.values())):
            continue
        # Trust exact government gazette link as identity; never embed
        # unapproved redirect/cross-origin or customer-provided parameters.
        external_id=hashlib.sha256(safe_url.encode()).hexdigest()[:40]
        if external_id in seen:
            continue
        seen.add(external_id)
        found.append(TenderNotice(
            source=SOURCE_ID,external_id=external_id,title=title[:1000],
            url=safe_url,published_at=published,
            customer="Hong Kong Monetary Authority",
            region="Hong Kong",
        ))
        if len(found)>=max(1,min(int(limit),100)):
            break
    if not found:
        raise SourceError("HKMA API contained no verifiable recent official tender invitations.")
    return found


@dataclass(frozen=True)
class HKMATenderSource:
    name: str=SOURCE_ID
    timeout: float=25.0

    def __post_init__(self):
        if self.name!=SOURCE_ID or not 0<self.timeout<=60:
            raise ValueError("Invalid HKMA public tender source.")

    async def fetch(self,limit=20):
        payload=await _fetch(API_URL,self.timeout,"application/json")
        return parse_hkma_tenders(payload,limit=limit)
