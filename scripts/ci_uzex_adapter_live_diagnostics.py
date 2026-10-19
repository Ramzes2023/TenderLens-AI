"""Read-only live UzEx adapter diagnostics (safe error categories only).

Public original API only; no customer text, IDs, prices, token, or raw URLs
printed to CI. Strict original parser is exercised against each genuine row.
"""
import asyncio
import json
from collections import Counter

from app.sources.http import FetchPolicy, bounded_fetch, source_client
from app.sources.eis_rss import SourceError
from app.sources.uz_uzex import (
    HOST, API_URL, PER_TYPE, MAX_BODY, parse_uzex_tradelist
)

def probe_row(row, type_id):
    try:
        parse_uzex_tradelist([row], type_id=type_id)
    except SourceError as error:
        # Only code-owned, fixed parser category strings, never response text.
        return str(error)
    return "NORMALIZED"

async def probe():
    result = {}
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 2, max_bytes=MAX_BODY)):
        async with source_client(timeout=25, trust_env=False, follow_redirects=False) as client:
            for type_id in (1, 2):
                reply = await client.post(
                    API_URL,
                    json={"TypeId": type_id, "From": 1, "To": PER_TYPE, "System_Id": 0},
                    headers={"Accept": "application/json", "User-Agent": "VALYQON-public-procurement-verifier/1.0"},
                )
                reply.raise_for_status()
                if "json" not in reply.headers.get("content-type","").lower() or len(reply.content)>MAX_BODY:
                    raise ValueError("Official response media or size mismatch")
                data = reply.json()
                if type(data) is not list or not 0<len(data)<=PER_TYPE:
                    raise ValueError("Original list shape mismatch")
                counts=Counter(probe_row(row,type_id) for row in data)
                result[str(type_id)]={"total":len(data),"safe_parser_categories":dict(sorted(counts.items()))}
    return result

def main():
    try:
        result=asyncio.run(probe())
    except Exception as exc:
        print("UZEX_ADAPTER_DIAG=BLOCKED_"+type(exc).__name__)
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("UZEX_ADAPTER_DIAG="+json.dumps(result,sort_keys=True))
    print("PRODUCTION_CHANGED=NO")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
