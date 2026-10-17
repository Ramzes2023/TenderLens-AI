"""First-party bounded public South Ural procurement source adapter.

Research-only public listing -> two independent same-origin detail corroborations.
No fixtures in live check, secrets, personal data, login, redirects or TLS bypass.
"""
from __future__ import annotations
from dataclasses import dataclass
from contextlib import nullcontext
import math
from datetime import datetime
import asyncio
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit
import httpx
from .http import FetchPolicy, bounded_fetch, source_client, _policy
from .models import TenderNotice
from .opportunities import validate_notice

SOURCE_ID="south_ural_public"
HOST="www.vendorportal.ru"
LIST_URL="https://www.vendorportal.ru/Market/OfferInvitationOpen"
DETAIL_PREFIX="https://www.vendorportal.ru/Market/OfferInvitationOpen/View/"
MAX_BYTES=1_800_000
RECORDS=2
MAX_PAGE_ITEMS=10
NUMBER=re.compile(r"[0-9]{5,8}\Z")
DETAIL_PATH=re.compile(r"/Market/OfferInvitationOpen/View/([0-9]{5,8})\Z")

class TableHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows=[]
        self.row=None
        self.cell=None
        self.link=None
        self.links=[]
        self.visible=[]
        self.hidden=[]

    def handle_starttag(self,tag,attrs):
        if tag in ("script","style","svg","template","noscript","iframe"):
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag=="tr":
            self.row={"cells":[],"links":[]}
        if tag in ("td","th") and self.row is not None:
            self.cell=[]
        if tag=="a":
            self.link=[dict(attrs).get("href"),[]]

    def handle_data(self,text):
        if self.hidden:
            return
        self.visible.append(text)
        if self.cell is not None:
            self.cell.append(text)
        if self.link is not None:
            self.link[1].append(text)

    def handle_endtag(self,tag):
        if self.hidden:
            if self.hidden[-1]==tag:
                self.hidden.pop()
            return
        if tag=="a" and self.link is not None:
            href,text=self.link
            item=(href," ".join(" ".join(text).split()))
            self.links.append(item)
            if self.row is not None:
                self.row["links"].append(item)
            self.link=None
        if tag in ("td","th") and self.cell is not None and self.row is not None:
            self.row["cells"].append(" ".join(" ".join(self.cell).split()))
            self.cell=None
        if tag=="tr" and self.row is not None:
            self.rows.append(self.row)
            self.row=None

def read_doc(body):
    if type(body) is not bytes or not 0 < len(body) <= MAX_BYTES or b"\0" in body:
        raise ValueError("Untrusted public HTML")
    parser=TableHTML()
    parser.feed(body.decode("utf-8-sig","replace"))
    parser.close()
    return parser

def canonical_detail(href):
    if (type(href) is not str or not 0 < len(href) <= 600 or "\\" in href
            or any(ord(c)<32 or c.isspace() for c in href)):
        return None
    try:
        url=urlsplit(urljoin(LIST_URL,href))
        if (url.scheme!="https" or url.netloc!=HOST or url.port is not None
                or url.username is not None or url.password is not None
                or url.fragment):
            return None
        match=DETAIL_PATH.fullmatch(url.path)
        if match is None:
            return None
        # Rebuild approved query instead of following arbitrary returnUrl,
        # session IDs or server-provided redirects from untrusted listing.
        return match.group(1),DETAIL_PREFIX+match.group(1)+"?isReadOnly=True"
    except ValueError:
        return None

def parse_public_listing(body, *, limit=MAX_PAGE_ITEMS):
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE_ITEMS:
        raise ValueError('Invalid South Ural page bound')
    doc=read_doc(body)
    found=[]
    seen=set()
    for row in doc.rows:
        texts=row["cells"]
        row_numbers={cell for cell in texts if NUMBER.fullmatch(cell)}
        if len(row_numbers)!=1:
            continue
        number=next(iter(row_numbers))
        candidates=[]
        for href,title in row["links"]:
            target=canonical_detail(href)
            if target is not None and target[0]==number and 7<=len(title)<=550 and re.search(r"[А-Яа-яЁё]",title):
                candidates.append((number,title,target[1]))
        if len(candidates)!=1 or number in seen:
            continue
        seen.add(number)
        found.extend(candidates)
    if len(found)<RECORDS:
        raise ValueError("Not enough published first-party numbered South Ural invitations")
    return found[:limit]

