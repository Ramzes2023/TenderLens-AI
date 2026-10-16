"""Read-only acceptance for Moldova's public licensed procurement marketplace.

Source: https://achizitii.md/ro/ live server-rendered purchases. Separate from
the currently failing government OCDS API. No redirects, secrets or bulk data.
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

HOST = "achizitii.md"
INDEX = "https://achizitii.md/ro/"
MAX_BYTES = 1024 * 1024
TIMEOUT = 14
DETAIL = re.compile(r"^/ro/public/tender/([1-9]\d{6,10})/$")
OCID = re.compile(r"ocds-b3wdp1-MD-\d{10,18}")
AMOUNT = re.compile(r"\b(?:\d{1,3}(?:[ ,.\u00a0]\d{3})+|\d{1,12})(?:[,.]\d{2})?\s*MDL\b")
DATE = re.compile(r"\b\d{1,2}\s+[a-zăîșț]{3,12}\s+20\d{2},?\s+\d{1,2}:\d{2}\b|\b\d{2}\.\d{2}\.20\d{2}\s+\d{2}:\d{2}\b", re.I)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, url):
        return None


def approved_href(href):
    parsed = urlsplit(href)
    if parsed.scheme and (parsed.scheme != "https" or parsed.hostname != HOST):
        return None
    if parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.fragment or parsed.query:
        return None
    match = DETAIL.fullmatch(parsed.path)
    return f"https://{HOST}{parsed.path}" if match else None


class Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tokens = []
        self.links = []
        self.hidden = 0
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "noscript"}:
            self.hidden += 1
        if self.hidden:
            return
        if tag == "a":
            href = approved_href(dict(attrs).get("href") or "")
            if href:
                self.links.append((len(self.tokens), href))
                self.current = href

    def handle_endtag(self, tag):
        if tag in {"script", "style", "template", "noscript"}:
            self.hidden = max(0, self.hidden-1)
        if tag == "a":
            self.current = None

    def handle_data(self, data):
        if not self.hidden:
            val = " ".join(data.split())
            if val:
                self.tokens.append((val, self.current))


def listings(raw):
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        return {"verified": False, "reason": "oversized_or_invalid"}
    parser = Visible()
    parser.feed(raw.decode("utf-8", errors="replace"))
    candidates = []
    seen = set()
    for i, (start, href) in enumerate(parser.links[:60]):
        if href in seen:
            continue
        seen.add(href)
        end = parser.links[i+1][0] if i+1<len(parser.links) else len(parser.tokens)
        chunk = parser.tokens[start:end]
        titles = [val for val, link in chunk if link == href and len(val) >= 6]
        excerpt = " ".join(val for val, _ in chunk)
        candidates.append({"link": href, "title": bool(titles),
                           "amount": bool(AMOUNT.search(excerpt)),
                           "date": bool(DATE.search(excerpt)),
                           "visible_tokens": len(chunk)})
    count = sum(x["title"] and x["amount"] and x["date"] for x in candidates)
    return {"verified": count >= 5, "matched_detail_links": len(candidates),
            "complete_listing_cards": count,
            "record_shapes": [{k:v for k,v in c.items() if k != "link"} for c in candidates[:5]],
            "approved_detail_urls": [c["link"] for c in candidates[:2]]}


def detail_evidence(raw):
    if not raw or len(raw)>MAX_BYTES:
        return {"verified": False, "reason": "invalid_detail_body"}
    parser = Visible()
    parser.feed(raw.decode("utf-8", errors="replace"))
    text = " ".join(v for v, _ in parser.tokens)
    ocids = OCID.findall(text)
    # Information about contracting authority + title and bid period are
    # visible without authentication, not extracted from script tags.
    valid = (len(ocids) >= 1
             and ("Denumirea" in text or "Denumirea" in raw.decode("utf-8", errors="replace"))
             and ("Data publicării" in text or "Perioada" in text)
             and bool(AMOUNT.search(text))
             and bool(DATE.search(text)))
    return {"verified": valid, "real_ocid_present": bool(ocids),
            "buyer_label_present": "Denumirea" in text,
            "amount_present": bool(AMOUNT.search(text)),
            "date_present": bool(DATE.search(text))}


def fetch(url, opener):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != HOST or parsed.port not in (None, 443):
        raise ValueError("Unapproved marketplace network target")
    request = Request(url, headers={"User-Agent": "VALYQON-readonly-procurement-source-check/1.0",
                                    "Accept": "text/html"})
    with opener.open(request, timeout=TIMEOUT) as response:
        if response.status != 200 or "html" not in response.headers.get("Content-Type", "").lower():
            raise ValueError("Unexpected public website response")
        raw = response.read(MAX_BYTES + 1)
        if len(raw)>MAX_BYTES:
            raise ValueError("Official marketplace response oversized")
        return raw


def main():
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    result = {"source": "md_achizitii_public", "index_verified": False,
              "detail_verified": False, "production_enabled": False}
    try:
        index = listings(fetch(INDEX, opener))
        result["index_verified"] = index["verified"]
        result["matched_detail_links"] = index.get("matched_detail_links", 0)
        result["complete_listing_cards"] = index.get("complete_listing_cards", 0)
        result["record_shapes"] = index.get("record_shapes", [])
        if index["verified"] and index.get("approved_detail_urls"):
            result.update({"detail_evidence": detail_evidence(fetch(index["approved_detail_urls"][0], opener))})
            result["detail_verified"] = result["detail_evidence"]["verified"]
    except HTTPError as exc:
        result.update({"reason": "http_error", "http_status": exc.code})
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        result["reason"] = type(exc).__name__
    result["verified"] = result["index_verified"] and result["detail_verified"]
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
