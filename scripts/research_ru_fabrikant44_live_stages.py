"""Read-only official soap4 Fabrikant original source failure-stage diagnosis.

No log of source HTML, cookies, tokens or customer data. Not acceptance proof.
"""
import asyncio
import httpx
from app.sources.http import ConnectorTransportError, FetchPolicy, bounded_fetch, source_client
from app.sources.fabrikant_44_public import (
    HOST, LIST_URL, MAX_BYTES, parse_fabrikant44_listing, parse_fabrikant44_detail,
)


async def probe():
    stage = "LIST_GET"
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 4, max_bytes=MAX_BYTES)):
        try:
            async with source_client(
                timeout=25, follow_redirects=False, trust_env=False,
                headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
            ) as client:
                page = await client.get(LIST_URL)
                print("FABRIKANT_LIST_STATUS=" + str(page.status_code))
                print("FABRIKANT_LIST_BYTES=" + str(len(page.content)))
                print("FABRIKANT_LIST_HTML=" + str("html" in page.headers.get("content-type", "").lower()))
                page.raise_for_status()
                stage = "LIST_PARSE"
                items = parse_fabrikant44_listing(page.content, limit=2)
                print("FABRIKANT_LIST_NATIVE_CANDIDATES=" + str(len(items)))
                verified = 0
                for identity, url, title in items:
                    stage = "DETAIL_GET"
                    detail = await client.get(url)
                    print("FABRIKANT_DETAIL_STATUS=" + str(detail.status_code))
                    detail.raise_for_status()
                    stage = "DETAIL_PARSE"
                    parse_fabrikant44_detail(detail.content, identity=identity, url=url, title=title)
                    verified += 1
                print("FABRIKANT_INDEPENDENT_ORIGINALS=" + str(verified))
                print("FABRIKANT_DIAG=" + ("TWO_ORIGINALS_POSSIBLE" if verified == 2 else "INSUFFICIENT"))
                print("PRODUCTION_CHANGED=NO")
                return 0 if verified == 2 else 2
        except (ConnectorTransportError, httpx.HTTPError, ValueError, OSError, TimeoutError) as exc:
            print("FABRIKANT_FAILURE_STAGE=" + stage)
            print("FABRIKANT_FAILURE_CLASS=" + type(exc).__name__)
            if isinstance(exc, ConnectorTransportError):
                print("FABRIKANT_RETRYABLE=" + str(exc.retryable))
            print("FABRIKANT_DIAG=BLOCKED")
            print("PRODUCTION_CHANGED=NO")
            return 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(probe()))
