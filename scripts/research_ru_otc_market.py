"""Fail-closed public original OTC-Market regional small-purchase research only.

Only publicly linked, first-party detail URLs and independently confirmed
official notice IDs/subjects count; a standalone indexed historic detail does
not establish a working current listing. No DB writes, credentials, bypasses.
"""
from __future__ import annotations
import asyncio
from html.parser import HTMLParser
import re
from urllib.parse import urljoin,urlsplit
import httpx
from app.sources.http import FetchPolicy,bounded_fetch,source_client,ConnectorTransportError

HOST="market.otc.ru"
LIST_URL="https://market.otc.ru/Search/Requests"
MAX_BYTES=1_800_000
NUMBER=re.compile(r"[0-9]{5,10}\Z")
PATH=re.compile(r"/ProductRequestGroup/Index/([0-9]{5,10})\Z")
REQUIRED=2

def clean(text):
    return " ".join(text.split())

class Doc(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links=[]
        self.headings=[]
        self.visible=[]
        self.hidden=[]
        self.anchor=None
        self.heading=None
        self.cell=None
        self.cells=[]
        self.rows=[]

    def handle_starttag(self,tag,attrs):
        if tag in ("script","style","svg","template","noscript","iframe"):
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag=="a":
            self.anchor=[dict(attrs).get("href"),[]]
        if tag=="h1":
            self.heading=[]
        if tag=="tr":
            self.cells=[]
        if tag in ("td","th"):
            self.cell=[]

    def handle_data(self,data):
        if self.hidden:return
        self.visible.append(data)
        if self.anchor is not None:self.anchor[1].append(data)
        if self.heading is not None:self.heading.append(data)
        if self.cell is not None:self.cell.append(data)

    def handle_endtag(self,tag):
        if self.hidden:
            if self.hidden[-1]==tag:self.hidden.pop()
            return
        if tag=="a" and self.anchor is not None:
            self.links.append((self.anchor[0],clean(" ".join(self.anchor[1]))))
            self.anchor=None
        if tag=="h1" and self.heading is not None:
            self.headings.append(clean(" ".join(self.heading)))
            self.heading=None
        if tag in ("td","th") and self.cell is not None:
            self.cells.append(clean(" ".join(self.cell)))
            self.cell=None
        if tag=="tr" and self.cells:
            self.rows.append(self.cells)
            self.cells=[]

def parse(body):
    if type(body) is not bytes or not 0<len(body)<=MAX_BYTES or b"\0" in body:
        raise ValueError("Invalid public OTC body")
    doc=Doc()
    doc.feed(body.decode("utf-8-sig","replace"))
    doc.close()
    return doc

def canonical(href):
    if (type(href) is not str or not 0<len(href)<=450 or "\\" in href
            or any(ord(x)<32 or x.isspace() for x in href)):
        return None
    try:
        u=urlsplit(urljoin(LIST_URL,href))
        if (u.scheme!="https" or u.netloc!=HOST or u.username is not None
                or u.password is not None or u.port is not None
                or u.query or u.fragment):
            return None
        m=PATH.fullmatch(u.path)
        return (m[1],"https://"+HOST+m.group(0)) if m else None
    except ValueError:
        return None

def list_native(body):
    rows=[]
    seen=set()
    for href,text in parse(body).links:
        dest=canonical(href)
        if dest is None or dest[0] in seen:continue
        number,url=dest
        # First-party public listing anchors use a native OTC request number,
        # not an unverified EIS 11/19-digit identifier.
        m=re.search(r"(?<!\d)"+re.escape(number)+r"(?:-[A-Z0-9]{2,12})?(?!\d)",text)
        if m is None:continue
        title=clean(text[m.end():].lstrip(" –—:-№."))
        if not 8<=len(title)<=550 or not re.search("[А-Яа-яЁё]",title):
            continue
        seen.add(number)
        rows.append((number,title,url))
    if len(rows)<REQUIRED:
        raise ValueError("No two independently linked regional native OTC requests")
    return rows[:REQUIRED]

def verify_detail(body,number,title,url):
    if canonical(url)!=(number,url) or not NUMBER.fullmatch(number):
        raise ValueError("Unsafe OTC detail request")
    doc=parse(body)
    visible=clean(" ".join(doc.visible))
    if (not re.search(r"Закупка\s*№\s*"+re.escape(number)+r"(?!\d)",visible)
            or not any(title.casefold() in h.casefold() for h in doc.headings)):
        raise ValueError("Official independent OTC number/title mismatch")
    fields={}
    for cells in doc.rows:
        if len(cells)>=2:
            fields.setdefault(cells[0].strip().lower(),set()).add(cells[1].strip())
    if fields.get("номер закупки")!={number}:
        raise ValueError("Original public OTC numbered field absent")
    if fields.get("наименование закупки")!={title}:
        raise ValueError("Original public OTC title field absent")
    return number,title,url

async def live():
    with bounded_fetch(FetchPolicy(frozenset({HOST}),3,max_bytes=MAX_BYTES)):
        async with source_client(timeout=25,trust_env=False,follow_redirects=False,
            headers={"Accept":"text/html","User-Agent":"Mozilla/5.0"}) as client:
            resp=await client.get(LIST_URL)
            resp.raise_for_status()
            if "html" not in resp.headers.get("content-type","").lower():
                raise ValueError("OTC first-party request listing not HTML")
            cards=list_native(resp.content)
            verified=[]
            for number,title,url in cards:
                res=await client.get(url)
                res.raise_for_status()
                if "html" not in res.headers.get("content-type","").lower():
                    raise ValueError("OTC detail not independently public HTML")
                verified.append(verify_detail(res.content,number,title,url))
            return verified

def main():
    try:
        n=asyncio.run(live())
        print("RU_OTC_MARKET_ORIGINAL_DETAILS="+str(len(n)))
        print("RU_OTC_MARKET_LIVE=PASS_RESEARCH_ONLY")
        print("PRODUCTION_CHANGED=NO")
        return 0 if len(n)==2 else 2
    except (ValueError,ConnectorTransportError,httpx.HTTPError,OSError,TimeoutError) as error:
        print("RU_OTC_MARKET_LIVE=BLOCKED_"+type(error).__name__)
        if isinstance(error,ConnectorTransportError):
            print("RU_OTC_MARKET_RETRYABLE="+str(error.retryable))
        print("PRODUCTION_CHANGED=NO")
        return 2

if __name__=="__main__":
    raise SystemExit(main())
