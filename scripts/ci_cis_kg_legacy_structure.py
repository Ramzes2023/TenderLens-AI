"""Read-only inspection of official Kyrgyz government procurement HTML structure.

No production writes. No fake notices. No personal/tender content in logs.
Never redirects or contacts unapproved host; TLS and hostname verified.
"""
from __future__ import annotations
import json
import re
import ssl
import sys
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

URL = "https://zakupki.gov.kg/popp/view/order/list.xhtml"
MAX_BYTES = 1024 * 1024
TIMEOUT = 18
NUMBER = re.compile(r"\b2[0-9]{12,17}\b")
DATE = re.compile(r"\b\d{2}\.\d{2}\.20\d{2}\s+\d{2}:\d{2}\b")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class Tables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.rows = []
        self.row = None
        self.cell = None
        self.depth = 0
        self.links = []
        self.cell_links = []
        self.hidden = 0
        self.attrs = []

    def handle_starttag(self, tag, attributes):
        a = dict(attributes)
        if tag in {"script", "style", "template", "noscript"}:
            self.hidden += 1
        if tag == "table":
            self.depth += 1
            if self.depth == 1:
                self.rows = []
        if not self.depth or self.hidden:
            return
        if tag == "tr" and self.depth == 1:
            self._finish_row()
            self.row = []
        if tag in {"th", "td"} and self.row is not None and self.depth == 1:
            self._finish_cell()
            self.cell = []
        if tag == "a" and self.cell is not None:
            for attr in ("href", "onclick", "data-url"):
                value = a.get(attr)
                if value:
                    self.cell_links.append((attr, str(value)[:600]))

    def handle_data(self, data):
        if self.cell is not None and not self.hidden:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"script", "style", "template", "noscript"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"th", "td"} and self.depth == 1:
            self._finish_cell()
        if tag == "tr" and self.depth == 1:
            self._finish_row()
        if tag == "table" and self.depth:
            self.depth -= 1
            if self.depth == 0:
                self._finish_row()
                self.tables.append(self.rows)
                self.rows = []

    def _finish_cell(self):
        if self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
        self.cell = None

    def _finish_row(self):
        if self.row:
            self.rows.append((self.row, self.cell_links))
        self.row = None
        self.cell = None
        self.cell_links = []


def inspect(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise ValueError("Response oversized")
    parser = Tables()
    parser.feed(raw.decode("utf-8", errors="replace"))
    candidates = []
    for idx, table in enumerate(parser.tables[:60]):
        rows = [cells for cells, _ in table]
        matching = [(cells, links) for cells, links in table
                    if NUMBER.search(" ".join(cells)) and len(cells) >= 5]
        if not matching:
            continue
        cells, links = matching[0]
        # Only shape information, no customer/tender text or executable JS.
        samples = []
        for val in cells[:15]:
            samples.append({"length": len(val), "digits": len(re.sub(r"\D", "", val)),
                            "date": bool(DATE.search(val)), "id": bool(NUMBER.search(val))})
        link_shapes = []
        for kind, value in links[:12]:
            matched = re.findall(r"(?:view/order/[a-z_]+\.xhtml|/popp/[a-z/_]+|id=)", value, re.I)
            link_shapes.append({"attribute": kind, "routing_shape": matched[:6], "length": len(value)})
        candidates.append({"table_index": idx, "rows": len(table), "columns": len(cells),
                           "strict_identifier_rows": len(matching), "cells_shape": samples,
                           "link_shapes": link_shapes})
    return {"candidate_tables": candidates[:8], "table_count": len(parser.tables),
            "verified_complete_listing_structure": bool(candidates)}


def main():
    if urlsplit(URL).hostname != "zakupki.gov.kg":
        raise SystemExit("unapproved host")
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    output = {"source": "kg_official_legacy", "verified": False, "url": URL}
    try:
        with opener.open(Request(URL, headers={"User-Agent": "VALYQON-live-government-procurement/1.0",
                                               "Accept": "text/html"}), timeout=TIMEOUT) as response:
            output["http_status"] = response.status
            if response.status != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
                output["reason"] = "unapproved_media_or_http_status"
            else:
                raw = response.read(MAX_BYTES + 1)
                output.update(inspect(raw))
                output["verified"] = output["verified_complete_listing_structure"]
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        output["failure_class"] = type(error).__name__
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0 if output["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
