"""Read-only bounded public-source diagnostics for prospective CIS adapters.

This script is NOT an ingestion adapter and never mutates VALYQON data.
It reports evidence separately from readiness. GitHub Actions executes it
against official/public endpoints to establish current network accessibility.
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import ssl
import sys
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

TIMEOUT = 12
MAX_BODY = 512 * 1024
TARGETS = {
    "md_mtender_index": "https://public.mtender.gov.md/tenders/",
    "md_mtender_known_detail": "https://public.mtender.gov.md/tenders/ocds-b3wdp1-MD-1770204825070",
    "kg_portal_home": "https://zakupki.gov.kg/popp/home.xhtml",
    "kg_known_detail": "https://zakupki.gov.kg/popp/view/order/view.xhtml?id=561794973",
    "kg_new_portal": "https://goszakupki.okmot.kg/public/?locale=ky",
    "kg_public_no_locale": "https://goszakupki.okmot.kg/public/",
    "md_index_no_slash": "https://public.mtender.gov.md/tenders?offset=",
    "md_public_get_index": "https://public.mtender.gov.md/get/tenders?offset=",
    "md_alternative_index": "https://public.eprocurement.systems/get/tenders?offset=",
    "md_agency_listing": "https://www.tender.gov.md/en/documente-in-curs-de-examinare",
    "md_public_portal": "https://mtender.gov.md/tenders",
    "md_public_portal_ru": "https://mtender.gov.md/ru/tenders",
    "md_agency_ro_listing": "https://tender.gov.md/ro/documente-in-curs-de-examinare",
}
HOSTS = {"public.mtender.gov.md", "zakupki.gov.kg", "goszakupki.okmot.kg", "public.eprocurement.systems", "www.tender.gov.md", "mtender.gov.md", "tender.gov.md"}
OCID = re.compile(r"^ocds-[a-zA-Z0-9_-]{3,150}$")
ORDER_LINK = re.compile(r"view/order/view\.xhtml\?id=\d{5,18}")
NEW_ORDER_ID = re.compile(r"(?:№|&#8470;|&numero;)\s*(20\d{12,20})")

# The 2026 official Kyrgyz portal is JS-backed. Visible HTML listings may
# appear in cached/server-rendered responses, but script bundles and UI labels
# are not procurement records. Never infer a functioning feed from HTTP 200.
class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "noscript"}:
            self.hidden += 1
        elif tag in {"article", "section", "p", "div", "li", "br"} and not self.hidden:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "template", "noscript"}:
            self.hidden = max(0, self.hidden - 1)
        elif tag in {"article", "section", "p", "div", "li"} and not self.hidden:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def extract_kg_notice_evidence(raw):
    """Require linked number, category, title, customer, amount and both dates.

    This is evidence validation, NOT a production parser or persistence proof.
    Fail closed on script-only SPAs and avoid retaining personal information.
    """
    parser = _VisibleText()
    parser.feed(raw.decode("utf-8", errors="replace"))
    visible = re.sub(r"\s+", " ", " ".join(parser.parts))
    marker = re.compile(r"№\s*(20\d{12,20})\b")
    positions = list(marker.finditer(visible))
    confirmed = set()
    for i, found in enumerate(positions[:100]):
        block = visible[found.end():positions[i + 1].start() if i + 1 < len(positions) else len(visible)]
        status = re.search(r"(?:Жарыяланган|Опубликовано|Published)\s+(?:Товары|Работы|Услуги|Goods|Works|Services)\s+(.+?)\s+Организация\s+(.+?)\s+Планируемая сумма\s+([\d\s\u00a0.,]+)\s*(?:Сом|сом|KGS)\b", block)
        if not status:
            continue
        title, customer, amount = status.groups()
        if (len(title.strip()) < 5 or len(customer.strip()) < 4
                or not re.search(r"\d", amount)
                or not re.search(r"Дата публикации\s+\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}", block)
                or not re.search(r"Дата окончания\s+\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}", block)):
            continue
        confirmed.add(found.group(1))
    return confirmed


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def check_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in HOSTS
            or parsed.username is not None or parsed.password is not None
            or parsed.port not in (None, 443) or parsed.fragment):
        raise ValueError("Unapproved endpoint")


def describe_payload(name, raw, content_type):
    if name in {"md_public_portal", "md_public_portal_ru"}:
        html = raw.decode("utf-8", errors="replace")
        ocids = set(re.findall(r"ocds-b3wdp1-MD-\d{10,18}", html))
        return {"verified": bool(ocids), "kind": "public_mtender_portal_ocid_listing",
                "ocid_count": len(ocids)}
    if name in {"md_agency_listing", "md_agency_ro_listing"}:
        document = raw.decode("utf-8", errors="replace")
        confirmed = set()
        for row in re.findall(r"<tr\b[^>]*>(.*?)</tr\s*>", document, flags=re.I | re.S)[:100]:
            cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]\s*>", row, flags=re.I | re.S)
            if len(cells) < 9:
                continue
            cleaned = [re.sub(r"\s+", " ", html_lib.unescape(
                re.sub(r"<[^>]+>", " ", cell))).strip() for cell in cells]
            document_type, title = cleaned[5], cleaned[6]
            ocid, cpv, received = cleaned[7], cleaned[8], cleaned[2]
            if (not re.fullmatch(r"ocds-b3wdp1-MD-\d{10,18}", ocid, flags=re.I)
                    or "mtender" not in document_type.casefold()
                    or len(title) < 6 or not re.fullmatch(r"\d{8}-\d", cpv)
                    or not re.fullmatch(r"\d{2}\.\d{2}\.20\d{2}", received)):
                continue
            confirmed.add(ocid.lower())
        return {"verified": bool(confirmed), "kind": "official_agency_structured_ocid_rows",
                "ocid_count": len(confirmed)}
    if name.startswith("md_"):
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeError, ValueError):
            return {"verified": False, "reason": "no_json"}
        if name.endswith("_index") or name == "md_mtender_index":
            rows = data if isinstance(data, list) else data.get("data", []) if isinstance(data, dict) else []
            valid = [row.get("ocid") for row in rows if isinstance(row, dict)
                     and isinstance(row.get("ocid"), str) and OCID.fullmatch(row["ocid"])]
            return {"verified": bool(valid), "kind": "public_ocid_listing",
                    "ocid_count": len(valid), "json_type": type(data).__name__}
        # An OCID alone is not a procurement notice. Require actual title and ID.
        records = data.get("records") if isinstance(data, dict) else None
        releases = data.get("releases") if isinstance(data, dict) else None
        rows = records if isinstance(records, list) else releases if isinstance(releases, list) else []
        titles = []
        for record in rows:
            if not isinstance(record, dict):
                continue
            release = record.get("compiledRelease", record)
            if isinstance(release, dict) and isinstance(release.get("tender"), dict):
                titles.append(release["tender"].get("title"))
        return {"verified": any(isinstance(t, str) and bool(t.strip()) for t in titles),
                "kind": "ocds_detail", "records_with_title": sum(
                    isinstance(t, str) and bool(t.strip()) for t in titles)}
    # Raw Kyrgyz pages may be JSF with server-side postbacks. Do not claim
    # completeness from a successful 200 response or a pre-existing detail page.
    html = raw.decode("utf-8", errors="replace")
    if name == "kg_portal_home":
        links = ORDER_LINK.findall(html)
        return {"verified": bool(links), "kind": "html_listing_with_detail_links",
                "order_links": len(set(links)), "has_jsf": "javax.faces" in html}
    if name in {"kg_new_portal", "kg_public_no_locale"}:
        ids = set(NEW_ORDER_ID.findall(html))
        verified_ids = extract_kg_notice_evidence(raw)
        return {"verified": bool(verified_ids), "kind": "new_portal_tender_listing",
                "order_ids": len(ids), "verified_order_count": len(verified_ids),
                "has_description": bool(verified_ids)}
    return {"verified": bool(re.search(r"(purchase Name|Date of publication|procurement|Наименование закупки|Наименование конкурса)", html, re.I)),
            "kind": "public_detail_html", "html_bytes": len(raw)}


def probe(name, url, opener):
    check_url(url)
    item = {"target": name, "url": url, "reachable": False, "verified": False}
    request = Request(url, headers={
        "User-Agent": "VALYQON-source-verification/1.0",
        "Accept": "application/json,text/html;q=0.9",
    })
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            item["http_status"] = response.status
            if response.status != 200:
                item["reason"] = "unexpected_status"
                return item
            raw = response.read(MAX_BODY + 1)
            if len(raw) > MAX_BODY:
                item["reason"] = "response_over_limit"
                return item
            item["reachable"] = True
            item["bytes"] = len(raw)
            item.update(describe_payload(name, raw, response.headers.get("Content-Type", "")))
    except HTTPError as exc:
        item.update({"reason": "http_error", "http_status": exc.code})
    except (URLError, TimeoutError, OSError, ValueError, ssl.SSLError) as exc:
        item.update({"reason": "network_or_tls_error", "error_kind": type(exc).__name__})
    return item


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-live", action="store_true",
                        help="Fail CI unless MD index and at least one KG listing verify records")
    parser.add_argument("--require-md", action="store_true", help="Fail CI unless Moldova OCIDs verified")
    parser.add_argument("--require-kg", action="store_true", help="Fail CI unless Kyrgyzstan listing IDs verified")
    args = parser.parse_args(argv)
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    results = [probe(name, url, opener) for name, url in TARGETS.items()]
    summary = {"kind": "observational_public_cis_probe", "results": results,
               "md_index_verified": any(row["verified"] for row in results if row["target"] in {
                   "md_mtender_index", "md_index_no_slash", "md_public_get_index", "md_alternative_index", "md_agency_listing", "md_public_portal", "md_public_portal_ru", "md_agency_ro_listing"}),
               "md_detail_verified": any(row["verified"] for row in results if row["target"] == "md_mtender_known_detail"),
               "kg_listing_verified": any(row["verified"] for row in results if row["target"] in {
                   "kg_portal_home", "kg_new_portal", "kg_public_no_locale"}),
               "end_to_end_storage_verified": False,
               "production_activation_allowed": False}
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    if args.require_md and not (summary["md_index_verified"] and summary["md_detail_verified"]):
        return 1
    if args.require_kg and not summary["kg_listing_verified"]:
        return 1
    return 1 if args.require_live and not (summary["md_index_verified"] and summary["kg_listing_verified"]) else 0


if __name__ == "__main__":
    sys.exit(main())
