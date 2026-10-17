"""Türkiye Ankara EGO public transit authority competitive e-ihale notices.

Only published public list + at most four trusted same-host detailed bid
pages. Exact agency, official KİK ID, title and unexpired deadline must match.
Never scrape EKAP verification/challenges or collect user authentication.
"""
from __future__ import annotations
import html
import re
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
from urllib.parse import parse_qs,urlsplit

from .asia_public import _fetch,_safe_link
from .eis_rss import SourceError
from .models import TenderNotice

SOURCE_ID="tr_ego_transport"
INDEX_URL="https://www.ego.gov.tr/ihaleler"
_HOSTS=frozenset({"www.ego.gov.tr"})
_TRT=timezone(timedelta(hours=3))
_MAX_BYTES=1024*1024
_MAX_DETAILS=4
_ROW=re.compile(r"<tr\b[^>]*>(.*?)</tr>",re.I|re.S)
_CELL=re.compile(r"<td\b[^>]*>(.*?)</td>",re.I|re.S)
_LINK=re.compile(r"""href\s*=\s*["']([^"']+)["']""",re.I)
_DETAIL=re.compile(r"^/tr/ihale/detay/([1-9][0-9]{1,9})/([a-z0-9-]{5,160})$",re.I)
_KIK=re.compile(r"^[0-9]{4}/[0-9]{4,12}$")
_DATE_FMT="%d.%m.%Y %H:%M"
_EXCLUDE=re.compile(r"\b(?:ihale sonucu|ihale iptali|ihale iptal|satışına ait)\b",re.I)


def _plain(markup:str)->str:
    safe=re.sub(r"<(?:script|style)\b[^>]*>.*?</(?:script|style)\s*>"," ",markup,flags=re.I|re.S)
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]*>"," ",safe))).strip()


def _detail_url(row:str)->str|None:
    for raw in _LINK.findall(row):
        try:
            url=_safe_link(html.unescape(raw),_HOSTS,base=INDEX_URL)
        except SourceError:
            continue
        parsed=urlsplit(url)
        params=parse_qs(parsed.query)
        if (_DETAIL.fullmatch(parsed.path) and params=={"tip":["0"]}):
            return url
    return None


def parse_ego_listing(payload:bytes,*,limit:int=4,as_of:datetime|None=None)->tuple[tuple[str,str,str],...]:
    if not payload or len(payload)>_MAX_BYTES:
        raise SourceError("EGO city transit government list empty or oversized.")
    raw=payload.decode("utf-8","replace")
    if "İHALELER" not in _plain(raw).upper():
        raise SourceError("EGO procurement listing heading is missing.")
    now=as_of or datetime.now(_TRT)
    if now.tzinfo is None:
        raise ValueError("Aware time required for Turkish tender eligibility.")
    today=now.astimezone(_TRT).date()
    out=[]
    seen=set()
    for tr in _ROW.findall(raw):
        cells=_CELL.findall(tr)
        if len(cells)!=4:continue
        kind,when,title,reference=[_plain(cell) for cell in cells]
        if (not re.search(r"e-ihale",kind,re.I) or not title or
                not _KIK.fullmatch(reference) or _EXCLUDE.search(title)):
            continue
        try:
            due=datetime.strptime(when,"%d.%m.%Y").date()
        except ValueError:
            continue
        if due<today or due>today+timedelta(days=366):
            continue
        link=_detail_url(cells[2])
        if not link or link in seen:
            continue
        seen.add(link)
        out.append((link,reference,title))
        if len(out)>=min(_MAX_DETAILS,max(1,int(limit))):
            break
    if not out:
        raise SourceError("EGO transit portal returned no verified active linked e-tenders.")
    return tuple(out)


def parse_ego_detail(payload:bytes,*,link:str,kik:str,title:str,as_of:datetime|None=None)->TenderNotice|None:
    checked=_safe_link(link,_HOSTS)
    p=urlsplit(checked)
    m=_DETAIL.fullmatch(p.path)
    if not m or parse_qs(p.query)!={"tip":["0"]}:
        raise SourceError("EGO detail URL is not an approved individual e-tender.")
    if not payload or len(payload)>_MAX_BYTES:
        raise SourceError("EGO government tender detail empty or oversized.")
    text=_plain(payload.decode("utf-8","replace"))
    if "İHALE DETAYI" not in text:
        raise SourceError("EGO detail page lacks an official tender record.")
    name=re.search(r"\bİHALE ADI\s+(.{4,1000}?)\s+İHALE BİRİMİ\b",text,re.I|re.S)
    buyer=re.search(r"\bİHALE BİRİMİ\s+(.{4,800}?)\s+KİK KAYIT NO\b",text,re.I|re.S)
    reference=re.search(r"\bKİK KAYIT NO\s+([0-9]{4}/[0-9]{4,12})\b",text,re.I)
    closing=re.search(r"\bİHALE TARİHİ\s+([0-9]{2}\.[0-9]{2}\.[0-9]{4}\s+[0-9]{2}:[0-9]{2})\b",text,re.I)
    if (not name or not buyer or not reference or not closing or
            reference.group(1)!=kik or _EXCLUDE.search(name.group(1))):
        return None
    normalized_title=name.group(1).strip()
    if normalized_title.casefold()!=title.strip().casefold():
        return None
    try:
        deadline=datetime.strptime(closing.group(1),_DATE_FMT).replace(tzinfo=_TRT)
    except ValueError:return None
    now=as_of or datetime.now(_TRT)
    if now.tzinfo is None:raise ValueError("Aware evaluation time required.")
    if deadline<=now.astimezone(_TRT):
        return None
    return TenderNotice(
        source=SOURCE_ID,external_id=m.group(1),title=normalized_title,
        url=checked,tender_number=reference.group(1),
        customer=buyer.group(1).strip(),
        published_at=None,deadline=deadline.isoformat(),
        region="Türkiye — Ankara EGO Transit",
    )


@dataclass(frozen=True)
class EGOTenderSource:
    name:str=SOURCE_ID
    timeout:float=25.0

    def __post_init__(self):
        if self.name!=SOURCE_ID or not 0<self.timeout<=60:
            raise ValueError("Invalid EGO transport procurement configuration.")

    async def fetch(self,limit:int=20)->list[TenderNotice]:
        listing=await _fetch(INDEX_URL,self.timeout,"text/html,application/xhtml+xml")
        candidates=parse_ego_listing(listing,limit=min(_MAX_DETAILS,max(1,int(limit))))
        records=[]
        for link,kik,title in candidates:
            detail=await _fetch(link,self.timeout,"text/html,application/xhtml+xml")
            notice=parse_ego_detail(detail,link=link,kik=kik,title=title)
            if notice is not None:
                records.append(notice)
        if not records:
            raise SourceError("EGO official transit tenders had no verified still-open detail.")
        return records
