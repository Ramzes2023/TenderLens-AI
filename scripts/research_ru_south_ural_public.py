"""Strict live original small-volume and commercial invitations: South Ural.

Research-only public listing -> two independent same-origin detail corroborations.
No fixtures in live check, secrets, personal data, login, redirects or TLS bypass.
"""
from __future__ import annotations
import asyncio
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit
import httpx
from app.sources.http import FetchPolicy, bounded_fetch, source_client, ConnectorTransportError

HOST="www.vendorportal.ru"
LIST_URL="https://www.vendorportal.ru/Market/OfferInvitationOpen"
DETAIL_PREFIX="https://www.vendorportal.ru/Market/OfferInvitationOpen/View/"
MAX_BYTES=1_800_000
RECORDS=2
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

def parse_public_listing(body):
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
    return found[:RECORDS]

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

async def live():
    with bounded_fetch(FetchPolicy(frozenset({HOST}),3,max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=24, follow_redirects=False,trust_env=False,
            headers={"Accept":"text/html","User-Agent":"Mozilla/5.0"},
        ) as client:
            resp=await client.get(LIST_URL)
            resp.raise_for_status()
            if "html" not in resp.headers.get("content-type","").lower():
                raise ValueError("Listing is not HTML")
            rows=parse_public_listing(resp.content)
            verified=[]
            for number,title,url in rows:
                page=await client.get(url)
                page.raise_for_status()
                if "html" not in page.headers.get("content-type","").lower():
                    raise ValueError("Detail is not HTML")
                verified.append(verify_public_detail(page.content,number,title,url))
            return verified

def main():
    try:
        results=asyncio.run(live())
        print("RU_SOUTH_URAL_INDEPENDENT_DETAILS="+str(len(results)))
        print("RU_SOUTH_URAL_LIVE=PASS_RESEARCH_ONLY" if len(results)==2 else "RU_SOUTH_URAL_LIVE=BLOCKED")
        print("PRODUCTION_CHANGED=NO")
        return 0 if len(results)==2 else 2
    except (ConnectorTransportError,ValueError,httpx.HTTPError,TimeoutError,OSError) as error:
        print("RU_SOUTH_URAL_LIVE=BLOCKED_"+type(error).__name__)
        if isinstance(error,ConnectorTransportError):
            print("RU_SOUTH_URAL_RETRYABLE="+str(error.retryable))
        print("PRODUCTION_CHANGED=NO")
        return 2

if __name__=="__main__":
    raise SystemExit(main())
