"""Read-only hosted verification of public VALYQON guest-source routes.

Fixed HTTPS host, no credentials, no production writes, no arbitrary URL input.
This cannot identify individual sources: the guest API intentionally redacts
source IDs and buyers. It checks only whether *public saved rows* are visible.
"""
from __future__ import annotations

import argparse
import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

HOST = "https://valyqon.duckdns.org"
PATHS = (
    "/api/v1/public/opportunities",
    "/api/v1/public/market-pulse",
    "/api/v1/public/market-intelligence",
    "/public/source-directory.json",
)
ALLOWED_NOTICE = frozenset({"title", "initial_price", "currency", "deadline"})
MAX_BYTES = 256_000


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate(path: str, data: object) -> tuple[str, int]:
    if not isinstance(data, dict):
        return ("INVALID_JSON_SHAPE", 0)
    if path.endswith("source-directory.json"):
        rows = data.get("sources")
        count = data.get("enabled_count")
        if (data.get("scope") != "runtime_registry_plus_separately_labeled_ru_inventory"
                or data.get("live_health_verified") is not False
                or not isinstance(rows, list) or type(count) is not int):
            return ("INVALID_DIRECTORY_SCOPE", 0)
        allowed = set()
        for item in rows:
            if not isinstance(item, dict) or type(item.get("enabled")) is not bool:
                return ("INVALID_DIRECTORY_ENTRY", 0)
            key = item.get("key")
            if not isinstance(key, str) or not key or len(key) > 64 or not all(
                ch in "abcdefghijklmnopqrstuvwxyz0123456789_-" for ch in key
            ) or key in allowed:
                return ("INVALID_DIRECTORY_KEY", 0)
            allowed.add(key)
        actual = sum(row["enabled"] for row in rows)
        if count != actual:
            return ("INVALID_DIRECTORY_COUNT", 0)
        return ("REGISTRY_FLAGS_NOT_LIVE_HEALTH", count)
    if path.endswith("opportunities"):
        if data.get("source") != "stored_connector_notices":
            return ("NOT_CONNECTOR_GUEST_API", 0)
        rows = data.get("results")
        shown = data.get("shown")
        if not isinstance(rows, list) or len(rows) > 12 or type(shown) is not int or shown != len(rows):
            return ("INVALID_GUEST_RESULTS", 0)
        if data.get("limited_preview") is not True or data.get("details_locked") is not True:
            return ("GUEST_DETAIL_LOCK_NOT_VERIFIED", 0)
        if any(not isinstance(row, dict) or not set(row).issubset(ALLOWED_NOTICE)
               or not isinstance(row.get("title"), str) for row in rows):
            return ("GUEST_REDACTION_FAILED", 0)
        return ("PUBLIC_SAVED_PREVIEWS_VISIBLE" if shown else "PUBLIC_GUEST_EMPTY", shown)
    if path.endswith("market-pulse"):
        count = data.get("scanned_recent_rows")
        if (data.get("scope") != "bounded_persisted_source_observations"
                or type(count) is not int or count < 0):
            return ("INVALID_PULSE_SCOPE", 0)
        return ("MARKET_PULSE_READY", count)
    if path.endswith("market-intelligence"):
        count = data.get("scanned_recent_rows")
        if (data.get("scope") != "bounded_persisted_source_observations"
                or type(count) is not int or count < 0):
            return ("INVALID_INTELLIGENCE_SCOPE", 0)
        return ("MARKET_INTELLIGENCE_READY", count)
    return ("UNKNOWN_ROUTE", 0)


