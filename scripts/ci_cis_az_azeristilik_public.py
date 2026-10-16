"""Read-only Azerbaijani state agency public tender announcement verification.

Azəristiliktəchizat is a government-related contracting entity, not the
entire national eTender portal. Live procurement listing and each individual
2026 deadline must pass official HTTPS to qualify as a source candidate.
Never follow redirects or emit tender contents, credentials, production data.
"""
from __future__ import annotations
import json
import re
import ssl
import sys
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPSHandler, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

INDEX = "https://azeristilik.gov.az/en/imkanlar/tender-elanlari"
HOST = "azeristilik.gov.az"
MAX_BYTES = 768 * 1024
TIMEOUT = 14
POST = re.compile(r"^/(?:en/)?post/([a-z0-9-]{12,200})$")
DATE = re.compile(r"\b([0-3]\d\.[01]\d\.20\d{2})\b")
DEADLINE_LABEL = "Təkliflərin son təqdim olunma tarixi və vaxtı"
START_LABEL = "Müsabiqənin başlanma tarixi və vaxtı"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, hdrs, url):
        return None


class VisibleLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.tokens = []
        self.hidden = 0
        self.stack = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden += 1
        if tag == "a":
            self.stack.append(dict(attrs).get("href") or "")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden = max(0, self.hidden - 1)
        if tag == "a" and self.stack:
            self.stack.pop()

    def handle_data(self, value):
        if self.hidden:
            return
        value = " ".join(value.split())
        if value:
            self.tokens.append(value)
            if self.stack:
                self.links.append((self.stack[-1], value))


def public_link(raw):
    parsed = urlsplit(raw)
    if (parsed.scheme and parsed.scheme != "https"
            or parsed.hostname and parsed.hostname != HOST
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.fragment or parsed.query):
        return None
    return "https://" + HOST + parsed.path if POST.fullmatch(parsed.path) else None


def parse_list(raw):
    if not isinstance(raw, bytes) or len(raw)>MAX_BYTES:
        raise ValueError("Incorrect public list body")
    p = VisibleLinks()
    p.feed(raw.decode("utf-8", errors="replace"))
    result = {}
    for href,title in p.links:
        url = public_link(href)
        if url and len(title)>=18 and "satınalınmasına" in title.casefold():
            result[url] = title
    return tuple(result.keys())[:10]


def inspect_detail(raw):
    if not raw or len(raw)>MAX_BYTES:
        return {"verified": False, "reason": "missing_or_oversized"}
    parser = VisibleLinks()
    parser.feed(raw.decode("utf-8", errors="replace"))
    text = " ".join(parser.tokens)
    def date_after(label):
        i=text.find(label)
        if i<0:
            return None
        m=DATE.search(text[i+len(label):i+len(label)+160])
        if not m:
            return None
        try:
            return datetime.strptime(m.group(1), "%d.%m.%Y").date()
        except ValueError:
            return None
    start=date_after(START_LABEL)
    deadline=date_after(DEADLINE_LABEL)
    buyer="Satınalan təşkilatın adı" in text and ("Azəristiliktəchizat" in text)
    good=start is not None and deadline is not None and deadline>=start and buyer
    return {"verified":good, "has_buyer":buyer,"has_start":start is not None,
            "has_deadline":deadline is not None, "plausible_dates":good}


def fetch(url, opener):
    p=urlsplit(url)
    if p.scheme!="https" or p.hostname!=HOST or p.port not in (None,443):
        raise ValueError("Unapproved external host")
    request=Request(url,headers={"User-Agent":"VALYQON-public-gov-tender-audit/1.0","Accept":"text/html"})
    with opener.open(request,timeout=TIMEOUT) as response:
        if response.status!=200 or "html" not in response.headers.get("Content-Type","").lower():
            raise ValueError("Unexpected public page media/status")
        data=response.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:
            raise ValueError("Oversized public page")
        return data


def main():
    opener=build_opener(ProxyHandler({}),HTTPSHandler(context=ssl.create_default_context()),NoRedirect())
    output={"source":"az_azeristilik_agency","official_agency_only":True,
            "verified":False,"production_enabled":False}
    try:
        urls=parse_list(fetch(INDEX,opener))
        output["linked_posts"]=len(urls)
        inspected=[inspect_detail(fetch(url,opener)) for url in urls[:3]]
        output["detail_shape_evidence"]=inspected
        output["complete_live_notices"]=sum(x["verified"] for x in inspected)
        output["verified"]=output["complete_live_notices"]>=2
    except HTTPError as ex:
        output.update({"error":"http_error","status":ex.code})
    except (URLError,OSError,TimeoutError,ValueError) as ex:
        output["error"]=type(ex).__name__
    print(json.dumps(output,ensure_ascii=False,sort_keys=True))
    return 0 if output["verified"] else 1


if __name__=="__main__":
    sys.exit(main())
