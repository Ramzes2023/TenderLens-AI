"""Read-only Chechnya EIS transport/law diagnostics on an approved host.

No TLS bypass, no redirects, no proxy inheritance, no writes, no Telegram.
Logs only stable classifications and record counts; never URLs or notice bodies.
"""
from __future__ import annotations

import json
import socket
import ssl

import httpx

from app.monitoring.config import load_monitoring_settings
from app.sources.eis_rss import (
    SourceError, eis_tls_verify, parse_eis_feed, verify_eis_feed_law,
)
from app.sources.ru_chechnya_eis_rss import (
    SOURCE_KEY, is_chechnya_notice, select_verified_chechnya_originals,
    validate_chechnya_feed_urls,
)

MAX_RSS_BYTES = 5 * 1024 * 1024


def transport_category(error: BaseException) -> str:
    """Classify safely without printing possibly secret-bearing exception text."""
    cursor: BaseException | None = error
    observed: list[BaseException] = []
    for _ in range(8):
        if cursor is None or any(cursor is other for other in observed):
            break
        observed.append(cursor)
        cursor = cursor.__cause__ or cursor.__context__
    if any(isinstance(item, ssl.SSLError) for item in observed):
        return "TLS_CERTIFICATE_OR_HANDSHAKE"
    if any(isinstance(item, socket.gaierror) for item in observed):
        return "DNS_RESOLUTION_FAILED"
    if isinstance(error, httpx.TimeoutException):
        return "TIMEOUT"
    if isinstance(error, httpx.ConnectError):
        return "CONNECT_FAILED_UNCLASSIFIED"
    if isinstance(error, httpx.TransportError):
        return "TRANSPORT_ERROR"
    if isinstance(error, (SourceError, ValueError)):
        return "INVALID_RSS_OR_LAW"
    return "UNEXPECTED_ERROR"


def run_probe() -> dict:
    settings = load_monitoring_settings()
    if not settings.ru_chechnya_eis_enabled:
        raise ValueError("Explicit operator enable required")
    validate_chechnya_feed_urls(settings.ru_chechnya_eis_rss_urls)
    if not settings.eis_direct_enabled:
        raise ValueError("Direct EIS mode required")
    trust = eis_tls_verify(
        direct=True,
        system_trust=settings.eis_system_trust_enabled,
        ca_bundle_file=settings.ca_bundle_file,
    )
    results = []
    with httpx.Client(
        timeout=min(settings.request_timeout, 30),
        follow_redirects=False, trust_env=False,
        verify=trust, headers={"User-Agent": "TenderLensAI/0.9 (+RSS monitor)"},
    ) as client:
        for url in settings.ru_chechnya_eis_rss_urls:
            # URL is validated against an exact official HTTPS RSS path.
            with client.stream("GET", url) as response:
                status = response.status_code
                if status != 200:
                    return {"state": "HTTP_" + str(status), "strict_tls": True}
                payload = bytearray()
                for chunk in response.iter_bytes():
                    payload.extend(chunk)
                    if len(payload) > MAX_RSS_BYTES:
                        return {"state": "OVER_SIZE_LIMIT", "strict_tls": True}
                if "html" in response.headers.get("content-type", "").lower():
                    return {"state": "HTML_NOT_RSS", "strict_tls": True}
                verify_eis_feed_law(bytes(payload), "44-FZ")
                notices = parse_eis_feed(bytes(payload), source_name=SOURCE_KEY)
                results.append({
                    "official_item_count": len(notices),
                    "regional_evidence_count": sum(
                        is_chechnya_notice(item) for item in notices
                    ),
                    # EXACT same trusted card + stable number + region gate as
                    # the live ingest adapter. Merely seeing a regional label
                    # in an XML record is not acceptance.
                    "accepted_original_numbers": [
                        n.tender_number for n in select_verified_chechnya_originals(
                            notices, limit=100,
                        )
                    ],
                })
    regional = sum(item["regional_evidence_count"] for item in results)
    originals = set(
        number for result in results
        for number in result["accepted_original_numbers"]
    )
    return {
        "state": "VERIFIED_FEED_WITH_ACCEPTED_ORIGINALS" if originals
                 else "VALID_FEED_NO_ACCEPTED_ORIGINALS",
        "strict_tls": True,
        "feed_count": len(results),
        "official_item_count": sum(item["official_item_count"] for item in results),
        "regional_evidence_count": regional,
        "accepted_original_count": len(originals),
        "worker_sqlite_verified": False,
        "telegram_delivery_verified": False,
    }


def main() -> int:
    try:
        result = run_probe()
    except Exception as error:
        # Never print raw exception: httpx errors can include full query URLs.
        result = {"state": transport_category(error), "strict_tls": True}
    print("RU_CHECHNYA_EIS_SAFE_NETWORK_DIAG=" + json.dumps(result, sort_keys=True))
    return 0 if result["state"] == "VERIFIED_FEED_WITH_ACCEPTED_ORIGINALS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
