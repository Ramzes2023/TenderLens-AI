"""Read-only exact first-party Samara public JSON grid research, not integration.

One anonymous GET grid + one POST to its explicitly published JSON route.
Same-session public CSRF, no secrets, account, redirects, proxy, unsafe IP or TLS
bypass. Strict native listing records are not independently verified details.
"""
from __future__ import annotations

import asyncio
import json

import httpx

from app.sources.http import (
    ConnectorTransportError, FetchPolicy, bounded_fetch, source_client,
)
from app.sources.ru_dagestan_public_list import public_settings, public_token
from scripts.research_ru_samara_browser_grid import (
    HOST, GRID, JSON_PATH, MAX_BYTES, public_row_shape,
)

URL = "https://" + HOST + JSON_PATH


async def proof() -> dict[str, int]:
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 2, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=25,
            trust_env=False,
            follow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            index = await client.get(GRID, headers={"Accept": "text/html"})
            index.raise_for_status()
            if "html" not in index.headers.get("content-type", "").lower():
                raise ValueError("No Samara public HTML grid")
            # This is a FIRST-PARTY anonymous token, not user authentication.
            # The proven same-family GzwSP grid publishes the JSON path.
            token = public_token(index.content)
            response = await client.post(
                URL,
                json={"settings": public_settings()},
                headers={
                    "Accept": "application/json, text/javascript",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": GRID,
                    "RequestVerificationToken": token,
                },
            )
            response.raise_for_status()
            if "application/json" not in response.headers.get("content-type", "").lower():
                raise ValueError("No official public JSON response")
            proof = public_row_shape(response.content)
            if proof["native_ids"] < 2 or proof["same_host_detail_refs"] < 2:
                raise ValueError("No two genuine same-host Samara list references")
            return proof


def main() -> int:
    try:
        result = asyncio.run(proof())
    except (ValueError, TypeError, ConnectorTransportError, httpx.HTTPError,
            OSError, TimeoutError, json.JSONDecodeError) as e:
        print("RU_SAMARA_NATIVE_HTTP=BLOCKED_" + type(e).__name__)
        if isinstance(e, ConnectorTransportError):
            print("RU_SAMARA_TRANSPORT_RETRYABLE=" + str(e.retryable))
        print("SOURCE_INTEGRATED=NO")
        print("PRODUCTION_CHANGED=NO")
        return 2
    for key, count in sorted(result.items()):
        print("RU_SAMARA_NATIVE_HTTP_" + key.upper() + "=" + str(count))
    print("RU_SAMARA_NATIVE_HTTP=PUBLIC_LIST_RESEARCH_ONLY")
    print("INDEPENDENT_ORIGINAL_DETAILS_VERIFIED=NO")
    print("SOURCE_INTEGRATED=NO")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
