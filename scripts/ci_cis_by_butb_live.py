"""Read-only Belarusian Universal Commodity Exchange procurement acceptance.

Official licensed exchange platform: zakupki.butb.by.
Avoid icetrade.by HTTPS chain errors without disabling TLS.
Treat page accessibility as diagnostics, not proof of tender ingestion.
"""
from __future__ import annotations
import json
import re
import ssl
import sys
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener
from urllib.error import HTTPError, URLError

HOST = "zakupki.butb.by"
URLS = (
    "https://zakupki.butb.by/auctions/restrauctions.html",
    "https://zakupki.butb.by/auctions/",
    "https://zakupki.butb.by/",
)
MAX_BODY = 1024*1024
TIMEOUT = 12
AUCTION = re.compile(r"\bAU20\d{12,16}\b")
DATE = re.compile(r"\b(?:20\d{2}[.\-/]\d\d[.\-/]\d\d|\d\d[.\-/]\d\d[.\-/]20\d{2})\b")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PublicAuctionHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.texts = []
        self.links = []
        self.tables = 0
        self.rows = 0
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "noscript"}:
            self.hidden += 1
        if self.hidden:
            return
        if tag == "table":
            self.tables += 1
        if tag == "tr":
            self.rows += 1
        if tag == "a":
            raw = str(dict(attrs).get("href") or "")
            p = urlsplit(raw)
            if (p.scheme in ("", "https") and p.hostname in (None, HOST)
                    and not p.query and not p.fragment and not p.username and not p.password):
                self.links.append({"route_len": len(p.path),
                                   "auction_route": ("auction" in p.path.lower() or "purchase" in p.path.lower()),
                                   "path": p.path[:130]})

    def handle_endtag(self, tag):
        if tag in {"script", "style", "template", "noscript"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            text = " ".join(data.split())
            if text:
                self.texts.append(text[:400])


def inspect(raw):
    if not raw or len(raw)>MAX_BODY:
        return {"verified": False, "reason": "empty_or_oversized"}
    p=PublicAuctionHTML()
    p.feed(raw.decode("utf-8", errors="replace"))
    text=" ".join(p.texts)
    ids=sorted(set(AUCTION.findall(text)))
    dated=DATE.findall(text)
    matched=[link for link in p.links if link["auction_route"]]
    return {
        "verified": len(ids)>=5 and len(matched)>=5 and bool(dated),
        "tender_identifiers":len(ids), "date_strings":len(dated),
        "tables":p.tables, "table_rows":p.rows,
        "same_host_auction_links":len(matched),
        "approved_route_shapes":[{"path_length":x["route_len"],
                                  "auction_path":x["auction_route"],
                                  "path":x["path"]} for x in matched[:5]],
    }


def fetch(url,opener):
    p=urlsplit(url)
    if p.scheme!="https" or p.hostname!=HOST or p.username or p.password or p.port not in (None,443):
        raise ValueError("unapproved official exchange host")
    req=Request(url,headers={"User-Agent":"VALYQON-verified-public-procurement/1.0",
                             "Accept":"text/html"})
    with opener.open(req,timeout=TIMEOUT) as response:
        if response.status!=200 or "html" not in response.headers.get("Content-Type","").lower():
            raise ValueError("unexpected market content type/status")
        body=response.read(MAX_BODY+1)
        if len(body)>MAX_BODY:
            raise ValueError("body too large")
        return body


def main():
    opener=build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    out={"source":"by_butb_public", "verified":False,
         "production_enabled":False, "official_pages":[]}
    for url in URLS:
        row={"route":urlsplit(url).path or "/", "verified":False}
        try:
            data=inspect(fetch(url,opener))
            row.update(data)
        except HTTPError as err:
            row.update({"error_kind":"HTTPError","status":err.code})
        except URLError as err:
            row.update({"error_kind":"URLError","reason_class":type(err.reason).__name__})
        except (OSError,TimeoutError,ValueError) as err:
            row["error_kind"]=type(err).__name__
        out["official_pages"].append(row)
    out["verified"]=any(row.get("verified") for row in out["official_pages"])
    print(json.dumps(out,ensure_ascii=False,sort_keys=True))
    return 0 if out["verified"] else 1


if __name__=="__main__":
    sys.exit(main())
