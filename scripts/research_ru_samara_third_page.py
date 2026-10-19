"""Read-only, first-party Samara page-2 research; NOT a production source gate.

Earlier accepted evidence proves native pages 0 and 1. This probe examines a
third independently numbered native page before permitting any 30-row adapter.
Do not emit tokens, notice content, URLs, or customer information to logs.
"""
from __future__ import annotations

import asyncio
import json
from collections import Counter
import math
import re

from app.sources.http import FetchPolicy, bounded_fetch, source_client
from app.sources.ru_samara_public_list import (
    GRID, HOST, JSON_URL, MAX_BYTES, PAGE_SIZE,
    parse_public_list, public_settings, public_token,
)


def public_metadata_shape(value, *, kind):
    """Report structural format ONLY; no public notice values in logs."""
    if value is None or type(value) is bool:
        return "absent"
    if type(value) in (int, float):
        return "finite_number" if math.isfinite(value) else "invalid_number"
    if type(value) is not str:
        return "unexpected_type"
    s = value.strip()
    if not s:
        return "absent"
    if kind == "money":
        if re.fullmatch(r"[0-9]+(?:[.,][0-9]{1,2})?", s):
            return "plain_number"
        if re.fullmatch(r"[0-9]{1,3}(?:[ \u00a0\u202f][0-9]{3})+(?:,[0-9]{1,2})?", s):
            return "grouped_space_money"
        return "unknown_money_format"
    if re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}[T ]+[0-9]{2}:[0-9]{2}(?::[0-9]{2})?(?:[+][0-9]{2}:[0-9]{2}|Z)?", s):
        return "iso_date_time"
    if re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", s):
        return "iso_date_only"
    if re.fullmatch(r"[0-9]{2}\.[0-9]{2}\.20[0-9]{2}[ ]+[0-9]{2}:[0-9]{2}(?::[0-9]{2})?", s):
        return "russian_dot_datetime"
    if re.fullmatch(r"[0-9]{2}\.[0-9]{2}\.20[0-9]{2}", s):
        return "russian_dot_date"
    if re.fullmatch(r"/Date\([0-9]+(?:[-+][0-9]+)?\)/", s):
        return "asp_net_json_date"
    return "unknown_date_format"

def verify_three_pages(payloads):
    if type(payloads) is not list or len(payloads) != 3:
        raise ValueError("Exactly three native pages required")
    ids, numbers = set(), set()
    metadata = {
        "pub_date": 0,
        "summa": 0,
        "collecting_endDate": 0,
        "collecting_enddate": 0,
    }
    shapes = {field: Counter() for field in metadata}
    for page, payload in enumerate(payloads):
        # The response page property has not been independently validated.
        # Prove page position using the issued POST and cross-page identities.
        rows = parse_public_list(payload, limit=PAGE_SIZE)
        if len(rows) != PAGE_SIZE or payload["totalRows"] < 3 * PAGE_SIZE:
            raise ValueError("Insufficient genuine rows for third-page proof")
        for record in rows:
            if record.external_id in ids or record.tender_number in numbers:
                raise ValueError("Repeated native identities across pages")
            ids.add(record.external_id)
            numbers.add(record.tender_number)
        for original in payload["items"][:PAGE_SIZE]:
            for field in metadata:
                value = original.get(field)
                if isinstance(value, (str, int, float)) and str(value).strip():
                    metadata[field] += 1
                shapes[field][public_metadata_shape(
                    value, kind="money" if field == "summa" else "date"
                )] += 1
    return {
        "native_pages": 3,
        "native_unique_list_notices": len(ids),
        "distinct_native_numbers": len(numbers),
        "optional_field_presence_counts_only": metadata,
        "optional_field_format_categories_only": {
            key: dict(sorted(counter.items())) for key, counter in shapes.items()
        },
        "independent_detail_pages_verified": False,
        "production_activation": False,
    }


async def probe():
    pages = []
    # Strict request/response caps and hard-pinned official origin: one original
    # anonymous grid GET plus precisely three original public JSON POSTs.
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 4, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=25, trust_env=False, follow_redirects=False,
            headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
        ) as client:
            grid = await client.get(GRID)
            grid.raise_for_status()
            if "html" not in grid.headers.get("content-type", "").lower():
                raise ValueError("Original anonymous grid did not serve HTML")
            token = public_token(grid.content)
            headers = {
                "Accept": "application/json, text/javascript",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": GRID,
                "RequestVerificationToken": token,
            }
            for page in (0, 1, 2):
                settings = public_settings()
                settings["page"] = page
                response = await client.post(
                    JSON_URL, json={"settings": settings}, headers=headers,
                )
                response.raise_for_status()
                if "application/json" not in response.headers.get("content-type", "").lower():
                    raise ValueError("Original JSON response media type mismatch")
                if not 0 < len(response.content) <= MAX_BYTES:
                    raise ValueError("Original JSON response size out of bound")
                pages.append(response.json())
    return verify_three_pages(pages)


def main():
    try:
        evidence = asyncio.run(probe())
    except Exception as exc:
        print("RU_SAMARA_THIRD_PAGE_RESEARCH=BLOCKED_" + type(exc).__name__)
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_SAMARA_THIRD_PAGE_EVIDENCE=" + json.dumps(evidence, sort_keys=True))
    print("RU_SAMARA_THIRD_PAGE_RESEARCH=PASS_ORIGINAL_LIST_ONLY")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
