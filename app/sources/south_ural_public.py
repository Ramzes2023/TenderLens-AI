"""First-party bounded public South Ural procurement source adapter.

Research-only public listing -> two independent same-origin detail corroborations.
No fixtures in live check, secrets, personal data, login, redirects or TLS bypass.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from contextlib import nullcontext
import math
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



def independently_verified_deadline(body, number, title, url):
    """Parse only a complete, uniquely labeled public detail date and UTC offset.

    No guessing from page header, search hit date, listed time, or local PC timezone.
    """
    verify_public_detail(body, number, title, url)
    page = read_doc(body)
    dates = set()
    for row in page.rows:
        cells = row["cells"]
        if (len(cells) >= 2 and cells[0].rstrip("*").strip().lower()
                == "дата окончания подачи оферт"):
            dates.add(cells[1].strip())
    if not dates:
        return None
    if len(dates) != 1:
        raise ValueError("Conflicting public South Ural submission deadlines")
    value = next(iter(dates))
    match = re.fullmatch(
        r"(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}) "
        r"\(UTC([+-])(\d{2}):(\d{2})\) [А-Яа-яЁё -]{2,40}",
        value,
    )
    if not match:
        raise ValueError("Unrecognized official South Ural public deadline")
    hours, minutes = int(match[3]), int(match[4])
    if hours > 14 or minutes not in (0, 15, 30, 45) or (hours == 14 and minutes != 0):
        raise ValueError("Invalid public deadline timezone offset")
    offset = timedelta(hours=hours, minutes=minutes)
    if match[2] == "-":
        offset = -offset
    dt = datetime.strptime(match[1], "%d.%m.%Y %H:%M")
    return dt.replace(tzinfo=timezone(offset)).isoformat(timespec="seconds")



def verified_optional_fields(body):
    """Optional fields read only from visible, separately verified public details.

    The original tender number/title and exact zoned deadline are verified
    elsewhere before these enrichment fields can enter an opportunity.
    Price and RUB are emitted together only with an explicit currency field.
    """
    approved = {"организация", "максимальная цена товаров, работ, услуг",
                "валюта", "тип закупки"}
    fields = {}
    for row in read_doc(body).rows:
        cells = row["cells"]
        if len(cells) != 2:
            continue
        label = cells[0].strip().rstrip("*: ").strip().casefold()
        if label not in approved:
            continue
        value = cells[1].strip()
        if not value or len(value) > 2000 or "\x00" in value:
            raise ValueError("Invalid public optional procurement field")
        if label in fields and fields[label] != value:
            raise ValueError("Conflicting independently visible procurement fields")
        fields[label] = value

    customer = fields.get("организация")
    if customer is not None and (not 3 <= len(customer) <= 2000
            or not re.search(r"[А-Яа-яЁёA-Za-z]", customer)
            or any(c in customer for c in "<>")):
        customer = None

    procurement_type = fields.get("тип закупки")
    if procurement_type is not None and (len(procurement_type) > 160
            or not (procurement_type.startswith("Закупка")
                    or procurement_type.startswith("Запрос коммерческих предложений"))):
        procurement_type = None

    price = None
    currency = None
    raw = fields.get("максимальная цена товаров, работ, услуг")
    declared_currency = fields.get("валюта")
    if raw and raw not in ("Цена не определена", "Не установлена", "-"):
        # An unlabeled or non-RUB figure must not be presented as RUB.
        if declared_currency == "Российский рубль":
            normalized = raw.replace("\u00a0", " ").replace("\u202f", " ")
            if not re.fullmatch(r"(?:\d{1,3}(?: \d{3})+|\d{1,12})(?:,\d{1,2})?", normalized):
                raise ValueError("Malformed official South Ural maximum price")
            price = float(normalized.replace(" ", "").replace(",", "."))
            if not math.isfinite(price) or not 0 < price <= 1_000_000_000_000:
                raise ValueError("Invalid official South Ural maximum price")
            currency = "RUB"

    return {
        "customer": customer,
        "initial_price": price,
        "currency": currency,
        "summary": ("Вид закупки: " + procurement_type) if procurement_type else None,
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
                        deadline=independently_verified_deadline(detail.content,number,title,url)
                        notice=TenderNotice(
                            source=SOURCE_ID,external_id=number,tender_number=number,
                            title=title,url=url,region="Челябинская область",deadline=deadline,
                            **verified_optional_fields(detail.content),
                        )
                        validate_notice(notice,SOURCE_ID)
                        notices.append(notice)
                    except (ValueError,httpx.HTTPStatusError):
                        continue
                if not notices:
                    raise ValueError("No independently corroborated South Ural tender details")
                return notices
