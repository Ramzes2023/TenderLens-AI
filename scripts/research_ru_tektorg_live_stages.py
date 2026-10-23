"""Strict first-party TEK-Torg HTTPS diagnostic; no data is ingested.

Emits only status/stage enums, never titles, page HTML, payload or credentials.
A nonzero exit code is NOT waived by CI. All requests share one pinned host.
"""
import asyncio
import httpx

from app.sources.http import FetchPolicy, bounded_fetch, source_client, ConnectorTransportError
from app.sources.tektorg_public_html import (
    HOST, LIST_URL, MAX_BYTES, parse_public_listing, validate_public_detail,
)


async def inspect():
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 3, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=25, trust_env=False, follow_redirects=False,
            headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
        ) as client:
            response = await client.get(LIST_URL)
            if response.status_code != 200:
                print("RU_TEKTORG_LIST_STATUS=" + str(response.status_code))
                print("RU_TEKTORG_STAGE=OFFICIAL_LIST_HTTP")
                return 2
            if "html" not in response.headers.get("content-type", "").lower():
                print("RU_TEKTORG_STAGE=OFFICIAL_LIST_NOT_HTML")
                return 2
            try:
                cards = parse_public_listing(response.content, limit=2)
            except ValueError:
                print("RU_TEKTORG_STAGE=OFFICIAL_LIST_CARDS_NOT_VERIFIED")
                return 2
            if len(cards) != 2:
                print("RU_TEKTORG_STAGE=TOO_FEW_ORIGINAL_LINKS")
                return 2
            for identity, url, title in cards:
                detail = await client.get(url)
                if detail.status_code != 200:
                    print("RU_TEKTORG_DETAIL_STATUS=" + str(detail.status_code))
                    print("RU_TEKTORG_STAGE=ORIGINAL_DETAIL_HTTP")
                    return 2
                if "html" not in detail.headers.get("content-type", "").lower():
                    print("RU_TEKTORG_STAGE=ORIGINAL_DETAIL_NOT_HTML")
                    return 2
                try:
                    validate_public_detail(detail.content, identity=identity, title=title)
                except ValueError:
                    print("RU_TEKTORG_STAGE=ORIGINAL_DETAIL_MISMATCH")
                    return 2
            print("RU_TEKTORG_STAGE=TWO_INDEPENDENT_VERIFIED_DETAILS")
            return 0


def main():
    try:
        code = asyncio.run(inspect())
    except ConnectorTransportError as error:
        print("RU_TEKTORG_STAGE=BLOCKED_CONNECTOR_TRANSPORT")
        print("RU_TEKTORG_RETRYABLE=" + str(error.retryable))
        code = 2
    except (httpx.HTTPError, OSError, ValueError, TimeoutError) as error:
        print("RU_TEKTORG_STAGE=BLOCKED_" + type(error).__name__)
        code = 2
    print("PRODUCTION_CHANGED=NO")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
