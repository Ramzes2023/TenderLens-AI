"""Observe official Ingushetia EIS + accredited 44-FZ marketplace routes.

This is READ-ONLY NETWORK DIAGNOSIS, not live ingestion, no cached/fixture
fallback, no production data, no secrets, no TLS/redirect/proxy bypass.
Records status and corroborating IDs without leaking network internals.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit

from app.sources.http import FetchPolicy, bounded_fetch, source_client
from scripts.ru_eis_pinned_tls_probe import verify_root

ROOT = Path(__file__).resolve().parents[1] / "russian_trusted_root_ca_pem.crt"
HOST_EIS = "zakupki.gov.ru"
HOST_FAB = "44.fabrikant.ru"
HOST_SOAP = "soap4.fabrikant.ru"
HOST_ZMO = "zmo.fabrikant.ru"
class VisibleText(HTMLParser):
    """Read only visible first-party text, not raw markup or inline scripts."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignored = 0
        self.words = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "svg", "noscript"}:
            self.ignored += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "template", "svg", "noscript"} and self.ignored:
            self.ignored -= 1

    def handle_data(self, data):
        if not self.ignored:
            self.words.append(data)


def public_visible_text(html):
    parser = VisibleText()
    parser.feed(html)
    parser.close()
    return " ".join(" ".join(parser.words).split()).upper()


CASES = (
    ("eis_ingushetia_rss", "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?fz44=on&regions=06&pageNumber=1", HOST_EIS, None),
    ("fabrikant_current_catalog", "https://44.fabrikant.ru/44/catalog/procedure/published?dir=desc&order=publication_datetime", HOST_FAB, None),
    ("fabrikant_soap4_current_catalog", "https://soap4.fabrikant.ru/44/catalog/procedure/published", HOST_SOAP, None),
    ("fabrikant_soap4_ordered_current_catalog", "https://soap4.fabrikant.ru/44/catalog/procedure/published?dir=desc&dropOrder=1&order=procedure_number", HOST_SOAP, None),
    ("fabrikant_zmo_current_catalog", "https://zmo.fabrikant.ru/44/catalog/procedure?dir=desc&order=trade_start_datetime&page=1", HOST_ZMO, None),
    ("fabrikant_ingush_0114500000826002121", "https://soap4.fabrikant.ru/44/procedure/ea21/0114500000826002121", HOST_SOAP, "0114500000826002121"),
    ("fabrikant_ingush_0114500000826002117", "https://soap4.fabrikant.ru/44/procedure/ea21/0114500000826002117", HOST_SOAP, "0114500000826002117"),
    # October 2026 original-card URL hypotheses: number exists in a fresh
    # independently indexed Ingushetia EIS record but the ETP path is NOT
    # confirmed until the exact official HTTPS detail returns and corroborates.
    ("fabrikant_oct_candidate_0114500000826002358", "https://soap4.fabrikant.ru/44/procedure/ea21/0114500000826002358", HOST_SOAP, "0114500000826002358"),
    ("fabrikant_oct_candidate_0114500000826002323", "https://soap4.fabrikant.ru/44/procedure/ea21/0114500000826002323", HOST_SOAP, "0114500000826002323"),
)


async def observe(name, url, host, number):
    status = {"route": name, "http_status": None, "verified_original_id": False,
              "status": "BLOCKED", "error": None}

    async def record(response):
        status["http_status"] = response.status_code

    try:
        if (urlsplit(url).scheme != "https" or urlsplit(url).netloc != host
                or host not in {HOST_EIS, HOST_FAB, HOST_SOAP, HOST_ZMO}):
            raise ValueError("Unexpected diagnostic host")
        verify = str(ROOT) if host == HOST_EIS else True
        with bounded_fetch(FetchPolicy(frozenset({host}), 1, max_bytes=1_800_000)):
            async with source_client(
                timeout=25 if host in {HOST_FAB, HOST_ZMO} else 15, trust_env=False, follow_redirects=False,
                verify=verify, event_hooks={"response": [record]},
                headers={"Accept": "text/html, application/rss+xml, application/xml",
                         "User-Agent": "Mozilla/5.0 (compatible; VALYQON-Source-Audit/1.0)"},
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                if number:
                    text = public_visible_text(response.text)
                    has_heading = "СВЕДЕНИЯ О ЗАКУПКЕ " + number in text
                    has_organizer = "КОМИТЕТ ГОСУДАРСТВЕННОГО ЗАКАЗА РЕСПУБЛИКИ ИНГУШЕТИЯ" in text
                    has_inn = "0608058533" in text
                    status["detail_fields"] = {"original_number": has_heading,
                                               "regional_organizer": has_organizer,
                                               "regional_inn": has_inn}
                    status["verified_original_id"] = has_heading and has_organizer and has_inn
                    status["status"] = "FIRST_PARTY_INGUSHETIA_DETAIL_VERIFIED" if status["verified_original_id"] else "UNVERIFIED_BODY"
                elif "rss" in name:
                    status["status"] = "OFFICIAL_RSS_RESPONSE_NOT_INGESTION_PROOF" if (
                        "xml" in response.headers.get("content-type", "").lower() or "<rss" in response.text[:500].lower()
                    ) else "NOT_RSS"
                else:
                    status["status"] = "MARKETPLACE_LIST_RESPONSE_NOT_INGESTION_PROOF" if (
                        "html" in response.headers.get("content-type", "").lower()
                    ) else "NOT_HTML"
    except Exception as exc:
        status["error"] = type(exc).__name__
        causes = []
        inner = getattr(exc, "__cause__", None)
        while inner is not None and len(causes) < 3:
            causes.append(type(inner).__name__)
            inner = getattr(inner, "__cause__", None)
        status["cause_types"] = causes
    return status


async def run():
    # A single pinned published Russian root for EIS, no system root modifications.
    verify_root(ROOT.read_bytes())
    return [await observe(*item) for item in CASES]


def main():
    results = asyncio.run(run())
    print("INGUSHETIA_OFFICIAL_ROUTE_DIAGNOSTICS=" + json.dumps(results, ensure_ascii=False))
    print("ALL_DIAGNOSTICS_ARE_OBSERVATIONAL=YES")
    print("NOTIFICATION_PROVEN=NO")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
