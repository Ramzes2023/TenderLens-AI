"""Strict official Sverdlovsk Oblast small-purchase list evidence.

A visible public listing is research ONLY: never accept it as proven real
detail/SQL/search pipeline. HTML 200 without two genuine numbered notice
objects always fails. No cookies, JS, redirects, proxies, login or TLS bypass.
"""
from __future__ import annotations
import asyncio
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit
import httpx
from app.sources.http import bounded_fetch, FetchPolicy, source_client, ConnectorTransportError

HOST="torgi.egov66.ru"
LIST_URL="https://torgi.egov66.ru/smallpurchases/GzwSP/NoticesGrid"
MAX_BYTES=2_000_000
IDENTITY=re.compile(r"Реестровый\s+номер\s+(ИМЗ-20\d{2}-[12]-(?:044|223)-\d{6})")
OBJECT=re.compile(r"Объект\s+закупки\s+(.{8,250}?)\s+Заказчик",re.S)

class Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text=[]
        self.anchors=[]
        self.current=None
        self.hidden=[]

    def handle_starttag(self,tag,attrs):
        if tag in ("script","style","svg","template","noscript","iframe"):
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag=="a":
            self.current=[dict(attrs).get("href"),[]]

    def handle_data(self,data):
        if self.hidden:
            return
        self.text.append(data)
        if self.current is not None:
            self.current[1].append(data)

    def handle_endtag(self,tag):
        if self.hidden:
            if self.hidden[-1]==tag:
                self.hidden.pop()
            return
        if tag=="a" and self.current is not None:
            self.anchors.append((self.current[0]," ".join(" ".join(self.current[1]).split())))
            self.current=None


def listing_evidence(body:bytes):
    if type(body) is not bytes or not 0<len(body)<=MAX_BYTES or b"\x00" in body:
        raise ValueError("Empty/oversized Sverdlovsk response")
    page=Visible()
    page.feed(body.decode("utf-8-sig","replace"))
    page.close()
    text=" ".join(" ".join(page.text).split())
    locations=list(IDENTITY.finditer(text))
    original={}
    for i,m in enumerate(locations):
        end=locations[i+1].start() if i+1<len(locations) else len(text)
        card=text[m.end():end]
        details=OBJECT.search(card)
        if not details:
            continue
        title=" ".join(details.group(1).split())
        if (not re.search(r"[а-яА-ЯЁё]",title) or len(title)>250
                or m.group(1) in original and original[m.group(1)]!=title):
            raise ValueError("Invalid/ambiguous official numbered small purchase")
        original[m.group(1)]=title

    # For future independently confirmed page retrieval only; these counts
    # do NOT establish detail availability and no discovered URL is followed.
    safe_linked=0
    for href,label in page.anchors:
        if type(href) is not str or "\\" in href or len(href)>400:
            continue
        try:
            u=urlsplit(urljoin(LIST_URL,href))
        except ValueError:
            continue
        if (u.scheme=="https" and u.netloc==HOST and u.username is None and
                u.password is None and u.port is None and
                u.path.startswith("/smallpurchases/GzwSP/") and
                re.search(r"ИМЗ-20\d{2}-[12]-(?:044|223)-\d{6}",label)):
            safe_linked+=1
    return original,safe_linked


async def probe():
    with bounded_fetch(FetchPolicy(frozenset({HOST}),1,max_bytes=MAX_BYTES)):
        async with source_client(timeout=26,trust_env=False,follow_redirects=False,
            headers={"Accept":"text/html","User-Agent":"Mozilla/5.0"}) as client:
            response=await client.get(LIST_URL)
            response.raise_for_status()
            if "html" not in response.headers.get("content-type","").lower():
                raise ValueError("Official public small-purchases listing not HTML")
            notices,linked=listing_evidence(response.content)
            print("RU_SVERDLOVSK_PUBLIC_ORIGINAL_NUMBER_AND_TITLE_PAIRS="+str(len(notices)))
            print("RU_SVERDLOVSK_NUMBERED_FIRSTPARTY_LINKS="+str(linked))
            if len(notices)<2:
                raise ValueError("No two distinct genuine regional notices in live HTML")
            return notices


def main():
    try:
        records=asyncio.run(probe())
        print("RU_SVERDLOVSK_LIVE=PASS_LISTING_ONLY_NOT_INTEGRATED")
        print("RU_SVERDLOVSK_INDEPENDENT_DETAIL_VERIFIED=NO")
        print("PRODUCTION_CHANGED=NO")
        return 0 if len(records)>=2 else 2
    except (ValueError,ConnectorTransportError,httpx.HTTPError,TimeoutError,OSError) as e:
        print("RU_SVERDLOVSK_LIVE=BLOCKED_"+type(e).__name__)
        if isinstance(e,ConnectorTransportError):
            print("RU_SVERDLOVSK_RETRYABLE="+str(e.retryable))
        print("PRODUCTION_CHANGED=NO")
        return 2


if __name__=="__main__":
    raise SystemExit(main())
