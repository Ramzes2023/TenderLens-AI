"""Read-only Moldovan procurement marketplace listing inspection.

Portal: https://mtender.md/Home/Achizitii, publicly announced alongside the
MTender government portal on mtender.gov.md. Real HTML only, no mocks, no secrets.
This is a published procurement PLATFORM, distinct from the inaccessible OCDS API.
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

URL = "https://mtender.md/Home/Achizitii"
MAX_BYTES = 1024 * 1024
TIMEOUT = 16
PATH = re.compile(r"^/Home/TenderInfo/(ocds-b3wdp1-MD-\d{10,18})$", re.I)
AMOUNT = re.compile(r"\b\d{1,3}(?:,\d{3})*\.\d{2}\s+MDL\b")
DATE = re.compile(r"\b\d{2}\.\d{2}\.20\d{2}\s+\d{2}:\d{2}\b")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class VisibleLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tokens = []
        self.links = []
        self.hidden = 0
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "template", "noscript"):
            self.hidden += 1
        if self.hidden:
            return
        if tag == "a":
            a = dict(attrs)
            href = str(a.get("href") or "")
            if PATH.fullmatch(href):
                self.links.append((len(self.tokens), href))
                self.current = href

    def handle_endtag(self, tag):
        if tag in ("script", "style", "template", "noscript"):
            self.hidden = max(0, self.hidden - 1)
        if tag == "a":
            self.current = None

    def handle_data(self, data):
        if not self.hidden:
            val = " ".join(data.split())
            if val:
                self.tokens.append((val, self.current))


def summarize(raw):
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        return {"verified": False, "reason": "oversized_or_wrong_type"}
    parser = VisibleLinks()
    parser.feed(raw.decode("utf-8", errors="replace"))
    items = []
    for i, (start, href) in enumerate(parser.links[:15]):
        end = parser.links[i+1][0] if i+1 < len(parser.links) else len(parser.tokens)
        tokens = parser.tokens[start:end]
        link_titles = [value for value, link in tokens if link == href]
        text = " ".join(value for value, link in tokens)
        enough_title = bool(link_titles and len(" ".join(link_titles)) >= 7)
        amounts = AMOUNT.findall(text)
        dates = DATE.findall(text)
        buyer_labels = [value for value, _ in tokens if value.casefold() not in (
            "denumirea obiectului achiziției", "valoarea estimată", "statut", "data publicării",
        )]
        # Structural evidence only. Buyer validated by explicit presence of a
        # non-label substantive text cell between linked title and amount.
        amount_start = next((j for j, (v, _) in enumerate(tokens) if "valoarea estimată" in v.casefold()), None)
        title_end = next((j for j, (v, link) in enumerate(tokens) if link == href), -1)
        buyer_present = (amount_start is not None and amount_start > title_end + 1 and
                         any(len(tokens[j][0]) >= 4 for j in range(title_end+1, amount_start)))
        items.append({
            "path_valid": PATH.fullmatch(href) is not None,
            "title": enough_title, "buyer": buyer_present,
            "amount": len(amounts) >= 1, "date": len(dates) >= 1,
            "tokens": len(tokens)
        })
    complete = sum(all(x[k] for k in ("path_valid", "title", "buyer", "amount", "date")) for x in items)
    return {"verified": complete >= 5, "linked_tenders": len(parser.links),
            "complete_visible_records": complete, "record_shapes": items[:5]}


def main():
    parsed = urlsplit(URL)
    if parsed.scheme != "https" or parsed.hostname != "mtender.md":
        raise ValueError("Invalid public official platform URL.")
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    data = {"source": "md_mtender_public_platform", "verified": False}
    try:
        with opener.open(Request(URL, headers={"User-Agent": "VALYQON-public-procurement-source-audit/1.0",
                                               "Accept": "text/html"}), timeout=TIMEOUT) as response:
            data["http_status"] = response.status
            if response.status == 200 and "html" in response.headers.get("Content-Type", "").lower():
                raw = response.read(MAX_BYTES+1)
                data["bytes"] = len(raw)
                data.update(summarize(raw))
            else:
                data["reason"] = "non_html_or_non200"
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        data["error_kind"] = type(exc).__name__
        if isinstance(exc, HTTPError):
            data["http_status"] = exc.code
    print(json.dumps(data, sort_keys=True, ensure_ascii=False))
    return 0 if data.get("verified") else 1


if __name__ == "__main__":
    sys.exit(main())
