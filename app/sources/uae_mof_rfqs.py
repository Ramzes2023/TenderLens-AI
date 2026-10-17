"""UAE Ministry of Finance's public CURRENT federal business opportunities.

One official HTTPS page, six government table cells per RFQ, exact individual
procurement.gov.ae RFQ detail link, no accounts or document scraping.
Does not claim statewide emirate procurements, Dubai, or Abu Dhabi coverage.
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

SOURCE_ID="ae_federal_mof"
URL="https://mof.gov.ae/en/public-finance/government-procurement/current-business-opportunities/"
_HOSTS=frozenset({"procurement.gov.ae"})
_MAX_BYTES=1024*1024
_UAE=timezone(timedelta(hours=4))
_TABLE=re.compile(r"<table\b[^>]*>.*?</table>",re.I|re.S)
_ROW=re.compile(r"<tr\b[^>]*>(.*?)</tr>",re.I|re.S)
_CELL=re.compile(r"<td\b[^>]*>(.*?)</td>",re.I|re.S)
_HREF=re.compile(r"""href=["']([^"']+)["']""",re.I)
_RFQ=re.compile(r"^[1-9][0-9]{2,11}$")
_DETAIL=re.compile(r"^/page\.aspx/en/bpm/process_manage_extranet/([1-9][0-9]{2,11})$")
_DATE_FMT="%d/%m/%Y %I:%M:%S %p"


def _text(value:str)->str:
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]*>"," ",value))).strip()


def parse_uae_open_rfqs(payload:bytes,*,limit:int=20,as_of:datetime|None=None)->list[TenderNotice]:
    if not payload or len(payload)>_MAX_BYTES:
        raise SourceError("UAE finance official open RFQ listing empty or oversized.")
    text=payload.decode("utf-8","replace")
    if "Current Business Opportunities" not in text or "Open tenders" not in text:
        raise SourceError("UAE ministry did not present an open-tender listing.")
    now=as_of or datetime.now(_UAE)
    if not isinstance(now,datetime) or now.tzinfo is None:
        raise ValueError("Timezone-aware evaluation date required.")
    now=now.astimezone(_UAE)
    output=[]
    seen=set()
    found_table=False
    for table in _TABLE.findall(text):
        header=_text(table[:min(4000,len(table))])
        if ("RFQ Number" not in header or "Entity Name" not in header or
                "Open Date" not in header or "Close Date" not in header):
            continue
        found_table=True
        for raw in _ROW.findall(table):
            cells=_CELL.findall(raw)
            if len(cells)!=6:
                continue
            rfq,customer,title,open_date,close_date=[_text(x) for x in cells[:5]]
            if (not _RFQ.fullmatch(rfq) or not customer or not title or
                    len(customer)>1800 or len(title)>1000):
                continue
            try:
                opened=datetime.strptime(open_date,_DATE_FMT).replace(tzinfo=_UAE)
                closed=datetime.strptime(close_date,_DATE_FMT).replace(tzinfo=_UAE)
            except ValueError:
                continue
            if not opened<=closed or closed<now:
                continue
            if opened>now+timedelta(days=1):
                continue
            links=_HREF.findall(cells[5])
            accepted_url=None
            for raw_link in links:
                try:
                    checked=_safe_link(html.unescape(raw_link),_HOSTS)
                except SourceError:
                    continue
                details=urlsplit(checked)
                matched=_DETAIL.fullmatch(details.path)
                if matched and matched.group(1)==rfq and not details.query:
                    accepted_url=checked
                    break
            if not accepted_url or rfq in seen:
                continue
            seen.add(rfq)
            output.append(TenderNotice(
                source=SOURCE_ID,external_id=rfq,title=title,
                url=accepted_url,tender_number=rfq,
                published_at=opened.isoformat(),
                deadline=closed.isoformat(),
                customer=customer,
                region="United Arab Emirates — federal",
            ))
            if len(output)>=max(1,min(int(limit),100)):
                break
        if len(output)>=max(1,min(int(limit),100)):
            break
    if not found_table or not output:
        raise SourceError("UAE Ministry of Finance published no verified current linked federal RFQs.")
    return output


@dataclass(frozen=True)
class UAEMinistryFinanceSource:
    name:str=SOURCE_ID
    timeout:float=25.0

    def __post_init__(self):
        if self.name!=SOURCE_ID or not 0<self.timeout<=60:
            raise ValueError("Invalid UAE Ministry of Finance source configuration.")

    async def fetch(self,limit:int=20)->list[TenderNotice]:
        payload=await _fetch(URL,self.timeout,"text/html,application/xhtml+xml")
        return parse_uae_open_rfqs(payload,limit=limit)
