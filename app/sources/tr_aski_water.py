"""Official Turkish Ankara ASKİ water-utility PUBLIC tender announcements.

One fixed government list GET and up to four verified individual HTML detail
GETs. Real current notices require a matching public KİK reference and
unexpired exact official deadline. No cookies, login, document downloads,
paginator discovery or other government origins.
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

SOURCE_ID="tr_aski_water"
LIST_URL="https://www.aski.gov.tr/tr/ihale.aspx"
_HOSTS=frozenset({"www.aski.gov.tr"})
_TRT=timezone(timedelta(hours=3))
_MAX_BYTES=1024*1024
_MAX_DETAILS=4
_TR=re.compile(r"<tr\b[^>]*>(.*?)</tr>",re.I|re.S)
_TD=re.compile(r"<td\b[^>]*>(.*?)</td>",re.I|re.S)
_LINK=re.compile(r"""href\s*=\s*["']([^"']+)["']""",re.I)
_DATE=re.compile(r"^[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{4}$")
_KIK=re.compile(r"^[0-9]{4}/[0-9]{4,12}$")
_DETAIL_PATH=re.compile(r"^/tr/IhaleDetay\.aspx$",re.I)


def _plain(value:str)->str:
    s=re.sub(r"<(?:script|style)\b[^>]*>.*?</(?:script|style)\s*>"," ",value,flags=re.I|re.S)
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]*>"," ",s))).strip()


def _detail_link(row:str)->str|None:
    for href in _LINK.findall(row):
        try:
            link=_safe_link(html.unescape(href),_HOSTS,base=LIST_URL)
        except SourceError:
            continue
        url=urlsplit(link)
        params=parse_qs(url.query)
        ident=params.get("ID")
        if (_DETAIL_PATH.fullmatch(url.path) and set(params)=={"ID"}
                and ident and len(ident)==1 and re.fullmatch(r"[1-9][0-9]{1,9}",ident[0])):
            return link
    return None


def listing_rows(payload:bytes,*,limit:int=4,as_of:datetime|None=None)->tuple[tuple[str,str,str,str],...]:
    if not payload or len(payload)>_MAX_BYTES:
        raise SourceError("ASKİ official listing empty or oversized.")
    markup=payload.decode("utf-8","replace")
    if "Güncel İhale İlanları" not in markup and "Güncel İhale İlanları" not in _plain(markup):
        raise SourceError("ASKİ listing did not show the current tender table.")
    now=as_of or datetime.now(_TRT)
    if now.tzinfo is None:raise ValueError("Timezone-aware evaluation required.")
    today=now.astimezone(_TRT).date()
    result=[]
    seen=set()
    for tr in _TR.findall(markup):
        cells=[_plain(cell) for cell in _TD.findall(tr)]
        if len(cells)<6:
            continue
        publication,closing,title,kik=cells[:4]
        if (not title or len(title)>1000 or not _DATE.fullmatch(publication)
                or not _DATE.fullmatch(closing) or not _KIK.fullmatch(kik)):
            continue
        try:
            posted=datetime.strptime(publication,"%d.%m.%Y").date()
            due=datetime.strptime(closing,"%d.%m.%Y").date()
        except ValueError:
            continue
        if posted>today or due<today or due>today+timedelta(days=366):
            continue
        link=_detail_link(tr)
        if not link or link in seen:
            continue
        seen.add(link)
        result.append((link,kik,title,posted.isoformat()))
        if len(result)>=max(1,min(_MAX_DETAILS,int(limit))):
            break
    if not result:
        raise SourceError("ASKİ listed no verifiable current individually linked procurement.")
    return tuple(result)


def parse_detail(payload:bytes,*,url:str,kik:str,title:str,published:str,as_of:datetime|None=None)->TenderNotice|None:
    # Never request or persist a URL outside this fixed official route.
    checked=_safe_link(url,_HOSTS)
    parts=urlsplit(checked)
    if not _DETAIL_PATH.fullmatch(parts.path) or set(parse_qs(parts.query))!={"ID"}:
        raise SourceError("ASKİ individual tender route failed validation.")
    if not payload or len(payload)>_MAX_BYTES:
        raise SourceError("ASKİ official tender detail empty or oversized.")
    text=_plain(payload.decode("utf-8","replace"))
    match=re.search(r"İhale Kayıt Numarası\s*\(İKN\)\s*:\s*([0-9]{4}/[0-9]{4,12})\b",text,re.I)
    due=re.search(r"2\.1\.\s*Tarih ve Saati\s*:\s*([0-9]{1,2}\.[0-9]{1,2}\.[0-9]{4})\s*-\s*([0-9]{2}:[0-9]{2})",text,re.I)
    if not match or match.group(1)!=kik or not due:
        return None
    try:
        deadline=datetime.strptime(due.group(1)+" "+due.group(2),"%d.%m.%Y %H:%M").replace(tzinfo=_TRT)
    except ValueError:
        return None
    now=as_of or datetime.now(_TRT)
    if now.tzinfo is None:raise ValueError("Timezone-aware evaluation required.")
    if deadline<=now.astimezone(_TRT):
        return None
    # Detail must be an actual ASKİ published bidding notice, not general news.
    if not ("İhale Detayı" in text or "İhale Kayıt Numarası" in text):
        return None
    return TenderNotice(
        source=SOURCE_ID,external_id=parse_qs(parts.query)["ID"][0],
        title=title,url=checked,tender_number=kik,
        customer="Ankara Water and Sewerage Administration (ASKİ)",
        published_at=published,deadline=deadline.isoformat(),region="Türkiye — Ankara",
    )


@dataclass(frozen=True)
class ASKIWaterTendersSource:
    name:str=SOURCE_ID
    timeout:float=25.0

    def __post_init__(self):
        if self.name!=SOURCE_ID or not 0<self.timeout<=60:
            raise ValueError("Unapproved ASKİ government tender settings.")

    async def fetch(self,limit:int=20)->list[TenderNotice]:
        page=await _fetch(LIST_URL,self.timeout,"text/html,application/xhtml+xml")
        candidates=listing_rows(page,limit=min(_MAX_DETAILS,max(1,int(limit))))
        notices=[]
        for link,kik,title,published in candidates:
            body=await _fetch(link,self.timeout,"text/html,application/xhtml+xml")
            row=parse_detail(body,url=link,kik=kik,title=title,published=published)
            if row:
                notices.append(row)
        if not notices:
            raise SourceError("ASKİ returned no verified unexpired individual government tender.")
        return notices
