"""Read-only Uzbekistan UzEx public tender API acceptance probe.

PROBE ONLY: never activates a source, reads secrets, or writes application data.
Only a current official HTTPS response with complete tender notices can pass.
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

API_URL = "https://apietender.uzex.uz/api/common/TradeList"
DETAIL_PREFIX = "https://etender.uzex.uz/lot/"
MAX_BYTES = 512 * 1024
TIMEOUT_SECONDS = 12
MAX_RECORDS = 20
DATE_RE = re.compile(r"20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}")
POSITIVE_ID_RE = re.compile(r"^[1-9]\d{2,11}$")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def make_request(type_id: int) -> Request:
    if type_id not in (1, 2):
        raise ValueError("Only tender and selection public listings are approved")
    body = json.dumps(
        {"TypeId": type_id, "From": 1, "To": MAX_RECORDS, "System_Id": 0},
        separators=(",", ":"),
    ).encode("ascii")
    return Request(
        API_URL,
        data=body,
        headers={
            "User-Agent": "VALYQON-public-procurement-verifier/1.0",
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )


def _field(row: dict, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def validate_notice(row: object) -> bool:
    """A list item's ID alone is insufficient proof of a live tender."""
    if not isinstance(row, dict):
        return False
    raw_id = row.get("id")
    if isinstance(raw_id, bool) or not isinstance(raw_id, (str, int)):
        return False
    if not POSITIVE_ID_RE.fullmatch(str(raw_id)):
        return False
    title = _field(row, "name", "trade_name", "title")
    buyer = _field(row, "customer_name", "customerName", "customer", "seller_name")
    start = _field(row, "start_date", "startDate", "start_at")
    deadline = _field(row, "end_date", "endDate", "end_at")
    if (len(title) < 8 or len(buyer) < 4
            or not DATE_RE.search(start) or not DATE_RE.search(deadline)):
        return False
    if "javascript:" in title.casefold() or title.casefold() in {"loading", "no data"}:
        return False
    return True


def inspect_json(raw: bytes) -> dict:
    try:
        parsed = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeError):
        return {"verified": False, "reason": "invalid_json"}
    if isinstance(parsed, list):
        rows = parsed
    elif isinstance(parsed, dict):
        rows = parsed.get("data", parsed.get("items", []))
    else:
        rows = []
    if not isinstance(rows, list):
        return {"verified": False, "reason": "unexpected_schema"}
    verified = sum(validate_notice(item) for item in rows[:MAX_RECORDS])
    # Schema-only diagnostics: never print customer, tender, tax or personal values.
    sample = next((item for item in rows[:MAX_RECORDS] if isinstance(item, dict)), {})
    field_types = {key: type(value).__name__ for key, value in sorted(sample.items())[:60]}
    return {
        "public_schema_types": field_types,
        "verified": verified > 0,
        "kind": "official_uzex_public_tender_list",
        "rows_seen": min(len(rows), MAX_RECORDS),
        "complete_notices": verified,
    }


def probe(type_id: int, opener) -> dict:
    result = {
        "kind": "official_uzex_public_tender_probe",
        "country": "UZ",
        "type_id": type_id,
        "verified": False,
        "reachable": False,
    }
    request = make_request(type_id)
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            result["http_status"] = response.status
            if response.status != 200:
                result["reason"] = "unexpected_http_status"
                return result
            content_type = response.headers.get("Content-Type", "")
            if "json" not in content_type.lower():
                result["reason"] = "non_json_content_type"
                return result
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                result["reason"] = "oversized_response"
                return result
            result["reachable"] = True
            result.update(inspect_json(raw))
    except HTTPError as exc:
        result.update({"reason": "http_error", "http_status": exc.code})
    except (URLError, TimeoutError, OSError, ValueError, ssl.SSLError) as exc:
        result.update({"reason": "network_or_tls_error", "error_kind": type(exc).__name__})
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--require-live", action="store_true")
    args = ap.parse_args(argv)
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    results = [probe(source_type, opener) for source_type in (1, 2)]
    passed = all(item["verified"] for item in results)
    summary = {
        "kind": "uzbekistan_uzex_official_public_readiness",
        "results": results,
        "official_live_verified": passed,
        "end_to_end_storage_verified": False,
        "production_activation_allowed": False,
    }
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
    return 1 if args.require_live and not passed else 0


if __name__ == "__main__":
    sys.exit(main())