def probe(path: str) -> tuple[str, int]:
    opener = build_opener(RejectRedirects())
    request = Request(HOST + path, headers={
        "Accept": "application/json",
        "User-Agent": "VALYQON-public-readonly-release-check/1",
    }, method="GET")
    try:
        with opener.open(request, timeout=12) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "").lower()
            caching = response.headers.get("Cache-Control", "").lower()
            body = response.read(MAX_BYTES + 1)
    except HTTPError as exc:
        if exc.code in (301, 302, 303, 307, 308):
            return ("ROUTE_REDIRECTS_AWAY", exc.code)
        if exc.code == 429:
            return ("PUBLIC_RATE_LIMITED", exc.code)
        return ("HTTP_ERROR", exc.code)
    except (URLError, OSError, TimeoutError, ssl.SSLError):
        return ("TLS_OR_NETWORK_UNAVAILABLE", 0)
    if status != 200:
        return ("NON_200", status)
    if len(body) > MAX_BYTES:
        return ("OVERSIZED_PUBLIC_RESPONSE", 0)
    if "json" not in content_type:
        return ("NOT_JSON", 0)
    if "no-store" not in caching:
        return ("GUEST_CACHE_SAFETY_MISSING", 0)
    try:
        value = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return ("JSON_PARSE_FAILED", 0)
    result = validate(path, value)
    if path.endswith("source-directory.json") and result[0] == "REGISTRY_FLAGS_NOT_LIVE_HEALTH":
        keys = sorted(row["key"] for row in value["sources"] if row["enabled"])
        print("PUBLIC_RUNTIME_ENABLED_REGISTRY_KEYS=" + ",".join(keys))
        print("PUBLIC_RUNTIME_REGISTERED_SOURCE_COUNT=" + str(len(value["sources"])))
    return result


def self_test() -> None:
    valid = {
        "source": "stored_connector_notices",
        "results": [{"title": "test", "initial_price": 12, "currency": "RUB", "deadline": None}],
        "shown": 1, "limited_preview": True, "details_locked": True,
    }
    assert validate(PATHS[0], valid) == ("PUBLIC_SAVED_PREVIEWS_VISIBLE", 1)
    assert validate(PATHS[0], {**valid, "results": [{**valid["results"][0], "buyer": "private"}]})[0] == "GUEST_REDACTION_FAILED"
    assert validate(PATHS[0], {**valid, "results": [], "shown": 0}) == ("PUBLIC_GUEST_EMPTY", 0)
    assert validate(PATHS[1], {"scope": "bounded_persisted_source_observations", "scanned_recent_rows": 0}) == ("MARKET_PULSE_READY", 0)
    assert validate(PATHS[2], {"scope": "bounded_persisted_source_observations", "scanned_recent_rows": 4}) == ("MARKET_INTELLIGENCE_READY", 4)
    example = {"scope": "runtime_registry_plus_separately_labeled_ru_inventory",
               "live_health_verified": False, "sources": [
                   {"key": "mikroton_tender", "enabled": True},
                   {"key": "stan_commercial_public", "enabled": False}], "enabled_count": 1}
    assert validate(PATHS[3], example) == ("REGISTRY_FLAGS_NOT_LIVE_HEALTH", 1)
    assert validate(PATHS[3], {**example, "enabled_count": 2})[0] == "INVALID_DIRECTORY_COUNT"
    print("PUBLIC_SOURCE_AUDIT_SELF_TEST=PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument("--live", action="store_true")
    flags.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0

    statuses = [probe(path) for path in PATHS]
    for path, (status, count) in zip(PATHS, statuses):
        label = path.rsplit("/", 1)[-1].upper().replace("-", "_")
        print(f"PUBLIC_{label}_STATUS={status}")
        print(f"PUBLIC_{label}_COUNT_OR_HTTP={count}")
    visible = statuses[0][0] == "PUBLIC_SAVED_PREVIEWS_VISIBLE"
    routes_ok = all(state in ("PUBLIC_SAVED_PREVIEWS_VISIBLE", "PUBLIC_GUEST_EMPTY",
                               "MARKET_PULSE_READY", "MARKET_INTELLIGENCE_READY",
                               "REGISTRY_FLAGS_NOT_LIVE_HEALTH")
                    for state, _ in statuses)
    print("PUBLIC_GUEST_API_REACHABLE=" + ("YES" if routes_ok else "NO"))
    print("PUBLIC_REAL_PREVIEWS_VISIBLE=" + ("YES" if visible else "NO"))
    print("INDIVIDUAL_SOURCE_ACTIVATION_VERIFIED=NO")
    print("DEPLOYED_SOURCE_SET_VERIFIED=NO")
    print("RUNTIME_REGISTRY_FLAGS_ARE_NOT_WORKER_DELIVERY=YES")
    print("PRODUCTION_CHANGED=NO")
    # Failure is deliberate: a green workflow must not mean the hosted website
    # serves fresh public previews when routes are broken or no rows exist.
    return 0 if visible and routes_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
