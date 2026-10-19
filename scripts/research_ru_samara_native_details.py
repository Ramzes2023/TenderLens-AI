"""First-party Samara public native list -> two independent original details.

RESEARCH ONLY. Never enable a source or mark list-only evidence as full details.
One GET anonymous grid, one announced native JSON POST, two list-originated
same-host detail GETs. No guessed IDs, redirects, login, proxies, TLS overrides,
production writes or credentials.
"""
from __future__ import annotations

import asyncio
import json
from urllib.parse import urljoin

import httpx

from app.sources.http import ConnectorTransportError, FetchPolicy, bounded_fetch, source_client
from app.sources.ru_dagestan_public_list import public_settings, public_token
from scripts.research_ru_samara_browser_grid import (
    HOST, GRID, JSON_PATH, MAX_BYTES, public_row_shape,
    safe_original_reference, NATIVE_ID,
)
from scripts.research_ru_samara_small_public import document

URL = "https://" + HOST + JSON_PATH


def verify_original_detail(raw: bytes, *, number: str, title: str, buyer: str) -> bool:
    if not isinstance(number, str) or not NATIVE_ID.fullmatch(number):
        raise ValueError("Missing native original purchase number")
    if not all(type(s) is str and 3 <= len(s) <= 1000 for s in (title, buyer)):
        raise ValueError("Missing independently verifiable notice fields")
    page = document(raw)
    visible = " ".join(" ".join(page.visible).split()).casefold()
    if (number.casefold() not in visible or title.casefold() not in visible
            or buyer.casefold() not in visible):
        raise ValueError("Native original detail does not confirm identity, title and buyer")
    if any(term in visible for term in (
            "необходимо авторизоваться", "войдите в систему для просмотра",
            "необходима авторизация")):
        raise ValueError("Original detail requires login")
    return True


async def proof(*, stage: dict | None = None) -> int:
    stage = stage if stage is not None else {}
    stage["step"] = "GRID_GET"
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 4, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=25, trust_env=False, follow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            page = await client.get(GRID, headers={"Accept": "text/html"})
            page.raise_for_status()
            if "html" not in page.headers.get("content-type", "").lower():
                raise ValueError("No native public grid HTML")
            token = public_token(page.content)
            stage["step"] = "GRID_NATIVE_JSON_POST"
            native = await client.post(
                URL,
                json={"settings": public_settings()},
                headers={
                    "Accept": "application/json, text/javascript",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": GRID,
                    "RequestVerificationToken": token,
                },
            )
            native.raise_for_status()
            if "json" not in native.headers.get("content-type", "").lower():
                raise ValueError("No native JSON media type")
            shape = public_row_shape(native.content)
            if shape["same_host_detail_refs"] < 2:
                raise ValueError("No two first-party original links")
            obj = json.loads(native.content)
            seen = set()
            confirmed = 0
            for row in obj["items"]:
                raw = row.get("link")
                if not safe_original_reference(raw):
                    continue
                number = row.get("number")
                title = row.get("name")
                buyer = row.get("uchr_sname")
                if number in seen:
                    raise ValueError("Duplicate native purchase numbers")
                seen.add(number)
                # URLs originate strictly from the live original public list.
                detail_url = urljoin(GRID, raw)
                stage["step"] = "ORIGINAL_DETAIL_GET"
                detail = await client.get(detail_url, headers={"Accept": "text/html"})
                print("RU_SAMARA_ORIGINAL_HTTP_STATUS=" + str(detail.status_code))
                detail.raise_for_status()
                if "html" not in detail.headers.get("content-type", "").lower():
                    raise ValueError("No original HTML detail media type")
                stage["step"] = "ORIGINAL_DETAIL_PARSE"
                verify_original_detail(detail.content, number=number, title=title, buyer=buyer)
                confirmed += 1
                if confirmed == 2:
                    return confirmed
            raise ValueError("No two independently verified Samara original details")


def main() -> int:
    stage = {}
    try:
        count = asyncio.run(proof(stage=stage))
    except (ValueError, TypeError, ConnectorTransportError, httpx.HTTPError,
            OSError, TimeoutError, json.JSONDecodeError) as error:
        print("RU_SAMARA_NATIVE_ORIGINAL_DETAILS=BLOCKED_" + type(error).__name__)
        print("RU_SAMARA_FAILURE_STAGE=" + stage.get("step", "START"))
        if isinstance(error, ConnectorTransportError):
            print("RU_SAMARA_TRANSPORT_RETRYABLE=" + str(error.retryable))
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_SAMARA_NATIVE_INDEPENDENT_ORIGINALS=" + str(count))
    print("RU_SAMARA_NATIVE_ORIGINAL_DETAILS=PASS_RESEARCH_ONLY")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
