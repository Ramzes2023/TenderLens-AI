"""Observe only anonymous first-party GET -> native list POST in a real browser.

Research-only. Not a scraper, no accounts/login, no CAPTCHA or TLS bypass,
no persisted cookies or requests, no clicking links, and no production writes.
Print only outgoing field NAMES and JSON SHAPE (never cookies/tokens/values).
"""
from __future__ import annotations

import asyncio
import json
from urllib.parse import parse_qsl, urljoin, urlsplit

from playwright.async_api import async_playwright

HOST = "goszakaz.e-dag.ru"
LISTING = "https://" + HOST + "/smallpurchases/GzwSP/NoticesGrid"
NATIVE = "/smallpurchases/GzwSP/NoticesJson"
MAX_ORIGIN_REQUESTS = 160
MAX_NATIVE_REQUESTS = 3
MAX_ROWS_LOGGED = 2


def allowed(url: str, method: str) -> bool:
    try:
        p = urlsplit(url)
        if (p.scheme != "https" or p.hostname != HOST
                or p.username or p.password or p.port not in (None, 443)):
            return False
        if p.path == NATIVE:
            return method.upper() == "POST"
        path = p.path.lower()
        if any(bad in path for bad in ("/login", "/logout", "/account",
                                        "/auth", "/admin", "/register")):
            return False
        return method.upper() == "GET"
    except ValueError:
        return False


def only_public_keynames(data: str | None, content_type: str) -> tuple[str, ...]:
    if not data or len(data) > 180_000:
        return ()
    if "application/json" in content_type:
        try:
            value = json.loads(data)
        except ValueError:
            return ()
        if isinstance(value, dict):
            return tuple(sorted(k for k in value if isinstance(k, str) and
                                k.isascii() and k.replace("_", "").isalnum())[:50])
        return ()
    pairs = parse_qsl(data, keep_blank_values=True)
    return tuple(sorted(set(k for k, _ in pairs if
                            k.isascii() and k.replace("_", "").isalnum()))[:50])


def extract_public_native_settings(data: str | None, content_type: str = ""):
    """Safely locate one first-party settings parameter in JSON or form, no logs."""
    if type(data) is not str or not 0 < len(data) <= 180_000:
        return None
    if "json" in content_type.lower():
        try:
            outer = json.loads(data)
        except ValueError:
            return None
        if type(outer) is not dict or set(outer) != {"settings"}:
            return None
        return outer["settings"]
    settings = [v for k, v in parse_qsl(data, keep_blank_values=True)
                if k == "settings"]
    if len(settings) != 1 or not 0 < len(settings[0]) <= 80_000:
        return None
    try:
        return json.loads(settings[0])
    except ValueError:
        return settings[0]


def public_native_settings_shape(data: str | None, content_type: str = ""):
    """Only safe field names/type names of native settings, NEVER values."""
    obj = extract_public_native_settings(data, content_type)
    if type(obj) is not dict:
        return (), ()
    keys = tuple(sorted(k for k in obj if type(k) is str and
                        k.isascii() and k.replace("_", "").isalnum())[:60])
    types = tuple(k + ":" + type(obj[k]).__name__ for k in keys)
    return keys, types


def public_native_settings_encoding(data: str | None, content_type: str = ""):
    """Emit only syntax classification and rough size, no values."""
    obj = extract_public_native_settings(data, content_type)
    if obj is None:
        return "MISSING_OR_INVALID", 0
    if type(obj) is dict:
        return "JSON_OBJECT", len(obj)
    if type(obj) is list:
        return "JSON_ARRAY", len(obj)
    if type(obj) is str:
        return "OPAQUE_STRING", len(obj)
    return "OTHER_TYPE", 0


def public_original_link_shape(value):
    """Classify first-party link PATHS only; strip all query and tokens."""
    if type(value) is not str or not 0 < len(value) < 1800:
        return "MISSING_OR_NONSTRING"
    try:
        parsed = urlsplit(urljoin(LISTING, value))
        if (parsed.scheme != "https" or parsed.hostname != HOST or
                parsed.username or parsed.password or
                parsed.port not in (None, 443)):
            return "NON_FIRST_PARTY"
        if not parsed.path.startswith("/smallpurchases/"):
            return "NOT_NATIVE_SMALL_PURCHASES"
        if any(ord(c) < 33 or c.isspace() for c in parsed.path):
            return "UNSAFE_PATH"
        return parsed.path[:180]
    except ValueError:
        return "INVALID_LINK"


