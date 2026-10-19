"""Anonymous current Samara public JSON page 0 → page 1 discovery.

RESEARCH ONLY. Independently requires twenty distinct real native published
procurement numbers over two server pages; never extends the production
connector before live proof. One first-party HTTPS grid GET and two bounded
same-origin JSON POSTs, no accounts, proxy, TLS bypass, external notification.
"""
from __future__ import annotations

import asyncio

import httpx

from app.sources.http import ConnectorTransportError, FetchPolicy, bounded_fetch, source_client
from app.sources.ru_samara_public_list import (
    GRID, HOST, JSON_URL, MAX_BYTES, public_token, public_settings, NATIVE_NUMBER,
)
from scripts.research_ru_samara_browser_grid import public_row_shape

PAGE_ROWS = 10


def distinct_two_pages(left, right) -> dict[str, int]:
    if type(left) is not dict or type(right) is not dict:
        raise ValueError("No distinct first-party JSON page responses")
    def identities(page):
        rows = page.get("items")
        if type(rows) is not list or len(rows) != PAGE_ROWS:
            raise ValueError("Original native pagination must show ten real notices per page")
        out = set()
        for row in rows:
            if type(row) is not dict:
                raise ValueError("Nonobject public native record")
            n = row.get("number")
            if type(n) is not str or NATIVE_NUMBER.fullmatch(n) is None or n in out:
                raise ValueError("Duplicate or untrusted Samara original number")
            out.add(n)
        return out
    a, b = identities(left), identities(right)
    if a & b:
        raise ValueError("Native page 1 repeats page 0; pagination not proved")
    return {"page0_native": len(a), "page1_native": len(b), "distinct": len(a | b)}


async def proof():
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 3, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=25, trust_env=False, follow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            public = await client.get(GRID, headers={"Accept": "text/html"})
            public.raise_for_status()
            if "html" not in public.headers.get("content-type", "").lower():
                raise ValueError("No official Samara public HTML grid")
            token = public_token(public.content)
            headers={
                "Accept": "application/json, text/javascript",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": GRID,
                "RequestVerificationToken": token,
            }
            records=[]
            for number in (0,1):
                settings=public_settings()
                settings["page"]=number
                response=await client.post(
                    JSON_URL, json={"settings":settings}, headers=headers,
                )
                print("RU_SAMARA_PAGE_HTTP="+str(response.status_code))
                response.raise_for_status()
                if "json" not in response.headers.get("content-type","").lower():
                    raise ValueError("No genuine native Samara public JSON")
                value=response.json()
                # Enforce original first-party title, buyer, ID and same-host
                # detail-reference shape independently for every page.
                shape=public_row_shape(response.content)
                if shape["rows"] != PAGE_ROWS or shape["same_host_detail_refs"] != PAGE_ROWS:
                    raise ValueError("Missing original native records on a page")
                records.append(value)
            return distinct_two_pages(*records)


def main():
    try:
        report=asyncio.run(proof())
    except (ConnectorTransportError, ValueError, TypeError, httpx.HTTPError,
            OSError, TimeoutError) as exc:
        print("RU_SAMARA_NATIVE_PAGE2=BLOCKED_"+type(exc).__name__)
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_SAMARA_NATIVE_PAGE2_DISTINCT="+str(report["distinct"]))
    print("PRODUCTION_CHANGED=NO")
    return 0 if report["distinct"]==20 else 2


if __name__ == "__main__":
    raise SystemExit(main())