def verify_public_detail(body,number,title,url):
    if canonical_detail(url)!=(number,url) or not NUMBER.fullmatch(number):
        raise ValueError("Unsafe detail identity")
    doc=read_doc(body)
    text=" ".join(" ".join(doc.visible).split())
    if not re.search(r"Просмотр приглашения №\s*"+re.escape(number)+r"(?![0-9])",text):
        raise ValueError("Independent viewing heading does not match list identity")
    # Table fields are the authoritative independently fetched values, not
    # hidden scripts, unrelated linked docs or a copy of the list row.
    pairs={}
    for row in doc.rows:
        c=row["cells"]
        if len(c)>=2:
            key=c[0].rstrip("*").strip().lower()
            if key in ("номер","предмет договора","тип закупки"):
                pairs.setdefault(key,set()).add(c[1].strip())
    if (pairs.get("номер")!={number}
            or pairs.get("предмет договора")!={title}
            or not pairs.get("тип закупки")
            or not any(v in x for x in pairs["тип закупки"] for v in (
                "Закупка", "Запрос коммерческих предложений", "закупка"))):
        raise ValueError("Number, title, or genuine procurement type mismatch")
    return (number,title,url)



def verified_detail_metadata(body):
    """Extract only independently visible first-party procurement fields.

    Missing price/deadline remain unknown; bad numeric/date values or
    contradictory repeated fields make the record inadmissible.
    """
    fields={}
    labels=frozenset({
        "организация", "дата окончания подачи оферт",
        "максимальная цена товаров, работ, услуг", "валюта",
    })
    for row in read_doc(body).rows:
        cells=row["cells"]
        if len(cells) != 2:
            continue
        label=cells[0].rstrip("*: ").strip().casefold()
        if label not in labels:
            continue
        value=cells[1].strip()
        if not value or len(value)>2000:
            raise ValueError("Invalid first-party procurement detail field")
        if label in fields and fields[label] != value:
            raise ValueError("Conflicting repeated procurement detail field")
        fields[label]=value
    customer=fields.get("организация")
    price=None
    raw=fields.get("максимальная цена товаров, работ, услуг")
    if raw is not None and raw.casefold() != "цена не определена":
        # Public site uses spaces as grouping, comma as decimal; never
        # interpret symbols or guess contract prices from product rows.
        clean=raw.replace(" ", "").replace("\u00a0","").replace("\u202f","").replace(",",".")
        if not re.fullmatch(r"\d{1,12}(?:\.\d{1,2})?",clean):
            raise ValueError("Unparseable official maximum contract price")
        price=float(clean)
        if not 0 <= price <= 100_000_000_000:
            raise ValueError("Unreasonable maximum contract price")
    currency=None
    raw_currency=fields.get("валюта")
    if raw_currency:
        if raw_currency != "Российский рубль":
            raise ValueError("Unsupported currency without explicit validated ISO code")
        currency="RUB"
    deadline=None
    raw_date=fields.get("дата окончания подачи оферт")
    if raw_date:
        match=re.fullmatch(
            r"(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})\s+\(UTC([+-]\d{2}:\d{2})\)(?:\s+Екатеринбург)?",
            raw_date
        )
        if match is None:
            raise ValueError("Unparseable official bid deadline")
        day,month,year,hour,minute,offset=match.groups()
        try:
            deadline=datetime.fromisoformat(
                f"{year}-{month}-{day}T{hour}:{minute}:00{offset}"
            ).isoformat(timespec="seconds")
        except ValueError as error:
            raise ValueError("Impossible official bid deadline") from error
    return {
        "customer":customer,
        "initial_price":price,
        "currency":currency if price is not None else None,
        "deadline":deadline,
    }


@dataclass(frozen=True)
class SouthUralPublicSource:
    timeout: float = 20
    name: str = SOURCE_ID

    def __post_init__(self):
        if (self.name != SOURCE_ID or type(self.timeout) not in (int,float)
                or not math.isfinite(self.timeout) or not 0 < self.timeout <= 30):
            raise ValueError("Invalid South Ural source configuration")

    async def fetch(self, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid South Ural result limit")
        cap=min(limit,MAX_PAGE_ITEMS)
        ctx=(bounded_fetch(FetchPolicy(frozenset({HOST}),cap+1,max_bytes=MAX_BYTES))
             if _policy.get() is None else nullcontext())
        with ctx:
            async with source_client(
                timeout=self.timeout, trust_env=False,follow_redirects=False,
                headers={"Accept":"text/html","User-Agent":"Mozilla/5.0"},
            ) as client:
                listing=await client.get(LIST_URL)
                listing.raise_for_status()
                if "html" not in listing.headers.get("content-type","").lower():
                    raise ValueError("South Ural listing not public HTML")
                cards=parse_public_listing(listing.content, limit=cap)
                notices=[]
                for number,title,url in cards:
                    try:
                        detail=await client.get(url)
                        detail.raise_for_status()
                        if "html" not in detail.headers.get("content-type","").lower():
                            raise ValueError("South Ural official detail not public HTML")
                        verify_public_detail(detail.content,number,title,url)
                        metadata=verified_detail_metadata(detail.content)
                        notice=TenderNotice(
                            source=SOURCE_ID,external_id=number,tender_number=number,
                            title=title,url=url,region="Челябинская область",
                            **metadata,
                        )
                        validate_notice(notice,SOURCE_ID)
                        notices.append(notice)
                    except (ValueError,httpx.HTTPStatusError):
                        continue
                if not notices:
                    raise ValueError("No independently corroborated South Ural tender details")
                return notices
