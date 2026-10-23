"""Safe official Roseltorg read-only diagnostic, no tender/customer data in logs."""
from __future__ import annotations
import asyncio
import httpx
from app.sources.roseltorg_public import (
    HOST, LIST_URL, MAX_BYTES, parse_roseltorg_links, parse_roseltorg_detail,
)
from app.sources.http import FetchPolicy, bounded_fetch, source_client, ConnectorTransportError


async def check():
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 4, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=24, trust_env=False, follow_redirects=False,
            headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
        ) as client:
            try:
                r = await client.get(LIST_URL)
                r.raise_for_status()
                print("RU_ROSELTORG_LIST_STATUS=" + str(r.status_code))
                print("RU_ROSELTORG_LIST_BYTES=" + str(len(r.content)))
                links = parse_roseltorg_links(r.content)
                print("RU_ROSELTORG_LIST_LINKS=" + str(len(links)))
            except httpx.HTTPStatusError as e:
                print("RU_ROSELTORG_LIST_HTTP_STATUS=" + str(e.response.status_code))
                return 1
            except (ValueError, ConnectorTransportError, httpx.TransportError) as e:
                print("RU_ROSELTORG_LIST_BLOCKED=" + type(e).__name__)
                if type(e) is ConnectorTransportError:
                    print("RU_ROSELTORG_TRANSPORT_RETRYABLE=" + str(e.retryable))
                return 1
            verified = 0
            for identity, url in links:
                try:
                    detail = await client.get(url)
                    detail.raise_for_status()
                    print("RU_ROSELTORG_DETAIL_HTTP_STATUS=" + str(detail.status_code))
                    parse_roseltorg_detail(detail.content, identity=identity, url=url)
                    verified += 1
                except httpx.HTTPStatusError as e:
                    print("RU_ROSELTORG_DETAIL_HTTP_STATUS=" + str(e.response.status_code))
                except (ValueError, ConnectorTransportError, httpx.TransportError) as e:
                    print("RU_ROSELTORG_DETAIL_BLOCKED=" + type(e).__name__)
                    if type(e) is ValueError:
                        allow = {
                            "Official Roseltorg detail breadcrumb identity mismatch",
                            "Roseltorg official detail title is ambiguous",
                            "Invalid Roseltorg public HTML",
                        }
                        if str(e) in allow:
                            print("RU_ROSELTORG_DETAIL_REASON=" + str(e))
            print("RU_ROSELTORG_GENUINE_VERIFIED=" + str(verified))
            return 0 if verified else 1


def main():
    try:
        status = asyncio.run(check())
    except Exception as e:
        print("RU_ROSELTORG_DIAGNOSTIC_BLOCKED=" + type(e).__name__)
        return 1
    print("PRODUCTION_CHANGED=NO")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
