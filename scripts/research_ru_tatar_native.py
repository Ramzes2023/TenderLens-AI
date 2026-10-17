"""Tatarstan own native (DP-numbered) procurement, excluding mirrored EIS 223-FZ.

Read-only research. No 200-only success; two genuine currently linked list
notices must independently confirm first-party detail title and local ID.
"""
from __future__ import annotations
import asyncio
from html.parser import HTMLParser
import re
from urllib.parse import parse_qsl,urljoin,urlsplit
import httpx
from app.sources.http import FetchPolicy,bounded_fetch,source_client,ConnectorTransportError

HOST="etpzakupki.tatar"
LIST="https://etpzakupki.tatar/app"
LIMIT=6
REQUIRED=2
MAX_BYTES=1_800_000
NATIVE_ID=re.compile(r"\d{8,12}DP\Z")
TOKEN=re.compile(r"Score[a-z0-9]{12,80}\Z")

class Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links=[]
        self.visible=[]
        self.headings=[]
        self.anchor=None
        self.h=None
        self.hidden=[]
    def handle_starttag(self,t,attrs):
        if t in {"script","style","svg","noscript","template","iframe"}:
            self.hidden.append(t)
        if self.hidden:
            return
        if t=="a":
            self.anchor=[dict(attrs).get("href"),[]]
        if t in {"h1","h2","h3","h4"}:
            self.h=[]
    def handle_data(self,d):
        if self.hidden:
            return
        self.visible.append(d)
        if self.anchor is not None:
            self.anchor[1].append(d)
        if self.h is not None:
            self.h.append(d)
    def handle_endtag(self,t):
        if self.hidden:
            if self.hidden[-1]==t:
                self.hidden.pop()
            return
        if t=="a" and self.anchor is not None:
            href,parts=self.anchor
            self.links.append((href," ".join(" ".join(parts).split())))
            self.anchor=None
        if t in {"h1","h2","h3","h4"} and self.h is not None:
            self.headings.append(" ".join(" ".join(self.h).split()))
            self.h=None

def html(body):
    if type(body) is not bytes or not 0<len(body)<=MAX_BYTES or b"\0" in body:
        raise ValueError("Invalid Tatarstan official first-party HTML")
    p=Visible()
    p.feed(body.decode("utf-8-sig","replace"))
    p.close()
    return p

def canonical(href):
    if type(href) is not str or not 0<len(href)<=450 or "\\" in href or any(ord(x)<32 or x.isspace() for x in href):
        return None
    try:
        u=urlsplit(urljoin(LIST,href))
        pairs=parse_qsl(u.query,keep_blank_values=True,strict_parsing=True)
        if (u.scheme!="https" or u.netloc!=HOST
                or u.port is not None or u.username is not None or u.password is not None
                or u.fragment or u.path!="/app/OfferCard/page"
                or len(pairs)!=1 or pairs[0][0]!="OfferCard.offerUUID"
                or not TOKEN.fullmatch(pairs[0][1])):
            return None
        return "https://"+HOST+"/app/OfferCard/page?OfferCard.offerUUID="+pairs[0][1]
    except ValueError:
        return None

def list_cards(data):
    cards,seen=[],set()
    for href,title in html(data).links:
        url=canonical(href)
        if url is None or url in seen or not 8<=len(title)<=650 or not re.search(r"[а-яА-ЯЁё]",title):
            continue
        seen.add(url)
        cards.append((url,title))
    if len(cards)<REQUIRED:
        raise ValueError("Fewer than two official current first-party Tatarstan cards")
    return cards[:LIMIT]

def verify_detail(data,url,title):
    if canonical(url)!=url:
        raise ValueError("Noncanonical Tatarstan official detail")
    page=html(data)
    text=" ".join(" ".join(page.visible).split())
    # Reject all EIS mirrored 11-digit 223-FZ ids, even if a marketplace
    # has a distinct local DP number; the upstream original is EIS.
    if re.search(r"Реестровый\s+номер\s+3\d{10}\s+ЕИС",text):
        raise ValueError("Syndicated federal EIS 223-FZ notice")
    m=re.search(r"Номер\s+процедуры\s+(\d{8,12}DP)\b",text)
    if not m or not NATIVE_ID.fullmatch(m.group(1)):
        raise ValueError("Not a uniquely published local DP number")
    if not re.search(r"Вид\s+торговой\s+процедуры\s+(?:Закупка|Малая закупка)\b",text):
        raise ValueError("Not native public procurement")
    if not re.search(r"Наименование\s+закупки\s+"+re.escape(title)+r"(?:\s|$)",text,re.I):
        raise ValueError("Native detail does not corroborate exact listing subject")
    return(m.group(1),title,url)

async def live():
    with bounded_fetch(FetchPolicy(frozenset({HOST}),LIMIT+1,max_bytes=MAX_BYTES)):
        async with source_client(timeout=24,follow_redirects=False,trust_env=False,
            headers={"Accept":"text/html","User-Agent":"Mozilla/5.0"}) as client:
            page=await client.get(LIST)
            page.raise_for_status()
            if "html" not in page.headers.get("content-type","").lower():
                raise ValueError("Native published listing not HTML")
            links=list_cards(page.content)
            print("RU_TATAR_VISIBLE_FIRSTPARTY_CARD_LINKS="+str(len(links)))
            confirmed=[]
            for url,title in links:
                detail=await client.get(url)
                detail.raise_for_status()
                if "html" not in detail.headers.get("content-type","").lower():
                    continue
                try:
                    item=verify_detail(detail.content,url,title)
                    if item[0] not in {v[0] for v in confirmed}:
                        confirmed.append(item)
                except ValueError:
                    # Mirrored EIS original explicitly excluded, not counted.
                    continue
                if len(confirmed)==REQUIRED:
                    break
            if len(confirmed)<REQUIRED:
                raise ValueError("Insufficient genuine independent native DP Tatarstan detail proofs")
            return confirmed

def main():
    try:
        n=asyncio.run(live())
        print("RU_TATAR_NATIVE_DP_CORROBORATED="+str(len(n)))
        print("RU_TATAR_NATIVE_DP=PASS_RESEARCH_ONLY")
        print("PRODUCTION_CHANGED=NO")
        return 0 if len(n)==REQUIRED else 2
    except (ConnectorTransportError,ValueError,httpx.HTTPError,TimeoutError,OSError) as e:
        print("RU_TATAR_NATIVE_DP=BLOCKED_"+type(e).__name__)
        print("PRODUCTION_CHANGED=NO")
        return 2

if __name__=="__main__":
    raise SystemExit(main())
