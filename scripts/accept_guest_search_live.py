"""Operator acceptance: verify deployed *real stored* public search, no demos.

Run only against an authorized VALYQON host. This verifies served HTTP routes,
not the provenance of upstream connector records; compare DB/Worker observations
separately before asserting full source->Worker->DB->HTTP delivery.

Usage (PowerShell):
  $env:VALYQON_ACCEPTANCE_BASE_URL='http://127.0.0.1:8000'
  python -B scripts/accept_guest_search_live.py
Exit code 0: gated UI and at least one actual stored opportunity returned.
Exit code 2: a required acceptance condition is unverified/failed.
"""
from __future__ import annotations

import json
import os
import sys
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

PROHIBITED_RESULT_KEYS = {
    "url", "source", "source_id", "external_id", "tender_number",
    "customer", "region", "summary", "enrichment", "documents",
    "buyer", "platform", "requirements", "contacts", "original_url",
}
ALLOWED_RESULT_KEYS = {"title", "initial_price", "currency", "deadline"}


def _get(base, route):
    with urlopen(Request(base + route, headers={"Accept": "application/json"}),
                 timeout=12) as response:
        return response.status, dict(response.headers), response.read(256_000)


def verify(base):
    parsed = urlsplit(base)
    # Do not allow leaked credentials, insecure remote HTTP or arbitrary protocols.
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Invalid acceptance target")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Remote acceptance targets must use HTTPS")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("Base URL must be origin only")
    base = base.rstrip("/")
    status, headers, page = _get(base, "/")
    if status != 200 or b'guestSearchForm' not in page or b'vqPulseChart' not in page:
        raise AssertionError("Guest page missing functional search/market markup")
    status, headers, payload = _get(base, "/api/v1/public/opportunities")
    if status != 200 or not headers.get("Cache-Control", "").startswith("no-store"):
        raise AssertionError("Guest search unavailable or cacheable")
    response = json.loads(payload)
    if response.get("source") != "stored_connector_notices" or response.get("details_locked") is not True:
        raise AssertionError("Unexpected opportunity source/scope")
    rows = response.get("results")
    if not isinstance(rows, list) or len(rows) > 12:
        raise AssertionError("Malformed/broad guest response")
    for item in rows:
        if not isinstance(item, dict) or set(item) != ALLOWED_RESULT_KEYS:
            raise AssertionError("Guest response exposes unexpected fields")
        if not isinstance(item.get("title"), str) or not item["title"].strip():
            raise AssertionError("Guest result has no real title")
        if any(token in item["title"].lower() for token in ("http://", "https://", "www.", "@")):
            raise AssertionError("Guest title contains prohibited link/contact")
    if not rows:
        raise AssertionError("NO_PERSISTED_TENDERS: source->Worker->DB->HTTP not verified")
    status, headers, market = _get(base, "/api/v1/public/market-pulse")
    if status != 200:
        raise AssertionError("Market pulse endpoint unavailable")
    pulse = json.loads(market)
    if pulse.get("scope") != "bounded_persisted_source_observations" or len(pulse.get("days", [])) != 14:
        raise AssertionError("Market pulse is not a verified bounded DB observation")
    for field in PROHIBITED_RESULT_KEYS:
        if any(field in row for row in rows):
            raise AssertionError("Unexpected protected field")
    return {"stored_notice_previews": len(rows),
            "first_observed_in_sample": pulse.get("new_notices_in_sample"),
            "scope": "HTTP_PUBLIC_PROJECTION_ONLY"}


def main():
    base = os.environ.get("VALYQON_ACCEPTANCE_BASE_URL", "").strip()
    if not base:
        print("ACCEPTANCE=BLOCKED; VALYQON_ACCEPTANCE_BASE_URL is not configured")
        return 2
    try:
        result = verify(base)
    except (ValueError, AssertionError, HTTPError, URLError, OSError,
            TimeoutError, json.JSONDecodeError):
        print("ACCEPTANCE=BLOCKED; public search and/or persistence evidence incomplete")
        return 2
    print("ACCEPTANCE=VERIFIED; PROJECTION_ONLY=YES; HTTP_RESULTS=" +
          str(result["stored_notice_previews"]) + "; MARKET_SAMPLE_OBSERVED=" +
          str(result["first_observed_in_sample"]))
    print("WARNING=Worker ingestion, freshness, payment entitlement and real-user browser UI require separate proof")
    return 0


if __name__ == "__main__":
    sys.exit(main())