async def observe():
    total_requests = 0
    native_requests = 0
    responses = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-proxy-server"])
        context = await browser.new_context(
            accept_downloads=False,
            ignore_https_errors=False,
            service_workers="block",
            java_script_enabled=True,
        )
        page = await context.new_page()

        async def route_request(route):
            nonlocal total_requests, native_requests
            req = route.request
            url = req.url
            suffix = urlsplit(url).path.lower()
            # Static image/font assets are unnecessary for the public grid
            # request: never fetch them and do not spend request budget.
            if suffix.endswith((".png", ".jpg", ".jpeg", ".gif", ".ico",
                                ".woff", ".woff2", ".ttf", ".svg")):
                await route.abort()
                return
            total_requests += 1
            if total_requests > MAX_ORIGIN_REQUESTS or not allowed(url, req.method):
                await route.abort()
                return
            if urlsplit(url).path == NATIVE:
                native_requests += 1
                if native_requests > MAX_NATIVE_REQUESTS:
                    await route.abort()
                    return
                content_type = req.headers.get("content-type", "")
                keys = only_public_keynames(req.post_data, content_type)
                print("RU_DAG_BROWSER_NATIVE_METHOD=" + req.method)
                print("RU_DAG_BROWSER_NATIVE_PARAM_NAMES=" + ",".join(keys))
                if "settings" in keys:
                    _, shape = public_native_settings_shape(req.post_data, content_type)
                    print("RU_DAG_BROWSER_NATIVE_SETTINGS_FIELD_TYPES=" +
                          ",".join(shape))
                    kind, length = public_native_settings_encoding(req.post_data, content_type)
                    print("RU_DAG_BROWSER_NATIVE_SETTINGS_ENCODING=" + kind)
                    print("RU_DAG_BROWSER_NATIVE_SETTINGS_LENGTH=" + str(length))
            await route.continue_()

        async def inspect_response(resp):
            if urlsplit(resp.url).path != NATIVE:
                return
            print("RU_DAG_BROWSER_NATIVE_HTTP=" + str(resp.status))
            if resp.status != 200:
                return
            if "json" not in resp.headers.get("content-type", "").lower():
                print("RU_DAG_BROWSER_NATIVE_MIME=NOT_JSON")
                return
            try:
                body = await resp.body()
                if len(body) > 1_800_000:
                    print("RU_DAG_BROWSER_NATIVE_JSON=OVERSIZED")
                    return
                doc = json.loads(body)
                if type(doc) is not dict:
                    return
                print("RU_DAG_BROWSER_NATIVE_ROOT_KEYS=" +
                      ",".join(sorted(k for k in doc if type(k) is str and
                                      k.isascii() and k.replace("_", "").isalnum())[:30]))
                items = doc.get("items")
                print("RU_DAG_BROWSER_NATIVE_ITEMS_TYPE=" + type(items).__name__)
                if type(items) is list:
                    print("RU_DAG_BROWSER_NATIVE_ITEMS_COUNT=" + str(len(items)))
                    for i, item in enumerate(items[:MAX_ROWS_LOGGED], 1):
                        if type(item) is dict:
                            safe = sorted(k for k in item if type(k) is str and
                                          k.isascii() and k.replace("_", "").isalnum())
                            print("RU_DAG_BROWSER_ITEM_" + str(i) + "_KEYS=" +
                                  ",".join(safe[:35]))
                            for label in ("link", "bid_link", "etp_url"):
                                print("RU_DAG_BROWSER_ITEM_" + str(i) + "_" +
                                      label.upper() + "_PUBLIC_PATH=" +
                                      public_original_link_shape(item.get(label)))
                    if len(items) >= 2:
                        responses.append(len(items))
            except (ValueError, RuntimeError):
                print("RU_DAG_BROWSER_NATIVE_JSON=UNREADABLE")

        page.on("response", lambda r: responses.append(asyncio.create_task(
            inspect_response(r)
        )) if urlsplit(r.url).path == NATIVE else None)
        await page.route("**/*", route_request)
        await page.goto(LISTING, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(9500)
        tasks = [t for t in responses if isinstance(t, asyncio.Task)]
        if tasks:
            await asyncio.gather(*tasks)
        await context.close()
        await browser.close()
    print("RU_DAG_BROWSER_TOTAL_PUBLIC_REQUESTS=" + str(total_requests))
    print("RU_DAG_BROWSER_BUDGET=" + str(MAX_ORIGIN_REQUESTS))
    print("RU_DAG_BROWSER_NATIVE_REQUESTS=" + str(native_requests))
    print("ORIGINAL_DETAILS_VERIFIED=NO")
    print("WORKER_SQL_KEYWORD_TENANT_VERIFIED=NO")
    return 0 if native_requests and any(
        isinstance(x, int) and x >= 2 for x in responses
    ) else 2


def main():
    try:
        outcome = asyncio.run(observe())
        print("RU_DAG_BROWSER_PUBLIC_GRID=" +
              ("LIVE_ROWS_RESEARCH_ONLY" if outcome == 0 else "BLOCKED_NO_TWO_ROWS"))
        return outcome
    except (OSError, ValueError, RuntimeError, TimeoutError) as error:
        print("RU_DAG_BROWSER_PUBLIC_GRID=BLOCKED_" + type(error).__name__)
        return 2
    finally:
        print("PRODUCTION_CHANGED=NO")


if __name__ == "__main__":
    raise SystemExit(main())
