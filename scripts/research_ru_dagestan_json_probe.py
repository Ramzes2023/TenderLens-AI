"""Read-only first-party Dagestan JSON registry candidate, no fixture fallback.

An unverified JSON result is NOT an integrated procurement source. Origin,
endpoint and query are fixed, no redirects, tokens, proxies, browser automation.
"""
from __future__ import annotations

import asyncio
import json

import httpx
from app.sources.http import (
    FetchPolicy, bounded_fetch, source_client, ConnectorTransportError,
)

HOST = "goszakaz.e-dag.ru"
INDEX = "https://goszakaz.e-dag.ru/smallpurchases/GzwSP/NoticesGrid"
PATH = "/smallpurchases/GzwSP/NoticesJson"
URL = "https://" + HOST + PATH
MAX_BYTES = 1_800_000


async def probe():
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 2, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=24, trust_env=False, follow_redirects=False,
            headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
        ) as index_client:
            resp = await index_client.get(INDEX)
            resp.raise_for_status()
            if "html" not in resp.headers.get("content-type", "").lower():
                print("RU_DAG_JSON_STAGE=NO_FIRSTPARTY_HTML")
                return 2
            if PATH.encode() not in resp.content:
                print("RU_DAG_JSON_STAGE=ROUTE_NOT_PUBLISHED")
                return 2
        # Separate anonymous client: do not transfer cookies/session/auth state.
        async with source_client(
            timeout=24, trust_env=False, follow_redirects=False,
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
        ) as client:
            response = await client.get(
                URL, params={"page": "1", "rows": "5", "sidx": "", "sord": "desc"},
            )
            response.raise_for_status()
            if "json" not in response.headers.get("content-type", "").lower():
                print("RU_DAG_JSON_STAGE=NOT_JSON")
                return 2
            data = response.json()
            if type(data) is not dict:
                print("RU_DAG_JSON_STAGE=NO_OBJECT")
                return 2
            rows = data.get("rows")
            if type(rows) is not list or not rows:
                print("RU_DAG_JSON_STAGE=NO_ORIGINAL_ROWS")
                return 2
            print("RU_DAG_JSON_ROW_COUNT=" + str(len(rows)))
            print("RU_DAG_JSON_SCHEMA_KEYS=" + ",".join(
                k for k in sorted(data)[:15]
                if type(k) is str and k.isascii() and k.replace("_", "").isalnum()
            ))
            print("RU_DAG_JSON_STAGE=RESEARCH_ROWS_ONLY")
            return 0


def main():
    try:
        result = asyncio.run(probe())
    except (ValueError, ConnectorTransportError, httpx.HTTPError, OSError,
            TimeoutError, json.JSONDecodeError) as error:
        print("RU_DAG_JSON_STAGE=BLOCKED_" + type(error).__name__)
        if isinstance(error, ConnectorTransportError):
            print("RU_DAG_JSON_RETRYABLE=" + str(error.retryable))
        result = 2
    print("PRODUCTION_CHANGED=NO")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
