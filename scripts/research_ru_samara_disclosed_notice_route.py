"""Research ONLY: Samara's own disclosed GzwSP/Notice?noticeLink route.

The alternative route is permitted ONLY if Samara's LIVE first-party public
grid itself discloses both the fixed route and query key in nearby HTML/JS.
Every notice id comes from the current signed native public JSON listing.
Never use guessed ids, unrelated host templates, private login, redirects,
new cookies or any user credentials. Two independently verified details
remain mandatory. Disabled in production.
"""
from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import urlsplit

import httpx

from app.sources.http import (
    ConnectorTransportError, FetchPolicy, bounded_fetch, source_client,
)
from app.sources.ru_dagestan_public_list import public_settings, public_token
from scripts.research_ru_samara_browser_originals import choose_originals
from scripts.research_ru_samara_browser_grid import GRID, HOST, JSON_PATH, MAX_BYTES
from scripts.research_ru_samara_native_details import verify_original_detail

JSON_URL = "https://" + HOST + JSON_PATH
DETAIL_PREFIX = "https://" + HOST + "/smallpurchases/GzwSP/Notice?noticeLink="


def disclosed_notice_contract(html: bytes) -> bool:
    if type(html) is not bytes or not 0 < len(html) <= MAX_BYTES:
        raise ValueError("Invalid source-origin registry HTML")
    # Same-origin public HTML/inline script; NEVER trust a foreign site route.
    cleaned = re.sub(
        rb"<script[^>]*\bsrc=[^>]*>.*?</script>",
        b"", html, flags=re.IGNORECASE | re.DOTALL,
    )
    return bool(re.search(
        rb"/smallpurchases/GzwSP/Notice.{0,1400}\bnoticeLink\b"
        rb"|\bnoticeLink\b.{0,1400}/smallpurchases/GzwSP/Notice",
        cleaned, flags=re.DOTALL,
    ))


def detail_url_from_original_native_link(url: str) -> str:
    if type(url) is not str:
        raise ValueError("Native URL not supplied")
    p = urlsplit(url)
    if (p.scheme != "https" or p.netloc != HOST or p.query or p.fragment
            or not re.fullmatch(r"/smallpurchases/GzwSP/[0-9]{6,12}", p.path)):
        raise ValueError("Not a current canonical first-party native listing link")
    identity = p.path.rsplit("/", 1)[-1]
    return DETAIL_PREFIX + identity


async def proof() -> int:
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 4, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=25, trust_env=False, follow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            public = await client.get(GRID, headers={"Accept": "text/html"})
            public.raise_for_status()
            if "html" not in public.headers.get("content-type", "").lower():
                raise ValueError("Not the actual first-party public grid")
            announced = disclosed_notice_contract(public.content)
            print("RU_SAMARA_PUBLIC_NOTICE_QUERY_DECLARED=" + str(announced))
            if not announced:
                raise ValueError("Official public page did not disclose that detail query")
            token = public_token(public.content)
            response = await client.post(JSON_URL, json={"settings": public_settings()}, headers={
                "Accept": "application/json, text/javascript",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": GRID,
                "RequestVerificationToken": token,
            })
            response.raise_for_status()
            if "json" not in response.headers.get("content-type", "").lower():
                raise ValueError("No genuine native JSON records")
            current = choose_originals(response.content)
            confirmed = 0
            for number, title, buyer, raw_url in current:
                detail_url = detail_url_from_original_native_link(raw_url)
                detail = await client.get(detail_url, headers={"Accept": "text/html"})
                print("RU_SAMARA_DECLARED_ORIGINAL_HTTP=" + str(detail.status_code))
                detail.raise_for_status()
                if "html" not in detail.headers.get("content-type", "").lower():
                    raise ValueError("Published detail not HTML")
                verify_original_detail(
                    detail.content, number=number, title=title, buyer=buyer,
                )
                confirmed += 1
            return confirmed


def main() -> int:
    try:
        found = asyncio.run(proof())
    except (ValueError, TypeError, ConnectorTransportError, httpx.HTTPError,
            OSError, TimeoutError, json.JSONDecodeError) as error:
        print("RU_SAMARA_DECLARED_DETAILS=BLOCKED_" + type(error).__name__)
        if isinstance(error, ConnectorTransportError):
            print("RU_SAMARA_DECLARED_RETRYABLE=" + str(error.retryable))
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_SAMARA_DECLARED_DETAILS_VERIFIED=" + str(found))
    print("PRODUCTION_CHANGED=NO")
    return 0 if found == 2 else 2


if __name__ == "__main__":
    raise SystemExit(main())
