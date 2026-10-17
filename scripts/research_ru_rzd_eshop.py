"""First-party Russian Railways e-shop price requests: genuine list to detail.

Research-only. Public official origin eshoprzd.ru, published price requests;
does not assume EIS 223-FZ mirrored source or count only website HTTP 200.
"""
from __future__ import annotations
import asyncio
from html.parser import HTMLParser
import re
import uuid
from urllib.parse import urljoin,urlsplit

import httpx
from app.sources.http import FetchPolicy,bounded_fetch,source_client,ConnectorTransportError

HOST="eshoprzd.ru"
LIST_URL="https://eshoprzd.ru/"
OTHER_LIST_URL="https://eshoprzd.ru/purchases"
PUBLIC_REST_URL="https://eshoprzd.ru/rest/"
DETAIL_PATH=re.compile(r"/purchases/([a-f0-9-]{36})\Z")
NOTICE_HEADING=re.compile(r"(?:Ценовой\s+запрос|Закупка)\s*№\s*([0-9]{5,18})\s+(.{8,600})\Z",re.I)
MAX_BYTES=1_800_000
MIN_LIVE=2


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links=[]
        self.headings=[]
        self._link=None
        self._heading=None
        self.hidden=[]
    def handle_starttag(self,tag,attrs):
        if tag in {"script","style","template","noscript","svg","iframe"}:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag=="a":
            self._link=[dict(attrs).get("href"),[]]
        if tag in {"h1","h2","h3","h4","h5"}:
            self._heading=[]
    def handle_data(self,data):
        if self.hidden:
            return
        if self._link is not None:
            self._link[1].append(data)
        if self._heading is not None:
            self._heading.append(data)
    def handle_endtag(self,tag):
        if self.hidden:
            if self.hidden[-1]==tag:
                self.hidden.pop()
            return
        if tag=="a" and self._link is not None:
            href,txt=self._link
            self.links.append((href," ".join(" ".join(txt).split())))
            self._link=None
        if tag in {"h1","h2","h3","h4","h5"} and self._heading is not None:
            self.headings.append(" ".join(" ".join(self._heading).split()))
            self._heading=None

def parse(body):
    if type(body) is not bytes or not 0<len(body)<=MAX_BYTES or b"\x00" in body:
        raise ValueError("Untrusted RZD listing/detail HTML")
    doc=VisibleHTML()
    doc.feed(body.decode("utf-8-sig","replace"))
    doc.close()
    return doc

def canonical(href):
    if type(href) is not str or not 0<len(href)<=450 or "\\" in href or any(ord(x)<32 or x.isspace() for x in href):
        return None
    try:
        url=urlsplit(urljoin(LIST_URL,href))
        m=DETAIL_PATH.fullmatch(url.path)
        if (url.scheme!="https" or url.netloc!=HOST or url.port is not None
                or url.username is not None or url.password is not None):
            return None
        if (url.query or url.fragment or not m
                or str(uuid.UUID(m.group(1)))!=m.group(1)):
            return None
        return LIST_URL+"purchases/"+m.group(1)
    except (ValueError,AttributeError):
        return None

def listed_purchases(body):
    seen=set()
    cards=[]
    for href,title in parse(body).links:
        url=canonical(href)
        if url is None or url in seen:
            continue
        # Public homepage link text may append /№ <number>; use only the
        # actual visible title, never synthesize title from UUID.
        title=re.sub(r"\s*/?\s*№\s*[0-9]{5,18}\s*$","",title).strip()
        if not 8<=len(title)<=600 or not re.search(r"[А-Яа-яЁё]",title):
            continue
        seen.add(url)
        cards.append((url,title))
    if len(cards)<MIN_LIVE:
        raise ValueError("Not two different public RZD purchase detail links")
    return cards[:MIN_LIVE]

def independently_verified_detail(body,url,title):
    if canonical(url)!=url:
        raise ValueError("Invalid RZD canonical procurement detail")
    matches=[NOTICE_HEADING.fullmatch(x) for x in parse(body).headings]
    matches=[m for m in matches if m]
    if len(matches)!=1:
        raise ValueError("No unique original RZD published price request heading")
    number,confirmed_title=matches[0].group(1),matches[0].group(2).strip()
    if title.casefold()!=confirmed_title.casefold():
        raise ValueError("Original title not corroborated by independent official detail")
    return(number,confirmed_title,url)

async def live():
    with bounded_fetch(FetchPolicy(frozenset({HOST}),5,max_bytes=MAX_BYTES)):
        async with source_client(timeout=25,trust_env=False,follow_redirects=False,
            headers={"Accept":"text/html","User-Agent":"Mozilla/5.0"}) as client:
            rows=[]
            for list_url in (LIST_URL,OTHER_LIST_URL,PUBLIC_REST_URL):
                page=await client.get(list_url)
                page.raise_for_status()
                if "html" not in page.headers.get("content-type","").lower():
                    raise ValueError("Official RZD first-party listing not HTML")
                doc=parse(page.content)
                print("RU_RZD_LIST_LINKS_TOTAL="+str(len(doc.links)))
                print("RU_RZD_LIST_CANONICAL_UUID_LINKS="+str(sum(
                    canonical(href) is not None for href,_ in doc.links
                )))
                print("RU_RZD_LIST_HEADINGS_TOTAL="+str(len(doc.headings)))
                try:
                    rows=listed_purchases(page.content)
                    print("RU_RZD_LIST_TWO_FIRSTPARTY_CARDS=YES")
                    break
                except ValueError:
                    print("RU_RZD_LIST_TWO_FIRSTPARTY_CARDS=NO")
                    continue
            if len(rows)<MIN_LIVE:
                raise ValueError("RZD official homepage and public listing did not reveal two canonical procurement links")
            verified=[]
            for url,title in rows:
                detail=await client.get(url)
                detail.raise_for_status()
                if "html" not in detail.headers.get("content-type","").lower():
                    raise ValueError("RZD official procurement detail not HTML")
                doc=parse(detail.content)
                print("RU_RZD_DETAIL_HEADINGS_TOTAL="+str(len(doc.headings)))
                try:
                    verified.append(independently_verified_detail(detail.content,url,title))
                    print("RU_RZD_DETAIL_ID_TITLE_CORROBORATED=YES")
                except ValueError:
                    print("RU_RZD_DETAIL_ID_TITLE_CORROBORATED=NO")
                    raise
            if len({x[0] for x in verified})!=MIN_LIVE:
                raise ValueError("RZD original notice numbers not unique")
            return verified

def main():
    try:
        records=asyncio.run(live())
        print("RU_RZD_ESHOP_INDEPENDENT_DETAILS="+str(len(records)))
        print("RU_RZD_ESHOP=PASS_RESEARCH_ONLY")
        print("PRODUCTION_CHANGED=NO")
        return 0 if len(records)==MIN_LIVE else 2
    except (ValueError,httpx.HTTPError,ConnectorTransportError,OSError,TimeoutError) as exc:
        print("RU_RZD_ESHOP=BLOCKED_"+type(exc).__name__)
        if isinstance(exc,ConnectorTransportError):
            print("RU_RZD_RETRYABLE="+str(exc.retryable))
        print("PRODUCTION_CHANGED=NO")
        return 2

if __name__=="__main__":
    raise SystemExit(main())
