"""Read-only, fail-closed official Azerbaijani heating entity public tender discovery.

This is a single public contracting entity, not the national AZ eTender API.
No production registration, redirects, TLS bypass, credentials, proxies, or DB.
"""
from __future__ import annotations

import json
import re
import ssl
import sys
from datetime import datetime
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

HOST = "azeristilik.gov.az"
INDEXES = (
    "https://azeristilik.gov.az/az/imkanlar/tender-elanlari",
    "https://azeristilik.gov.az/en/imkanlar/tender-elanlari",
    "https://azeristilik.gov.az/ru/imkanlar/tender-elanlari",
)
SAMPLE = "https://azeristilik.gov.az/post/is-yerlerinin-attestasiyasinin-kecirilmesi-xidmetinin-satinalinmasina-dair-kotirovka-sorgusu-elan-edir"
POST = re.compile(r"/(?:(?:az|en|ru)/)?post/([a-z0-9-]{12,200})$")
DATE = re.compile(r"\b([0-3]\d\.[01]\d\.20\d{2})\b")
START_LABEL = "Müsabiqənin başlanma tarixi və vaxtı"
END_LABEL = "Təkliflərin son təqdim olunma tarixi və vaxtı"
MAX_BYTES = 768 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, url):
        return None


class Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.tokens = []
        self.hrefs = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template"):
            self.hidden += 1
        if tag == "a":
            self.hrefs.append(dict(attrs).get("href") or "")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template"):
            self.hidden = max(0, self.hidden - 1)
        if tag == "a" and self.hrefs:
            self.hrefs.pop()

    def handle_data(self, value):
        if self.hidden:
            return
        text = " ".join(value.split())
        if text:
            self.tokens.append(text)
            if self.hrefs:
                self.links.append((self.hrefs[-1], text))


def approved_post(value):
    try:
        p = urlsplit(value)
        if (p.scheme not in ("", "https") or p.hostname not in (None, HOST)
            or p.username or p.password or p.query or p.fragment
            or p.port not in (None, 443) or not POST.fullmatch(p.path)):
            return None
        return "https://" + HOST + p.path
    except ValueError:
        return None


