"""Independent read-only diagnostic for official Ingushetia EIS 44-FZ RSS.

The genuine leased Worker gate in PR #313 currently fails with opaque
`handler_error`. This diagnostic distinguishes pinned-CA construction,
official RSS network/HTTP, law verification, absent regional metadata and
source result count without leaking exception text or weakening controls.

A zero-exception exit is *diagnostic only*, not evidence of operational
Worker, tenant isolation, alerts, deduplication or public deployment.
"""
from __future__ import annotations

import asyncio
import json

from app.sources.http import ConnectorTransportError
from app.sources.ru_ingushetia_eis44 import IngushetiaEis44Source, SOURCE_ID, RSS_URL
from app.sources.eis_rss import SourceError
from app.sources.eis_pinned_ca import select_verified_eis_ca

SAFE_CA_FAILURE = frozenset({"OSError", "ValueError", "SourceError"})
SAFE_NETWORK_FAILURE = frozenset({
    "network", "tls_certificate", "http_status", "http_transient",
    "policy", "public_ip", "response_size",
})


def classify_exception(exc: BaseException) -> str:
    if isinstance(exc, ConnectorTransportError):
        code = getattr(exc, "reason", "policy")
        return "transport_" + code if code in SAFE_NETWORK_FAILURE else "transport_unclassified"
    if isinstance(exc, SourceError):
        # No upstream exception text, URL, html, cert material, or stack.
        return "source_contract"
    if isinstance(exc, (OSError, TimeoutError)):
        return "network_or_tls"
    return "unexpected_" + type(exc).__name__ if type(exc).__name__ in {
        "ValueError", "TypeError", "RuntimeError",
    } else "unexpected_unclassified"


async def fetch_originals(source) -> dict:
    notices = await source.fetch(limit=10)
    return {
        "source": SOURCE_ID,
        "originals": len(notices),
        "unique_original_numbers": len({
            n.tender_number for n in notices if type(n.tender_number) is str
        }),
        "official_origin": all(
            n.url.startswith("https://zakupki.gov.ru/epz/order/notice/")
            for n in notices
        ),
        "regional_metadata_validated_by_adapter": True,
    }


def main() -> int:
    if not RSS_URL.startswith(
        "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?"
    ):
        print("INGUSHETIA_EIS_DIAGNOSTIC=BLOCKED_UNSAFE_URL")
        return 2
    try:
        select_verified_eis_ca()
    except (OSError, ValueError, SourceError):
        print("INGUSHETIA_EIS_DIAGNOSTIC=BLOCKED_PINNED_CA")
        print("PRODUCTION_CHANGED=NO")
        return 0
    try:
        source = IngushetiaEis44Source(timeout=20)
        proof = asyncio.run(fetch_originals(source))
        print("INGUSHETIA_EIS_RSS_ORIGINALS=" + json.dumps(proof,sort_keys=True))
        print("INGUSHETIA_EIS_DIAGNOSTIC=FETCH_COMPLETE")
    except Exception as exc:
        print("INGUSHETIA_EIS_DIAGNOSTIC="+classify_exception(exc))
    print("LEASED_WORKER_SQL_SEARCH=NOT_VERIFIED")
    print("FIVE_SOURCE_PUBLIC_RELEASE_UNCHANGED=YES")
    print("REGIONAL_SOURCE_ENABLED=NO")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
