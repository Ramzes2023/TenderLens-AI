"""Read-only first-party STAN-Torgi commercial tender discovery (not EIS mirrors)."""
from __future__ import annotations
import asyncio
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit

import httpx
from app.sources.http import FetchPolicy, bounded_fetch, source_client, ConnectorTransportError

HOST = "stantorgi.ru"
LIST_URL = "https://stantorgi.ru/etp"
MAX_BYTES = 1_800_000
DETAIL = re.compile(r"/etp/[A-Za-z0-9]{8}")
NUMBER = re.compile(r"[А-ЯA-Z]{1,4}-20\d{2}-\d{6}")
MAX_DETAILS = 2


def norm(value):
    return " ".join(value.split())


class ReadHtml(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.headings, self.visible = [], [], []
        self.link = self.h1 = None
        self.hidden = []
    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "svg", "template", "noscript"}:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag == "a":
            self.link = [dict(attrs).get("href"), []]
        if tag == "h1":
            self.h1 = []
    def handle_data(self, data):
        if self.hidden:
            return
        self.visible.append(data)
        if self.link is not None:
            self.link[1].append(data)
        if self.h1 is not None:
            self.h1.append(data)
    def handle_endtag(self, tag):
        if self.hidden:
            if self.hidden[-1] == tag:
                self.hidden.pop()
            return
        if tag == "a" and self.link is not None:
            self.links.append((self.link[0], norm(" ".join(self.link[1]))))
            self.link = None
        if tag == "h1" and self.h1 is not None:
            self.headings.append(norm(" ".join(self.h1)))
            self.h1 = None


def parse_doc(data):
    if type(data) is not bytes or not 0 < len(data) <= MAX_BYTES or b"\x00" in data:
        raise ValueError("Unsafe STAN-Torgi public HTML")
    doc=ReadHtml()
    doc.feed(data.decode("utf-8-sig","replace"))
    doc.close()
    return doc


def canonical(value):
    if type(value) is not str or not 0 < len(value) <= 300 or "\\" in value or any(c.isspace() or ord(c) < 32 for c in value):
        return None
    try:
        url=urlsplit(urljoin(LIST_URL,value))
        if (url.scheme != "https" or url.netloc != HOST or url.port is not None
                or url.username is not None or url.password is not None
                or url.query or url.fragment or not DETAIL.fullmatch(url.path)):
            return None
        return LIST_URL + "/" + url.path.rsplit("/",1)[-1]
    except ValueError:
        return None


def parse_list(data):
    cards={}
    for href,text in parse_doc(data).links:
        url=canonical(href)
        if not url:
            continue
        c=cards.setdefault(url,{"numbers":set(),"titles":set(),"eis":False})
        if re.search(r"(?<!\d)3\d{10}(?!\d)",text):
            c["eis"]=True
        if text.startswith("№ ") and NUMBER.fullmatch(text[2:].strip()):
            c["numbers"].add(text[2:].strip())
        elif 12 <= len(text) <= 600 and re.search(r"[А-Яа-яЁё]",text):
            c["titles"].add(text)
    valid=[]
    for url,c in cards.items():
        if not c["eis"] and len(c["numbers"])==1 and len(c["titles"])==1:
            valid.append((next(iter(c["numbers"])),next(iter(c["titles"])),url))
    if len(valid) < MAX_DETAILS:
        raise ValueError("Insufficient independent commercial procedure links")
    return valid[:MAX_DETAILS]


def verify_detail(data, number, title, url):
    if canonical(url)!=url or not NUMBER.fullmatch(number):
        raise ValueError("Noncanonical procedure identity")
    doc=parse_doc(data)
    visible=norm(" ".join(doc.visible))
    if len(doc.headings)!=1 or doc.headings[0].casefold()!=title.casefold():
        raise ValueError("Commercial listing/detail title mismatch")
    if "Коммерческая закупка" not in visible:
        raise ValueError("EIS or unproven commercial procedure")
    if not re.search(r"Номер процедуры\s+"+re.escape(number)+r"(?![\dA-Za-z])",visible):
        raise ValueError("Commercial procedure ID missing on independent detail")
    return number,title,url


async def probe():
    with bounded_fetch(FetchPolicy(frozenset({HOST}), MAX_DETAILS+1, max_bytes=MAX_BYTES)):
        async with source_client(timeout=25,trust_env=False,follow_redirects=False,
            headers={"Accept":"text/html","User-Agent":"Mozilla/5.0"}) as client:
            res=await client.get(LIST_URL)
            res.raise_for_status()
            if "html" not in res.headers.get("content-type","").lower():
                raise ValueError("Official STAN list not HTML")
            records=[]
            for number,title,url in parse_list(res.content):
                page=await client.get(url)
                page.raise_for_status()
                if "html" not in page.headers.get("content-type","").lower():
                    raise ValueError("Official STAN detail not HTML")
                records.append(verify_detail(page.content,number,title,url))
            return records


def main():
    try:
        data=asyncio.run(probe())
    except (ValueError,ConnectorTransportError,httpx.HTTPStatusError,httpx.TransportError) as exc:
        print("RU_STAN_LIVE=BLOCKED_"+type(exc).__name__)
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_STAN_COMMERCIAL_VERIFIED_DETAILS="+str(len(data)))
    print("RU_STAN_LIVE=PASS_RESEARCH_ONLY")
    print("PRODUCTION_CHANGED=NO")
    return 0 if len(data)==MAX_DETAILS else 2

if __name__=="__main__":
    raise SystemExit(main())