def extract_index(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        return ()
    parser = Visible()
    parser.feed(raw.decode("utf-8", errors="replace"))
    notices = {}
    for href, title in parser.links:
        url = approved_post(href)
        if url and len(title) >= 18 and ("satına" in title.casefold() or "tender" in title.casefold()):
            notices[url] = title
    return tuple(notices.keys())[:10]


def detail_fields(raw):
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
        return {"verified": False, "reason": "invalid_html"}
    parser = Visible()
    parser.feed(raw.decode("utf-8", errors="replace"))
    text = " ".join(parser.tokens)

    def get_date(label):
        offset = text.find(label)
        if offset < 0:
            return None
        match = DATE.search(text[offset + len(label):offset + len(label) + 160])
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%d.%m.%Y").date()
        except ValueError:
            return None

    start, deadline = get_date(START_LABEL), get_date(END_LABEL)
    buyer = "Satınalan təşkilatın adı" in text and "Azəristiliktəchizat" in text
    is_2026 = bool(start and start.year == 2026)
    good = bool(start and deadline and buyer and is_2026 and deadline >= start)
    return {"verified": good, "buyer": buyer, "publication_date": bool(start),
            "submission_deadline": bool(deadline), "date_order": bool(start and deadline and deadline >= start)}


def fetch(url, opener):
    p = urlsplit(url)
    if (p.scheme != "https" or p.hostname != HOST or p.port not in (None, 443)
        or p.username or p.password or p.query or p.fragment):
        raise ValueError("invalid official HTTPS URL")
    req = Request(url, headers={"Accept": "text/html", "User-Agent": "VALYQON-public-tender-audit/1.0"})
    with opener.open(req, timeout=12) as resp:
        if resp.status != 200 or "html" not in resp.headers.get("content-type", "").lower():
            raise ValueError("not verified HTML")
        if resp.url != url:
            raise ValueError("redirected official content")
        body = resp.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("oversized HTML")
        return body


def check_linked_details(links, opener):
    """Probe at most four original cards independently and fail closed per card.

    A failed individual request or malformed card cannot become evidence.
    Log only categories/counts, never tender data, URLs or response bodies.
    """
    result = {"checked_details": 0, "complete_details": 0,
              "rejected_details": 0, "blocking_detail_errors": 0,
              "detail_http_errors": {}, "detail_network_errors": {}}
    for url in links[:4]:
        result["checked_details"] += 1
        try:
            fields = detail_fields(fetch(url, opener))
            if fields["verified"]:
                result["complete_details"] += 1
            else:
                result["rejected_details"] += 1
        except HTTPError as exc:
            key = str(exc.code) if exc.code in (401, 403, 404, 410, 429, 500, 502, 503, 504) else "other"
            result["detail_http_errors"][key] = result["detail_http_errors"].get(key, 0) + 1
            if exc.code not in (403, 404, 410):
                result["blocking_detail_errors"] += 1
        except URLError as exc:
            key = type(exc.reason).__name__
            if key not in {"ConnectionResetError", "TimeoutError", "ConnectionRefusedError",
                           "SSLCertVerificationError", "SSLError"}:
                key = "OtherNetworkError"
            result["detail_network_errors"][key] = result["detail_network_errors"].get(key, 0) + 1
            if isinstance(exc.reason, ssl.SSLError):
                result["blocking_detail_errors"] += 1
        except (TimeoutError, OSError, ValueError, ssl.SSLError) as exc:
            key = type(exc).__name__ if type(exc).__name__ in {
                "TimeoutError", "ConnectionResetError", "ValueError", "SSLError",
                "SSLCertVerificationError",
            } else "OtherError"
            result["detail_network_errors"][key] = result["detail_network_errors"].get(key, 0) + 1
            if isinstance(exc, ssl.SSLError):
                result["blocking_detail_errors"] += 1
    return result


def run():
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    out = {"source": "az_azeristilik_agency", "official_entity_only": True,
           "registered_in_production": False, "verified": False, "locales": []}
    for index_url in INDEXES:
        item = {"language": urlsplit(index_url).path.split("/")[1], "index_verified": False}
        try:
            links = extract_index(fetch(index_url, opener))
            item["discovered_posts"] = len(links)
            item["index_verified"] = len(links) >= 2
            item.update(check_linked_details(links, opener))
            # A source is verified only if the listing is official AND at
            # least one independently fetched original has mandatory buyer,
            # publication and deadline. Failed cards never contribute.
            item["verified"] = (item["index_verified"]
                                and item["complete_details"] >= 1
                                and item["blocking_detail_errors"] == 0)
        except HTTPError as exc:
            item.update(error="HTTPError", http_status=exc.code)
        except URLError as exc:
            item.update(error="URLError", reason_class=type(exc.reason).__name__)
        except (TimeoutError, OSError, ValueError, ssl.SSLError) as exc:
            item["error"] = type(exc).__name__
        out["locales"].append(item)
        if item.get("verified"):
            out["verified"] = True
            break
    if not out["verified"]:
        # Diagnose official individual detail only; this NEVER constitutes
        # working source discovery or justifies enabling an adapter.
        try:
            out["individual_detail_only"] = detail_fields(fetch(SAMPLE, opener))
        except HTTPError as exc:
            out["detail_http_status"] = exc.code
        except URLError as exc:
            out["detail_error"] = type(exc.reason).__name__
        except (TimeoutError, OSError, ValueError, ssl.SSLError) as exc:
            out["detail_error"] = type(exc).__name__
    print(json.dumps(out, ensure_ascii=False, sort_keys=True))
    return int(not out["verified"])


if __name__ == "__main__":
    sys.exit(run())
