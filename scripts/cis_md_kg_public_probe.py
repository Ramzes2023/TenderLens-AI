"""Read-only bounded public-source diagnostics for prospective CIS adapters.

This script is NOT an ingestion adapter and never mutates VALYQON data.
It reports evidence separately from readiness. GitHub Actions executes it
against official/public endpoints to establish current network accessibility.
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
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
}
HOSTS = {"public.mtender.gov.md", "zakupki.gov.kg", "goszakupki.okmot.kg"}
OCID = re.compile(r"^ocds-[a-zA-Z0-9_-]{3,150}$")
ORDER_LINK = re.compile(r"view/order/view\.xhtml\?id=\d{5,18}")
NEW_ORDER_ID = re.compile(r"(?:№|&#8470;|&numero;)\s*(20\d{12,20})")


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
    if name.startswith("md_"):
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeError, ValueError):
            return {"verified": False, "reason": "no_json"}
        if name == "md_mtender_index":
            rows = data if isinstance(data, list) else data.get("data", []) if isinstance(data, dict) else []
            valid = [row.get("ocid") for row in rows if isinstance(row, dict)
                     and isinstance(row.get("ocid"), str) and OCID.fullmatch(row["ocid"])]
            return {"verified": bool(valid), "kind": "public_ocid_listing",
                    "ocid_count": len(valid), "json_type": type(data).__name__}
        # An OCID alone is not a procurement notice. Require actual title and ID.
        records = data.get("records") if isinstance(data, dict) else None
        releases = data.get("releases") if isinstance(data, dict) else None
        rows = records if isinstance(records, list) else releases if isinstance(releases, list) else []
        titles = [r.get("tender", {}).get("title") for r in rows if isinstance(r, dict)
                  and isinstance(r.get("tender"), dict)]
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
    if name == "kg_new_portal":
        ids = set(NEW_ORDER_ID.findall(html))
        has_description = ("Планируемая сумма" in html or "Организация" in html)
        return {"verified": bool(ids) and has_description,
                "kind": "new_portal_tender_listing", "order_ids": len(ids),
                "has_description": has_description}
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
               "md_index_verified": results[0]["verified"],
               "kg_listing_verified": results[2]["verified"] or results[4]["verified"],
               "end_to_end_storage_verified": False,
               "production_activation_allowed": False}
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    if args.require_md and not summary["md_index_verified"]:
        return 1
    if args.require_kg and not summary["kg_listing_verified"]:
        return 1
    return 1 if args.require_live and not (summary["md_index_verified"] and summary["kg_listing_verified"]) else 0


if __name__ == "__main__":
    sys.exit(main())
