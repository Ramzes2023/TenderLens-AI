"""Read-only genuine Samara anonymous browser list → original detail acceptance.

Research-only: one current first-party JSON listing, then EXACTLY TWO
first-party numeric detail links physically returned by that current listing.
No login, credentials, proxies, TLS relaxation, forced redirects, hidden
endpoints, guessed URL, mutation, subscriber sends or production activation.
"""
from __future__ import annotations

import asyncio
import json
from urllib.parse import urljoin, urlsplit

from scripts.research_ru_samara_browser_grid import (
    GRID, HOST, JSON_PATH, MAX_BYTES, NATIVE_ID,
    allowed, public_row_shape, safe_original_reference,
)
from scripts.research_ru_samara_native_details import verify_original_detail


def choose_originals(body: bytes) -> list[tuple[str, str, str, str]]:
    """Bounded native first-party JSON; never substitute a fixture for live proof."""
    shape = public_row_shape(body)
    if shape["same_host_detail_refs"] < 2:
        raise ValueError("Two canonical original references not present")
    rows = json.loads(body)["items"]
    selected, seen_numbers, seen_urls = [], set(), set()
    for row in rows:
        number, title, buyer, raw = (
            row.get("number"), row.get("name"), row.get("uchr_sname"), row.get("link")
        )
        if (not safe_original_reference(raw) or type(number) is not str
                or NATIVE_ID.fullmatch(number) is None or type(title) is not str
                or type(buyer) is not str or not title.strip() or not buyer.strip()):
            continue
        url = urljoin(GRID, raw)
        if number in seen_numbers or url in seen_urls:
            continue
        selected.append((number, title, buyer, url))
        seen_numbers.add(number)
        seen_urls.add(url)
        if len(selected) == 2:
            return selected
    raise ValueError("Two independent list-origin exact URLs were not disclosed")


async def observe(*, disclosed_notice_route: bool = False) -> int:
    # Dedicated CI alone installs optional browser dependency.
    from playwright.async_api import async_playwright

    entries = []
    native_received = asyncio.Event()
    tasks = []
    count = 0
    post_count = 0
    stage = "GRID_NAVIGATION"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True, args=["--no-proxy-server"],
        )
        context = await browser.new_context(
            java_script_enabled=True,
            ignore_https_errors=False,
            accept_downloads=False,
            service_workers="block",
        )
        page = await context.new_page()

        async def gate(route):
            nonlocal count, post_count
            req = route.request
            path = urlsplit(req.url).path
            if path.lower().endswith(
                    (".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2", ".ico")):
                await route.abort()
                return
            count += 1
            if count > 130 or not allowed(req.url, req.method):
                await route.abort()
                return
            if path == JSON_PATH:
                post_count += 1
                if post_count > 2:
                    await route.abort()
                    return
            await route.continue_()

        async def check_native(response):
            if urlsplit(response.url).path != JSON_PATH:
                return
            if (response.status != 200
                    or "json" not in response.headers.get("content-type", "").lower()):
                return
            try:
                body = await response.body()
                if len(body) > MAX_BYTES:
                    return
                rows = choose_originals(body)
            except (ValueError, TypeError, UnicodeDecodeError):
                return
            if not entries:
                entries.extend(rows)
                native_received.set()

        def on_response(response):
            if urlsplit(response.url).path == JSON_PATH:
                tasks.append(asyncio.create_task(check_native(response)))

        await context.route("**/*", gate)
        page.on("response", on_response)
        try:
            try:
                await page.goto(GRID, wait_until="domcontentloaded", timeout=30000)
                if disclosed_notice_route:
                    # Only the current Samara first-party grid may authorize
                    # this alternative route. Never infer it from another region.
                    from scripts.research_ru_samara_disclosed_notice_route import (
                        disclosed_notice_contract,
                    )
                    if not disclosed_notice_contract(
                        (await page.content()).encode("utf-8"),
                    ):
                        raise ValueError("First-party Samara detail route not disclosed")
                    print("RU_SAMARA_BROWSER_DECLARED_NOTICE_ROUTE=YES")
                await asyncio.wait_for(native_received.wait(), timeout=15)
                if len(entries) != 2 or post_count < 1:
                    raise ValueError("Current official native JSON not available")
                print("RU_SAMARA_BROWSER_LIVE_LIST_ROWS_VERIFIED=2")
                confirmed = 0
                for number, title, buyer, url in entries:
                    if disclosed_notice_route:
                        from scripts.research_ru_samara_disclosed_notice_route import (
                            detail_url_from_original_native_link,
                        )
                        url = detail_url_from_original_native_link(url)
                    stage = "ORIGINAL_DETAIL_NAVIGATION"
                    # Only links disclosed by the fresh current official JSON.
                    # Blocked redirects/login never count as independent details.
                    response = await page.goto(
                        url, wait_until="domcontentloaded", timeout=18000,
                    )
                    print("RU_SAMARA_ORIGINAL_BROWSER_HTTP_STATUS=" + (
                        str(response.status) if response is not None else "NONE"
                    ))
                    print("RU_SAMARA_ORIGINAL_FINAL_URL_MATCH=" + str(page.url == url))
                    if response is None or response.status != 200 or page.url != url:
                        raise ValueError("Original detail was blocked or redirected")
                    stage = "ORIGINAL_DETAIL_PARSE"
                    html = (await page.content()).encode("utf-8")
                    if not 0 < len(html) <= MAX_BYTES:
                        raise ValueError("Invalid original HTML size")
                    verify_original_detail(
                        html, number=number, title=title, buyer=buyer,
                    )
                    confirmed += 1
                print("RU_SAMARA_BROWSER_INDEPENDENT_ORIGINALS=" + str(confirmed))
                print("PRODUCTION_CHANGED=NO")
                return 0 if confirmed == 2 else 2
            except (ValueError, TimeoutError) as error:
                print("RU_SAMARA_BROWSER_ORIGINAL_STAGE=" + stage)
                print("RU_SAMARA_BROWSER_ORIGINAL_ERROR=" + type(error).__name__)
                print("PRODUCTION_CHANGED=NO")
                return 2
        finally:
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await context.close()
            await browser.close()


def main() -> int:
    try:
        result = asyncio.run(observe())
    except Exception as error:
        # No response body, title, number, cookies, tokens or raw URL in logs.
        print("RU_SAMARA_BROWSER_ORIGINAL_RUNTIME=" + type(error).__name__)
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_SAMARA_BROWSER_ORIGINAL_RESULT=" + (
        "TWO_INDEPENDENT_ORIGINALS" if result == 0 else "BLOCKED"
    ))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
