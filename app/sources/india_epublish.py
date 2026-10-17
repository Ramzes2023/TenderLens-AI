"""Official India Central ePublishing live tender home, separate from CPPP eProcure.

One anonymous official HTML GET; bounded latest *tenders* table only, no
awards/corrigenda; verifiable site-generated DirectLink in each row, but never
store the temporary session-bearing URL. Saved URL points to stable ePublishing
home and includes the genuine printed public reference in tender_number.
"""
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

from .asia_public import _fetch
from .eis_rss import SourceError
from .models import TenderNotice

SOURCE_ID="in_epublish"
HOME="https://eprocure.gov.in/epublish/app"
LIST_URL=HOME+"?service=home"
_MAX_BYTES=1024*1024
_IST=timezone(timedelta(hours=5,minutes=30))
_CLEAN=re.compile(r"\s+")
_TR=re.compile(r"<tr\b[^>]*>(.*?)</tr>",re.I|re.S)
_TD=re.compile(r"<td\b[^>]*>(.*?)</td>",re.I|re.S)
_LINK=re.compile(r"""href=["']([^"']+)["']""",re.I)
_TITLE=re.compile(r"^\s*\d{1,3}\.\s*(.+)$")
_RAW_DATE="%d-%b-%Y %I:%M %p"


def _text(markup):
    return _CLEAN.sub(" ",html.unescape(re.sub(r"<[^>]*>"," ",markup))).strip()


def _verified_portal_detail(row):
    """Prove the row is a government-generated individual tender link.

    Never return session, sp or any ephemeral page token from this function.
    """
    for raw in _LINK.findall(row):
        link=html.unescape(raw)
        if len(link)>2000 or not ("DirectLink" in link or "%24DirectLink" in link):
            continue
        if any(ord(c)<32 or ord(c)==127 or c=="\\" for c in link):
            continue
        parsed=urlsplit(urljoin(HOME,link))
        if (parsed.scheme!="https" or parsed.hostname!="eprocure.gov.in" or
                parsed.username or parsed.password or parsed.fragment or
                parsed.port not in (None,443) or parsed.path!="/epublish/app"):
            continue
        parameters=parse_qs(parsed.query,keep_blank_values=True)
        if (not parameters or not set(parameters).issubset(
                {"component","page","service","session","sp"}) or
                parameters.get("component")!=["$DirectLink"] or
                parameters.get("page")!=["Home"] or
                not parameters.get("session") or not parameters.get("sp") or
                any(len(values)!=1 or len(values[0])>500 for values in parameters.values())):
            continue
        return True
    return False


def parse_epublish_latest(payload:bytes,*,limit:int=20,as_of:datetime|None=None)->list[TenderNotice]:
    if not payload or len(payload)>_MAX_BYTES:
        raise SourceError("India ePublishing latest tender listing is empty or oversized.")
    document=payload.decode("utf-8","replace")
    start=document.lower().find("latest tenders")
    end=document.lower().find("latest corrigendum",start+1)
    if start<0 or end<0 or end<=start or "Tender Title" not in document[start:end]:
        raise SourceError("India ePublishing home structure did not identify latest tenders section.")
    section=document[start:end]
    now=as_of or datetime.now(_IST)
    if now.tzinfo is None:
        raise ValueError("Timezone-aware acceptance date required.")
    now=now.astimezone(_IST)
    output=[]
    seen=set()
    for tr in _TR.findall(section):
        if not _verified_portal_detail(tr):
            continue
        cells=[_text(x) for x in _TD.findall(tr)]
        if len(cells)!=4:
            continue
        m=_TITLE.fullmatch(cells[0])
        if not m:
            continue
        title=m.group(1).strip()
        ref=cells[1].strip()
        if not title or not ref or len(title)>1000 or len(ref)>500:
            continue
        try:
            closing=datetime.strptime(cells[2],_RAW_DATE).replace(tzinfo=_IST)
            opening=datetime.strptime(cells[3],_RAW_DATE).replace(tzinfo=_IST)
        except ValueError:
            continue
        if closing<now or opening<closing or opening>closing+timedelta(days=120):
            continue
        external_id=hashlib.sha256((ref+"\n"+title).encode("utf-8")).hexdigest()[:40]
        if external_id in seen:
            continue
        seen.add(external_id)
        output.append(TenderNotice(
            source=SOURCE_ID,external_id=external_id,
            title=title,url=LIST_URL,
            tender_number=ref,
            published_at=None,deadline=closing.isoformat(),
            customer="Government of India — Central ePublishing",
            region="India",
            summary="Official ePublishing latest tender listing; search by reference number to view full details.",
        ))
        if len(output)>=max(1,min(int(limit),100)):
            break
    if not output:
        raise SourceError("India ePublishing returned no verified active individually linked tenders.")
    return output


@dataclass(frozen=True)
class IndiaEpublishSource:
    name:str=SOURCE_ID
    timeout:float=25.0

    def __post_init__(self):
        if self.name!=SOURCE_ID or not 0<self.timeout<=60:
            raise ValueError("Invalid India ePublishing public source.")

    async def fetch(self,limit:int=20)->list[TenderNotice]:
        body=await _fetch(LIST_URL,self.timeout,"text/html,application/xhtml+xml")
        return parse_epublish_latest(body,limit=limit)
