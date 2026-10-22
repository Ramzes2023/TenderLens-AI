"""Read-only GPB transport stages: true first-party GETs, redacted diagnostics.

This is NOT an ingest success proof. It uses no credentials, bypasses, proxy,
redirects, production data, non-public IP or unverified mirrors.
"""
from __future__ import annotations
import asyncio
import httpx

from app.sources.gpb_etp_public import (
    HOST, LIST_URL, MAX_BYTES, parse_gpb_public_links, parse_gpb_verified_detail,
)
from app.sources.http import (
    ConnectorTransportError, FetchPolicy, bounded_fetch, source_client,
)

REASONS = frozenset({
    "network", "public_ip", "tls_certificate", "http_status",
    "http_transient", "response_size", "policy",
})


def _cause_category(error):
    seen = set()
    causes = [error]
    for _ in range(8):
        if not causes:
            break
        item = causes.pop(0)
        if id(item) in seen:
            continue
        seen.add(id(item))
        if isinstance(item, httpx.ConnectTimeout):
            return "connect_timeout"
        if isinstance(item, httpx.ReadTimeout):
            return "read_timeout"
        if isinstance(item, httpx.ConnectError):
            return "connect_error"
        if isinstance(item, httpx.ReadError):
            return "read_error"
        if item.__cause__ is not None:
            causes.append(item.__cause__)
        if item.__context__ is not None:
            causes.append(item.__context__)
    return "unclassified"


async def probe():
    stage = "LIST_GET"
    try:
        with bounded_fetch(FetchPolicy(frozenset({HOST}), 2, max_bytes=MAX_BYTES)):
            async with source_client(
                timeout=25, follow_redirects=False, trust_env=False,
                headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
            ) as client:
                response = await client.get(LIST_URL)
                if "html" not in response.headers.get("content-type", "").lower():
                    print("GPB_STAGE=LIST_NON_HTML")
                    return 2
                found = parse_gpb_public_links(response.content, limit=1)
                print("GPB_LIST_FIRSTPARTY_LINKS=1")
                stage = "DETAIL_GET"
                identity, url = found[0]
                detail = await client.get(url)
                if "html" not in detail.headers.get("content-type", "").lower():
                    print("GPB_STAGE=DETAIL_NON_HTML")
                    return 2
                parse_gpb_verified_detail(detail.content, identity, url)
                print("GPB_STAGE=FIRSTPARTY_FIRST_DETAIL_VERIFIED")
                print("GPB_FIRST_PARTY_REQUESTS=2")
                print("PRODUCTION_CHANGED=NO")
                return 0
    except ConnectorTransportError as error:
        print("GPB_STAGE=" + stage)
        reason = error.reason if error.reason in REASONS else "unclassified"
        print("GPB_TRANSPORT_REASON=" + reason)
        print("GPB_TRANSPORT_CAUSE=" + _cause_category(error))
        print("GPB_RETRYABLE=" + str(error.retryable))
    except ValueError:
        print("GPB_STAGE=" + stage)
        print("GPB_PUBLISHER_CONTENT=UNVERIFIED")
    except Exception as error:
        print("GPB_STAGE=" + stage)
        print("GPB_FAILURE_CLASS=" + type(error).__name__[:70])
    print("PRODUCTION_CHANGED=NO")
    return 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(probe()))
