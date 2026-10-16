"""Strict live evidence for a documented public Russian procurement API.

Only real remote procurement records count. No fixtures, mock transports,
credentials, source registrations, customer data, production writes or TLS
exceptions. One bounded API list request per open/archive endpoint and at most
one independent published detail-card request.
"""
from __future__ import annotations

import asyncio
import json
from urllib.parse import urlsplit

from app.sources.http import FetchPolicy, bounded_fetch, source_client

HOST = "tender.mt52.ru"
BASE = "https://tender.mt52.ru/api/v1"
URLS = (BASE + "/tenders?page=1&page_size=10",
        BASE + "/tenders/archive?page=1&page_size=10")
MAX_BYTES = 1_048_576


def public_records(body: bytes) -> tuple[list[dict], int]:
    if not isinstance(body, bytes) or len(body) > MAX_BYTES:
        raise ValueError("RESPONSE_INVALID")
    doc = json.loads(body)
    if not isinstance(doc, dict):
        raise ValueError("SCHEMA_INVALID")
    meta, records = doc.get("meta"), doc.get("items")
    if not isinstance(meta, dict) or not isinstance(records, list):
        raise ValueError("SCHEMA_INVALID")
    if meta.get("api_version") != "v1" or not 0 <= len(records) <= 10:
        raise ValueError("SCHEMA_INVALID")
    count = 0
    for row in records:
        if not isinstance(row, dict):
            raise ValueError("ITEM_INVALID")
        identity, title, url = row.get("id"), row.get("title"), row.get("portal_url")
        if type(identity) is not int or identity <= 0 or not isinstance(title, str) or not title.strip():
            raise ValueError("ITEM_INVALID")
        if type(url) is not str or not url.startswith(f"https://{HOST}/tenders/"):
            raise ValueError("ITEM_INVALID")
        parts = urlsplit(url)
        if (parts.scheme != "https" or parts.netloc != HOST
                or parts.query or parts.fragment
                or parts.path != f"/tenders/{identity}"):
            raise ValueError("ITEM_INVALID")
        count += 1
    return records, count


async def acceptance() -> dict:
    result = {"listing_200": 0, "real_notice_count": 0,
              "detail_http_200": False, "detail_identity_verified": False}
    real_items = []
    # Exact-host allowlist, direct public-IP transport, no env proxies,
    # no redirects and bounded decompression enforced in app.sources.http.
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 3, max_bytes=MAX_BYTES)):
        async with source_client(timeout=15, trust_env=False, follow_redirects=False,
                                 headers={"Accept": "application/json"}) as client:
            for url in URLS:
                response = await asyncio.wait_for(client.get(url), timeout=20)
                response.raise_for_status()
                if response.status_code != 200 or "json" not in response.headers.get("content-type", ""):
                    raise ValueError("LISTING_NOT_JSON_200")
                result["listing_200"] += 1
                rows, count = public_records(response.content)
                result["real_notice_count"] += count
                real_items.extend(rows)
            if real_items:
                first = real_items[0]
                response = await asyncio.wait_for(
                    client.get(f"{BASE}/tenders/{first['id']}"), timeout=20)
                response.raise_for_status()
                result["detail_http_200"] = response.status_code == 200
                detail = json.loads(response.content)
                result["detail_identity_verified"] = (
                    type(detail) is dict
                    and detail.get("id") == first["id"]
                    and detail.get("title") == first["title"]
                )
    return result


def main() -> int:
    try:
        report = asyncio.run(acceptance())
    except Exception as error:
        print("MIKROTON_REAL_API=BLOCKED", flush=True)
        print("FAILURE_CLASS=" + type(error).__name__, flush=True)
        print("PRODUCTION_CHANGED=NO", flush=True)
        return 1
    print("MIKROTON_REAL_API_EVIDENCE=" +
          json.dumps(report, sort_keys=True), flush=True)
    success = (report["listing_200"] == 2
               and report["real_notice_count"] > 0
               and report["detail_http_200"]
               and report["detail_identity_verified"])
    print("MIKROTON_REAL_API=" + ("PASS" if success else "NOT_VERIFIED"), flush=True)
    print("PRODUCTION_CHANGED=NO", flush=True)
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
