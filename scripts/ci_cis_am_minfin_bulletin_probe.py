"""Strict read-only Armenian Ministry of Finance procurement bulletin exploration.

Does NOT integrate a source, treat archived notices as open, or relax transport
policy. Only bounded HTTPS official server-rendered data proves feasibility.
"""
from __future__ import annotations
import asyncio
from collections import Counter
from html.parser import HTMLParser
import json
import re
from urllib.parse import urlsplit
from app.sources.http import FetchPolicy, bounded_fetch, source_client

HOST = "procurement.am"
URLS = (
    "https://procurement.am/en/page/announcement_and_invitation_of_an_electronic_auction/",
    "https://procurement.am/en/page/announcement_and_invitation_of_an_open_tender/",
)
MAX_BYTES = 1_500_000
STAMP = re.compile(r"Published\s+20\d{2}-\d{2}-\d{2}", re.I)

class PublicStructure(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.texts = []
        self.tags = Counter()
        self.ignore = 0
        self.href = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        self.tags[tag] += 1
        if tag in {"script","style","noscript","template"}:
            self.ignore += 1
        if tag == "a" and self.ignore == 0:
            self.href = dict(attrs).get("href","")
            self.parts = []

    def handle_data(self, data):
        if self.ignore:
            return
        value = " ".join(data.split())
        if not value:
            return
        if self.href is not None:
            self.parts.append(value)
        if len(value) > 14 and len(self.texts) < 1200:
            self.texts.append(value[:250])

    def handle_endtag(self, tag):
        if tag == "a" and self.href is not None:
            self.links.append((self.href, " ".join(self.parts)))
            self.href = None
            self.parts = []
        if tag in {"script","style","noscript","template"} and self.ignore:
            self.ignore -= 1

def scrub_link(href):
    try:
        p=urlsplit(href)
        if (p.scheme and p.scheme != "https") or p.username or p.password or p.query or p.fragment:
            return None
        return {"host":p.hostname or HOST,"path_prefix":p.path[:120]}
    except ValueError:
        return None

async def main():
    report=[]
    for url in URLS:
        page={"source":HOST,"path":urlsplit(url).path,"enabled":False}
        try:
            with bounded_fetch(FetchPolicy(frozenset({HOST}), 1, max_bytes=MAX_BYTES)):
                async with source_client(timeout=20, follow_redirects=False, trust_env=False) as client:
                    response=await client.get(url)
            page["status"]=response.status_code
            page["html"]=response.status_code==200 and "html" in response.headers.get("content-type","").lower()
            if not page["html"]:
                report.append(page)
                continue
            dom=PublicStructure()
            dom.feed(response.text)
            document_links=[(h,label) for h,label in dom.links
                            if any(x in h.casefold() for x in (".pdf",".doc",".zip","/media/","/download/"))]
            page.update({"bytes":len(response.content),
                         "text_blocks":len(dom.texts),
                         "notice_date_indicators":sum("Published 2026" in t for t in dom.texts),
                         "document_links":len(document_links),
                         "candidate_link_hosts":dict(Counter((scrub_link(h) or {}).get("host","rejected")
                                                             for h,_ in document_links)),
                         "sample_public_titles":[t for t in dom.texts if any(w in t.casefold()
                           for w in ("municipality","community","համայնքապետ","համայնքի"))][:6],
                         "document_link_shapes":[scrub_link(h) for h,_ in document_links[:6]],
                         "tags":{k:dom.tags[k] for k in ("article","li","div","p","a","time","section")},
                         "production_enabled":False})
            report.append(page)
        except Exception as error:
            report.append({**page,"failure_type":type(error).__name__,"verified":False})
    ok=any(v.get("html") and v.get("document_links",0)>=3
           and v.get("notice_date_indicators",0)>=3 for v in report)
    print(json.dumps({"passed":ok,"official_listing_profiles":report,
                      "no_live_connector_claim":True},ensure_ascii=False,sort_keys=True))
    return 0 if ok else 1

if __name__=="__main__":
    raise SystemExit(asyncio.run(main()))
