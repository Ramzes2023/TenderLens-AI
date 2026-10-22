"""Read-only anonymous POST contract for a FIRST-PARTY Dagestan public listing.

This is an independent research-only route probe, not a production adapter.
It does not claim real opportunities until independent first-party details are
proven. Exact route must be advertised in original unmodified HTML.
"""
from __future__ import annotations

import asyncio
import json

import httpx

from app.sources.http import (
    ConnectorTransportError, FetchPolicy, bounded_fetch, source_client,
)

HOST = "goszakaz.e-dag.ru"
INDEX = "https://" + HOST + "/smallpurchases/GzwSP/NoticesGrid"
PATH = "/smallpurchases/GzwSP/NoticesJson"
URL = "https://" + HOST + PATH
MAX_BYTES = 1_800_000
LIMIT = 5
# Standard anonymous jqGrid form, without any filters, credentials or private
# identifiers. Must not be interpreted as a documented POST API schema.
FORM = {"page": "1", "rows": str(LIMIT), "sidx": "", "sord": "desc"}


def published_route(html: bytes) -> bool:
    """Never probe a guessed private endpoint absent from the public HTML."""
    return (type(html) is bytes and 0 < len(html) <= MAX_BYTES
            and PATH.encode("ascii") in html
            and b"\x00" not in html)


def parse_public_json(body: bytes, content_type: str, *, max_rows: int = LIMIT):
    # Legacy anonymous form requests up to five. The first-party native grid
    # explicitly requests rp=10; callers must supply that bounded page limit.
    # Never infer an unbounded allowance from a totalRows counter.
    if type(max_rows) is not int or not 2 <= max_rows <= 10:
        raise ValueError("Invalid bounded public grid page size")
    if type(body) is not bytes or not 0 < len(body) <= MAX_BYTES:
        raise ValueError("No bounded original JSON response")
    if "application/json" not in content_type.lower():
        raise ValueError("No advertised JSON media type")
    try:
        data = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("Not a real JSON response") from None
    if type(data) is not dict:
        raise ValueError("No JSON registry object")
    # The live government grid (unlike generic jqGrid examples) exposes
    # {items, page, totalAmount, totalRows}. Only accept this observed
    # first-party shape or the strictly bounded legacy rows form.
    if "items" in data:
        rows = data["items"]
        if (type(data.get("totalRows")) is not int or data["totalRows"] < 2
                or type(data.get("page")) is not int or data["page"] < 0):
            raise ValueError("Invalid original public registry pagination")
    else:
        rows = data.get("rows")
    if type(rows) is not list or not 2 <= len(rows) <= max_rows:
        raise ValueError("No two real first-party public listing rows")
    keys = sorted(k for k in data if isinstance(k, str) and k.isascii()
                  and k.replace("_", "").isalnum())[:15]
    row_shapes = []
    for row in rows[:2]:
        if type(row) is dict:
            shape = sorted(str(k) for k in row
                           if type(k) is str and k.isascii()
                           and k.replace("_", "").isalnum())[:20]
            if not shape:
                raise ValueError("Empty native regional record")
            row_shapes.append(("object", shape))
        elif type(row) is list and len(row) >= 2:
            row_shapes.append(("array", len(row)))
        else:
            raise ValueError("Unexpected or unverified native row schema")
    # Schema discovery does not prove original cards, notice identity, buyer,
    # price, deadlines, or tenant-scoped delivery.
    return len(rows), keys, row_shapes


async def probe():
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 2, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=24, trust_env=False, follow_redirects=False,
            headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
        ) as listing_client:
            html = await listing_client.get(INDEX)
            if "html" not in html.headers.get("content-type", "").lower():
                raise ValueError("Official first-party grid page not HTML")
            if not published_route(html.content):
                raise ValueError("Original HTML does not publish fixed read-only JSON grid")
        # Anonymous independent request with no transfer of cookies / auth.
        async with source_client(
            timeout=24, trust_env=False, follow_redirects=False,
            headers={
                "Accept": "application/json, text/javascript",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": INDEX,
                "User-Agent": "Mozilla/5.0",
            },
        ) as client:
            response = await client.post(URL, data=FORM)
            count, keys, shapes = parse_public_json(
                response.content, response.headers.get("content-type", ""),
            )
            print("RU_DAG_PUBLIC_POST_ROWS=" + str(count))
            print("RU_DAG_POST_ROOT_KEYS=" + ",".join(keys))
            for i, (kind, structure) in enumerate(shapes, 1):
                print("RU_DAG_POST_ROW_" + str(i) + "_SHAPE=" + kind)
                print("RU_DAG_POST_ROW_" + str(i) + "_FIELDS=" +
                      (",".join(structure) if kind == "object" else str(structure)))
            print("RU_DAG_PUBLIC_POST=SCHEMA_OBSERVED_RESEARCH_ONLY")
            print("ORIGINAL_NOTICE_IDENTITY_PROVED=NO")
            print("PERSISTED_SEARCH_PROVED=NO")
            return 0


def main():
    try:
        return asyncio.run(probe())
    except (ValueError, ConnectorTransportError, httpx.HTTPError,
            OSError, TimeoutError) as error:
        print("RU_DAG_PUBLIC_POST=BLOCKED_" + type(error).__name__)
        if isinstance(error, ConnectorTransportError):
            print("RU_DAG_RETRYABLE=" + str(error.retryable))
        return 2
    finally:
        print("PRODUCTION_CHANGED=NO")


if __name__ == "__main__":
    raise SystemExit(main())
