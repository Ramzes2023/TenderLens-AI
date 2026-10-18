"""Read-only Murmansk first-party discovery endpoint reconnaissance.

The fixed /site/GzwSP/NoticesJson path was observed in the *real* official
NoticesGrid public HTML on hosted CI. Never claim valid source acquisition based
only on HTTP 200, script metadata, canned fixture, or response size.
"""
from __future__ import annotations

import asyncio
import json
import httpx
from app.sources.http import FetchPolicy, bounded_fetch, source_client, ConnectorTransportError

HOST = "gz-murman.ru"
URL = "https://gz-murman.ru/site/GzwSP/NoticesJson"
QUERY = {"page": "1", "rows": "5", "sidx": "", "sord": "desc"}
MAX_BYTES = 1_800_000


async def probe():
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 1, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=24,
            trust_env=False,
            follow_redirects=False,
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
        ) as client:
            result = await client.get(URL, params=QUERY)
            result.raise_for_status()
            if "json" not in result.headers.get("content-type", "").lower():
                print("RU_MURMANSK_JSON=NOT_JSON")
                return 2
            data = result.json()
            print("RU_MURMANSK_JSON_TYPE=" + type(data).__name__)
            if type(data) is not dict:
                print("RU_MURMANSK_JSON=INVALID_ROOT")
                return 2
            # Keys are schema information only: restrict untrusted output.
            public_keys = sorted(
                x for x in data if type(x) is str and x.isascii()
                and x.replace("_", "").isalnum() and len(x) <= 32
            )
            print("RU_MURMANSK_JSON_KEYS=" + ",".join(public_keys[:16]))
            rows = data.get("rows")
            if type(rows) is not list:
                print("RU_MURMANSK_JSON=NO_ROWS_ARRAY")
                return 2
            print("RU_MURMANSK_JSON_ROWS=" + str(len(rows)))
            if rows and type(rows[0]) is dict:
                cols = sorted(k for k in rows[0] if type(k) is str and k.isascii()
                              and k.replace("_", "").isalnum() and len(k) <= 36)
                print("RU_MURMANSK_JSON_FIRST_ROW_KEYS=" + ",".join(cols[:20]))
                cells = rows[0].get("cell")
                if type(cells) is list:
                    print("RU_MURMANSK_JSON_CELL_COUNT=" + str(len(cells)))
            # Even a valid original JSON index is ONLY research; no SQL or
            # source adapter exists and no original details were verified.
            print("RU_MURMANSK_JSON=DISCOVERY_ONLY")
            return 0 if rows else 2


def main():
    try:
        return asyncio.run(probe())
    except (ValueError, json.JSONDecodeError, httpx.HTTPError, OSError,
            ConnectorTransportError, TimeoutError) as error:
        print("RU_MURMANSK_JSON=BLOCKED_" + type(error).__name__)
        if isinstance(error, ConnectorTransportError):
            print("RU_MURMANSK_JSON_RETRYABLE=" + str(error.retryable))
        return 2
    finally:
        print("PRODUCTION_CHANGED=NO")


if __name__ == "__main__":
    raise SystemExit(main())
