"""Observe an anonymously published Samara small-purchase grid with real Chromium.

RESEARCH ONLY, not source integration. Never use accounts, auth routes, proxies,
redirect bypass, TLS overrides, arbitrary URL input or fixture-as-live evidence.
Only first-party metadata/counts are logged, never tokens, titles or raw bodies.
"""
from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import parse_qsl, urljoin, urlsplit

HOST = "webtorgi.samregion.ru"
GRID = f"https://{HOST}/smallpurchases/GzwSP/NoticesGrid"
JSON_PATH = "/smallpurchases/GzwSP/NoticesJson"
MAX_REQUESTS = 100
MAX_POSTS = 3
MAX_BYTES = 1_800_000
NATIVE_ID = re.compile(r"ИМЗ-20[0-9]{2}-[0-9-]{5,20}", re.I)


def allowed(url: str, method: str) -> bool:
    """Pin browser dispatch to this single public host and public read route."""
    try:
        p = urlsplit(url)
        if (p.scheme != "https" or p.hostname != HOST or p.username or p.password
                or p.port not in (None, 443) or p.fragment):
            return False
        if p.path == JSON_PATH:
            return method == "POST"
        if any(term in p.path.lower() for term in
               ("/login", "/logout", "/register", "/admin", "/account",
                "/authorization", "/signin", "/auth/")):
            return False
        return method == "GET"
    except ValueError:
        return False


def safe_original_reference(raw: str | None) -> bool:
    if (type(raw) is not str or not 1 <= len(raw) <= 800
            or "\\" in raw or any(ord(c) < 33 or c.isspace() for c in raw)):
        return False
    try:
        p = urlsplit(urljoin(GRID, raw))
        return (p.scheme == "https" and p.hostname == HOST and p.port in (None, 443)
                and not (p.username or p.password or p.fragment or p.query)
                # A general same-host public page is NOT a notice detail.
                # Only native published numeric original links qualify.
                and re.fullmatch(r"/smallpurchases/GzwSP/[0-9]{6,12}", p.path)
                is not None)
    except ValueError:
        return False


def public_post_names(data: str | None, mime: str) -> tuple[str, ...]:
    """Expose form field NAMES only, not values/cookies/CSRF token."""
    if type(data) is not str or len(data) > 100_000:
        return ()
    if "json" in mime.lower():
        try:
            obj = json.loads(data)
        except ValueError:
            return ()
        if type(obj) is not dict:
            return ()
        keys = obj.keys()
    else:
        keys = (name for name, _ in parse_qsl(data, keep_blank_values=True))
    return tuple(sorted({name for name in keys if type(name) is str
                         and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,45}", name)}))[:25]


def public_row_shape(body: bytes) -> dict[str, int]:
    """Validate genuine native list identity/subject/buyer, not private detail."""
    if type(body) is not bytes or not 0 < len(body) <= MAX_BYTES:
        raise ValueError("Invalid original grid response size")
    doc = json.loads(body)
    if type(doc) is not dict or type(doc.get("items")) is not list:
        raise ValueError("Native JSON items missing")
    rows = doc["items"]
    if not 2 <= len(rows) <= 30:
        raise ValueError("Original public grid returned insufficient or excessive rows")
    unique = set()
    linked = 0
    for row in rows:
        if type(row) is not dict:
            raise ValueError("Native row is not an object")
        number, title, buyer = (row.get(k) for k in ("number", "name", "uchr_sname"))
        if (type(number) is not str or not NATIVE_ID.fullmatch(number.strip())
                or type(title) is not str or len(title.strip()) < 4
                or type(buyer) is not str or len(buyer.strip()) < 3
                or number in unique):
            raise ValueError("Native first-party identity/title/buyer unverified")
        unique.add(number)
        if safe_original_reference(row.get("link")):
            linked += 1
    return {"rows": len(rows), "native_ids": len(unique), "same_host_detail_refs": linked}


async def observe() -> int:
    # Optional only for dedicated live research workflow; never required by pytest.
    from playwright.async_api import async_playwright

    request_count = 0
    post_count = 0
    live_evidence = []
    pending = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-proxy-server"])
        context = await browser.new_context(
            ignore_https_errors=False, accept_downloads=False,
            service_workers="block", java_script_enabled=True,
        )
        page = await context.new_page()

        async def route_handler(route):
            nonlocal request_count, post_count
            request = route.request
            if urlsplit(request.url).path.lower().endswith(
                    (".png", ".jpg", ".jpeg", ".gif", ".woff", ".woff2", ".svg", ".ico")):
                await route.abort()
                return
            request_count += 1
            if request_count > MAX_REQUESTS or not allowed(request.url, request.method):
                await route.abort()
                return
            if urlsplit(request.url).path == JSON_PATH:
                post_count += 1
                if post_count > MAX_POSTS:
                    await route.abort()
                    return
                names = public_post_names(request.post_data, request.headers.get("content-type", ""))
                print("RU_SAMARA_NATIVE_METHOD=POST")
                print("RU_SAMARA_NATIVE_PUBLIC_FIELD_NAMES=" + ",".join(names))
            await route.continue_()

        async def inspect(response):
            if urlsplit(response.url).path != JSON_PATH:
                return
            print("RU_SAMARA_BROWSER_NATIVE_HTTP=" + str(response.status))
            if response.status != 200 or "json" not in response.headers.get("content-type", "").lower():
                return
            try:
                shape = public_row_shape(await response.body())
            except (ValueError, TypeError, UnicodeDecodeError):
                print("RU_SAMARA_BROWSER_LIST=NOT_PROVEN")
                return
            for key, val in shape.items():
                print("RU_SAMARA_BROWSER_" + key.upper() + "=" + str(val))
            if shape["native_ids"] >= 2 and shape["same_host_detail_refs"] >= 2:
                live_evidence.append(shape)

        def on_response(response):
            if urlsplit(response.url).path == JSON_PATH:
                pending.append(asyncio.create_task(inspect(response)))

        await page.route("**/*", route_handler)
        page.on("response", on_response)
        try:
            await page.goto(GRID, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(8500)
            if pending:
                await asyncio.gather(*pending)
        finally:
            await context.close()
            await browser.close()

    print("RU_SAMARA_BROWSER_TOTAL_REQUESTS=" + str(request_count))
    print("RU_SAMARA_BROWSER_NATIVE_POSTS=" + str(post_count))
    print("ORIGINAL_DETAIL_GET_PROVED=NO")
    print("WORKER_SQL_TENANT_PROVED=NO")
    print("PRODUCTION_CHANGED=NO")
    return 0 if live_evidence else 2


def main() -> int:
    try:
        code = asyncio.run(observe())
    except (ValueError, RuntimeError, OSError, TimeoutError) as error:
        print("RU_SAMARA_PUBLIC_BROWSER=BLOCKED_" + type(error).__name__)
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_SAMARA_PUBLIC_BROWSER=" + ("LIST_RESEARCH_ONLY" if code == 0 else "BLOCKED_NO_ORIGINAL_ROWS"))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
