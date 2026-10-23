"""Read-only GPB transport stages: true first-party GETs, redacted diagnostics.

This is NOT an ingest success proof. It uses no credentials, bypasses, proxy,
redirects, production data, non-public IP or unverified mirrors.
"""
from __future__ import annotations
import asyncio
import httpx

from app.sources.gpb_etp_public import (
    HOST, LIST_URL, MAX_BYTES, parse_gpb_public_links,
    parse_gpb_official_rss, parse_gpb_verified_detail,
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
        with bounded_fetch(FetchPolicy(frozenset({HOST}), 5, max_bytes=MAX_BYTES)):
            async with source_client(
                timeout=25, follow_redirects=False, trust_env=False,
                headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
            ) as client:
                try:
                    response = await client.get(LIST_URL)
                    response.raise_for_status()
                    if "html" not in response.headers.get("content-type", "").lower():
                        raise ValueError("GPB list not HTML")
                    found = parse_gpb_public_links(response.content, limit=3)
                    print("GPB_DISCOVERY=PUBLIC_HTML")
                except (ConnectorTransportError, httpx.HTTPStatusError,
                        httpx.TransportError, ValueError, TimeoutError, OSError):
                    stage = "OFFICIAL_RSS_GET"
                    feed = await client.get(f"https://{HOST}/procedures.rss",
                                            headers={"Accept": "application/rss+xml, application/xml"})
                    feed.raise_for_status()
                    if not any(x in feed.headers.get("content-type", "").lower()
                               for x in ("rss", "xml")):
                        raise ValueError("Official GPB RSS not XML")
                    found = parse_gpb_official_rss(feed.content, limit=3)
                    print("GPB_DISCOVERY=OFFICIAL_RSS")
                print("GPB_LIST_FIRSTPARTY_LINKS=" + str(len(found)))
                stage = "DETAIL_GET"
                stale = 0
                for identity, url in found:
                    try:
                        detail = await client.get(url)
                        if "html" not in detail.headers.get("content-type", "").lower():
                            stale += 1
                            continue
                        parse_gpb_verified_detail(detail.content, identity, url)
                    except ConnectorTransportError as error:
                        # A deleted/not-public original cannot be used; never
                        # mask a network/TLS failure as a stale individual card.
                        if error.reason != "http_status":
                            raise
                        stale += 1
                        continue
                    except ValueError:
                        stale += 1
                        continue
                    print("GPB_STAGE=FIRSTPARTY_DETAIL_VERIFIED")
                    print("GPB_STALE_DETAILS_IGNORED=" + str(stale))
                    print("PRODUCTION_CHANGED=NO")
                    return 0
                print("GPB_STAGE=NO_VERIFIED_FIRSTPARTY_DETAIL")
                print("GPB_STALE_DETAILS_IGNORED=" + str(stale))
                print("PRODUCTION_CHANGED=NO")
                return 2
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
