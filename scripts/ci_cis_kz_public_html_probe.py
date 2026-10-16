"""Fail-closed live evidence for Kazakhstan's PUBLIC HTML procurement catalogue.

Distinct from the token-required KZ API already registered in VALYQON.
Official server-rendered pages only, verified TLS, no cookies, proxy, redirect,
API key or tenant input. Never mutate a database or claim production readiness.
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

HOST = "procurement.gov.kz"
APPROVED_HOSTS = ("procurement.gov.kz", "old.goszakup.gov.kz", "goszakup.gov.kz")
INDEX = "https://procurement.gov.kz/ru/search/announce?count_record=50&page=1"
MAX_BYTES = 1024 * 1024
TIMEOUT = 16
DETAIL_PATH = re.compile(r"^/ru/announce/index/([1-9]\d{6,11})$")
ANNOUNCE_NUMBER = re.compile(r"\b([1-9]\d{6,11})-1\b")
KZ_DATE = re.compile(r"\b20\d\d-\d\d-\d\d\s+\d\d:\d\d:\d\d\b")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class PublicTables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None
        self.rows = []
        self.links = []
        self.hidden = 0
        self.cell_links = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "noscript"}:
            self.hidden += 1
        if self.hidden:
            return
        if tag == "table":
            if self.table is None:
                self.table = []
        if tag == "tr" and self.table is not None:
            self._row()
            self.row = []
        if tag in {"th", "td"} and self.row is not None:
            self._cell()
            self.cell = []
        if tag == "a" and self.cell is not None:
            href = dict(attrs).get("href")
            if href:
                self.cell_links.append(str(href)[:300])

    def handle_data(self, data):
        if self.cell is not None and not self.hidden:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"script", "style", "template", "noscript"}:
            self.hidden = max(0, self.hidden-1)
        if tag in {"th", "td"}:
            self._cell()
        if tag == "tr":
            self._row()
        if tag == "table" and self.table is not None:
            self._row()
            self.tables.append(self.table)
            self.table = None

    def _cell(self):
        if self.row is not None and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
        self.cell = None

    def _row(self):
        if self.row is not None and self.table is not None and self.row:
            self.table.append((self.row, tuple(self.cell_links)))
        self.row = None
        self.cell_links = []


def inspect_index(raw, *, hostname=HOST):
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        return {"verified": False, "reason": "invalid_body"}
    parser = PublicTables()
    parser.feed(raw.decode("utf-8", errors="replace"))
    candidates = []
    for table in parser.tables:
        if not table or len(table) > 100:
            continue
        plausible = []
        for cells, links in table:
            joined = " ".join(cells)
            numbers = ANNOUNCE_NUMBER.findall(joined)
            if numbers and len(cells) >= 5:
                approved = []
                for href in links:
                    target = urlsplit(href)
                    if (target.scheme in ("", "https") and target.hostname in (None, hostname)
                            and DETAIL_PATH.fullmatch(target.path)
                            and not target.query and not target.fragment
                            and not target.username and not target.password):
                        approved.append(target.path)
                plausible.append((cells, approved))
        if plausible:
            cells, approved = plausible[0]
            candidates.append({
                "rows": len(table),
                "matched_announcement_rows": len(plausible),
                "columns": len(cells),
                "date_fields": sum(bool(KZ_DATE.search(v)) for v in cells),
                "linked_detail_routes": len(approved),
                "sample_cell_lengths": [min(300, len(v)) for v in cells[:12]],
                "sample_detail_paths": approved[:2],
            })
    real = sum(x["matched_announcement_rows"] for x in candidates)
    details = sum(x["linked_detail_routes"] for x in candidates)
    return {"verified": real >= 5 and details >= 1,
            "table_count": len(parser.tables),
            "verified_list_rows": real,
            "detail_links_seen": details,
            "public_table_shapes": candidates[:3]}


def get(url, opener):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in APPROVED_HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError("unapproved official host")
    request = Request(url, headers={"User-Agent": "VALYQON-cis-official-public-readonly/1.0",
                                    "Accept": "text/html"})
    with opener.open(request, timeout=TIMEOUT) as response:
        if response.status != 200 or "html" not in response.headers.get("Content-Type", "").lower():
            raise ValueError("unexpected response content")
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("oversized official response")
        return data


def main():
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    out = {"source": "kz_goszakup_public_html", "verified": False,
           "production_activation_allowed": False, "hosts": []}
    for hostname in APPROVED_HOSTS:
        probe = {"hostname": hostname, "index_verified": False,
                 "detail_verified": False}
        index_url = f"https://{hostname}/ru/search/announce?count_record=50&page=1"
        try:
            result = inspect_index(get(index_url, opener), hostname=hostname)
            probe["index_verified"] = result["verified"]
            probe["matched_notice_rows"] = result.get("verified_list_rows", 0)
            probe["detail_link_count"] = result.get("detail_links_seen", 0)
            candidates = [p for t in result.get("public_table_shapes", [])
                          for p in t.get("sample_detail_paths", [])]
            if result["verified"] and candidates:
                detail = get("https://" + hostname + candidates[0], opener).decode("utf-8", errors="replace")
                probe["detail_verified"] = (
                    "Просмотр объявления" in detail and
                    "Организатор" in detail and
                    "Срок окончания приема заявок" in detail
                )
        except HTTPError as exc:
            probe.update({"failure_kind": "HTTPError", "http_status": exc.code})
        except URLError as exc:
            probe.update({"failure_kind": "URLError",
                          "reason_class": type(exc.reason).__name__})
        except (OSError, ValueError, TimeoutError) as exc:
            probe["failure_kind"] = type(exc).__name__
        probe["verified"] = probe["index_verified"] and probe["detail_verified"]
        out["hosts"].append(probe)
    out["verified"] = any(x["verified"] for x in out["hosts"])
    print(json.dumps(out, ensure_ascii=False, sort_keys=True))
    return 0 if out["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
