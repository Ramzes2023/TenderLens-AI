"""Live read-only discovery of the Belarus ICETRADE public tender catalogue.

Only current government-recognized icetrade.by pages; no login, proxy,
redirects, crawler bypass, production writes, or fabricated tender data.
A successful homepage alone does NOT validate public tender ingestion.
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

HOST = "icetrade.by"
PAGES = (
    "https://icetrade.by/",
    "https://icetrade.by/tenders8000/",
    "https://icetrade.by/tenders8000/search",
)
MAX_BYTES = 1024 * 1024
TIMEOUT = 12
DETAIL = re.compile(r"^/tenders8000/view/([1-9]\d{3,9})$")
DATE = re.compile(r"\b(?:[0-3]?\d[./][01]?\d[./]20\d{2}|20\d{2}[-.][01]?\d[-.][0-3]?\d)\b")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PublicLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.hidden = 0
        self.current_href = ""
        self.captured = []
        self.tenders = {}

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "template", "noscript"):
            self.hidden += 1
        if self.hidden:
            return
        if tag == "a":
            href = str(dict(attrs).get("href") or "")
            parsed = urlsplit(href)
            if (parsed.scheme in ("", "https") and parsed.hostname in (None, HOST)
                    and not parsed.username and not parsed.password and not parsed.query
                    and not parsed.fragment and DETAIL.fullmatch(parsed.path)):
                self.current_href = parsed.path
                self.tenders.setdefault(parsed.path, [])
                self.links.append(parsed.path)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "template", "noscript"):
            self.hidden = max(0, self.hidden - 1)
        if tag == "a":
            self.current_href = ""

    def handle_data(self, data):
        if self.hidden:
            return
        text = " ".join(data.split())
        if text:
            self.captured.append(text[:300])
            if self.current_href:
                self.tenders[self.current_href].append(text[:300])


def inspect(raw):
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ValueError("invalid or oversized page")
    p = PublicLinks()
    p.feed(raw.decode("utf-8", errors="replace"))
    rows = [(url, " ".join(labels)) for url, labels in p.tenders.items()]
    titled = [(url, title) for url, title in rows if len(title) >= 8]
    visible = " ".join(p.captured)
    return {"linked_tenders": len(rows), "title_linked_tenders": len(titled),
            "public_date_strings": len(DATE.findall(visible)),
            "candidate_detail_paths": [url for url, _ in titled[:3]],
            "verified_index": len(titled) >= 5}


def fetch(url, opener):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != HOST or parsed.port not in (None, 443)
            or parsed.username or parsed.password):
        raise ValueError("unapproved Belarus procurement host")
    request = Request(url, headers={"User-Agent":"VALYQON-public-procurement-verifier/1.0",
                                    "Accept":"text/html"})
    with opener.open(request, timeout=TIMEOUT) as response:
        if response.status != 200 or "html" not in response.headers.get("Content-Type", "").lower():
            raise ValueError("nonpublic or nonHTML procurement page")
        data = response.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:
            raise ValueError("oversized Belarus procurement response")
        return data


def main():
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    output = {"source":"by_icetrade_official", "verified": False,
              "production_activation_allowed": False, "tested_paths":[]}
    for url in PAGES:
        item={"path":urlsplit(url).path or "/", "verified_index":False}
        try:
            parsed=inspect(fetch(url,opener))
            item.update(parsed)
            if parsed["verified_index"] and parsed["candidate_detail_paths"]:
                detail=fetch("https://"+HOST+parsed["candidate_detail_paths"][0],opener)
                body=detail.decode("utf-8",errors="replace")
                item["verified_detail"]=(
                    "Закуп" in body and ("Срок" in body or "Дата" in body)
                    and len(body)>1000
                )
                item["verified"]=item["verified_index"] and item["verified_detail"]
        except HTTPError as e:
            item.update({"failure_kind":"HTTPError","status":e.code})
        except (URLError, OSError, TimeoutError, ValueError) as e:
            item["failure_kind"]=type(e).__name__
        output["tested_paths"].append(item)
    output["verified"]=any(x.get("verified") for x in output["tested_paths"])
    print(json.dumps(output,ensure_ascii=False,sort_keys=True))
    return 0 if output["verified"] else 1


if __name__=="__main__":
    sys.exit(main())
