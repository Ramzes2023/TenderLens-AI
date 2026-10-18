"""Samara public small-purchase FIRST-PARTY list→independent details research.

No third-party aggregator, indexed historical tenders, guessable detail URL,
session/cookie, production writes, redirect, TLS downgrade, or fixture-as-live.
Only URLs physically disclosed by a fresh official HTML listing are followed.
"""
from __future__ import annotations

import asyncio
import json
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit

import httpx
from app.sources.http import (
    FetchPolicy, bounded_fetch, source_client, ConnectorTransportError,
)

HOST = "webtorgi.samregion.ru"
# Official regional small-purchase public registry, not the portal root.
# Documented public entry point; live listing/detail proof remains mandatory.
INDEX = "https://webtorgi.samregion.ru/smallpurchases/Menu/Page/1"
GRID_URL = "https://webtorgi.samregion.ru/smallpurchases/GzwSP/NoticesGrid"
MAX_BYTES = 1_800_000
REQUIRED = 2
NATIVE_ID = re.compile(r"ИМЗ-20[0-9]{2}-[0-9-]{5,20}", re.I)


class PublicRows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = self.cell = self.anchor = None
        self.links = []
        self.scripts = []
        self.visible = []
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            src = dict(attrs).get("src")
            if type(src) is str:
                self.scripts.append(src)
        if tag in {"script", "style", "noscript", "svg", "iframe", "template"}:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag == "tr":
            self.row = {"cells": [], "links": []}
        if tag in {"td", "th"} and self.row is not None:
            self.cell = []
        if tag == "a":
            self.anchor = [dict(attrs).get("href"), []]

    def handle_data(self, data):
        if self.hidden:
            return
        self.visible.append(data)
        if self.cell is not None:
            self.cell.append(data)
        if self.anchor is not None:
            self.anchor[1].append(data)

    def handle_endtag(self, tag):
        if self.hidden:
            if self.hidden[-1] == tag:
                self.hidden.pop()
            return
        if tag == "a" and self.anchor is not None:
            item = (self.anchor[0], " ".join(" ".join(self.anchor[1]).split()))
            self.links.append(item)
            if self.row is not None:
                self.row["links"].append(item)
            self.anchor = None
        if tag in {"td", "th"} and self.cell is not None and self.row is not None:
            self.row["cells"].append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def document(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES or b"\x00" in raw:
        raise ValueError("Untrusted Samara public HTML")
    parsed = PublicRows()
    parsed.feed(raw.decode("utf-8-sig", "replace"))
    parsed.close()
    return parsed


def strict_original_link(href):
    if (type(href) is not str or not 0 < len(href) <= 500 or "\\" in href
            or any(c.isspace() or ord(c) < 32 for c in href)):
        return None
    try:
        link = urlsplit(urljoin(INDEX, href))
    except ValueError:
        return None
    # Do not allow the homepage/login route, fragments, operator redirects,
    # arbitrary query strings, credentials, ports or cross-origin linking.
    if (link.scheme != "https" or link.netloc != HOST or link.port is not None
            or link.username or link.password or link.fragment or len(link.path) < 6
            or link.path in {"/login", "/account", "/"}):
        return None
    if not re.fullmatch(r"/[A-Za-z0-9_./%-]{5,250}", link.path):
        return None
    if len(link.query) > 150 or not re.fullmatch(r"[A-Za-z0-9_=&%-]*", link.query):
        return None
    return link.geturl()


def disclosed_grid_paths(raw):
    """Diagnostic-only same-page GzwSP route hints; NO inferred API requests.

    These strings may occur in public inline JavaScript and do not by themselves
    establish an open endpoint, original notice, or safe GET/POST contract.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES or b"\x00" in raw:
        raise ValueError("Invalid original research HTML")
    routes = set()
    for hit in re.findall(
        rb"/smallpurchases/GzwSP/[A-Za-z][A-Za-z0-9_]{2,55}",
        raw, re.IGNORECASE,
    ):
        try:
            route = hit.decode("ascii")
        except UnicodeDecodeError:
            continue
        # Print ONLY a fixed local namespace and a short, identifier-free
        # action name; no query, credentials, tokens, body or external origins.
        if re.fullmatch(r"/smallpurchases/GzwSP/[A-Za-z][A-Za-z0-9_]{2,55}", route):
            routes.add(route)
    return tuple(sorted(routes))[:12]


def disclosed_json_grid_method(raw):
    """Read a method hint *only* from original public inline grid markup."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("Unsafe public method diagnostic")
    target = b"/smallpurchases/GzwSP/NoticesJson"
    where = raw.find(target)
    if where < 0:
        return "NOT_DISCLOSED"
    # A nearby inline jqGrid configuration is evidence of intended HTTP
    # method, not evidence of a working anonymous public endpoint.
    context = raw[max(where - 600, 0):min(where + 600, len(raw))]
    seen = set(re.findall(
        rb"""\b(?:mtype|method)\s*:\s*["'](GET|POST)["']""",
        context, re.IGNORECASE,
    ))
    if len(seen) != 1:
        return "UNKNOWN"
    return next(iter(seen)).decode("ascii").upper()


def describe_public_json_shape(raw):
    """Read-only diagnostics: structure/ID counts are NOT real tender proof."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES or b"\x00" in raw:
        raise ValueError("Invalid public JSON size")
    value = json.loads(raw)
    if isinstance(value, dict):
        keys = sorted(key for key in value if
                      type(key) is str and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,35}", key))
        rows = value.get("rows")
        root_kind = "object"
    elif isinstance(value, list):
        keys = []
        rows = value
        root_kind = "array"
    else:
        raise ValueError("Invalid public grid JSON root")
    return {
        "root": root_kind,
        "keys": tuple(keys[:12]),
        "rows": len(rows) if isinstance(rows, list) else 0,
        "native_ids_visible": len(set(NATIVE_ID.findall(raw.decode("utf-8-sig", "replace")))),
    }


async def probe_disclosed_public_json(client, html):
    """At most two anonymous same-host diagnostic reads of a disclosed JSON path.

    GET and one empty-body POST are informational-only requests: no credentials,
    cookies, mutations, search profile, arbitrary method or operator URL. Even
    a valid JSON structure NEVER counts as independently verified tenders.
    """
    path = "/smallpurchases/GzwSP/NoticesJson"
    if path not in disclosed_grid_paths(html):
        print("RU_SAMARA_JSON_DIAG=NOT_DISCLOSED")
        return
    hint = disclosed_json_grid_method(html)
    print("RU_SAMARA_JSON_GRID_METHOD_HINT=" + hint)
    url = "https://" + HOST + path
    # A page explicitly declaring GET cannot authorize a speculative POST.
    methods = ("GET",) if hint == "GET" else ("GET", "POST")
    for method in methods:
        try:
            client.cookies.clear()
            kwargs = {"headers": {"Accept": "application/json"}}
            if method == "POST":
                kwargs["content"] = b""  # No forms, CSRF fields or guessed paging.
            response = await client.request(method, url, **kwargs)
            client.cookies.clear()
            print("RU_SAMARA_JSON_" + method + "_HTTP_STATUS=" + str(response.status_code))
            mime = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if mime not in {"application/json", "text/json"}:
                print("RU_SAMARA_JSON_" + method + "=NOT_JSON")
                continue
            diagnostic = describe_public_json_shape(response.content)
            print("RU_SAMARA_JSON_" + method + "_ROOT=" + diagnostic["root"])
            print("RU_SAMARA_JSON_" + method + "_ROWS=" + str(diagnostic["rows"]))
            print("RU_SAMARA_JSON_" + method + "_NATIVE_IDS=" + str(diagnostic["native_ids_visible"]))
            print("RU_SAMARA_JSON_" + method + "_KEYS=" + ",".join(diagnostic["keys"]))
            print("RU_SAMARA_JSON_DIAG=STRUCTURE_ONLY_NOT_ORIGINALS")
            return
        except (ConnectorTransportError, httpx.HTTPError, ValueError, OSError, TimeoutError) as exc:
            print("RU_SAMARA_JSON_" + method + "=BLOCKED_" + type(exc).__name__)
            if isinstance(exc, ConnectorTransportError):
                print("RU_SAMARA_JSON_" + method + "_RETRYABLE=" + str(exc.retryable))
                # A transient upstream outage must not trigger a second request.
                if exc.retryable:
                    return
        finally:
            client.cookies.clear()
    print("RU_SAMARA_JSON_DIAG=BLOCKED_NO_VERIFIABLE_DATA")


def listing(raw):
    doc = document(raw)
    print("RU_SAMARA_LIST_ROWS=" + str(len(doc.rows)))
    print("RU_SAMARA_LIST_LINKS=" + str(len(doc.links)))
    # First-party public script paths only; do not print HTML, form values,
    # external URLs, cookies, query strings, or follow an API guess.
    print("RU_SAMARA_SCRIPT_COUNT=" + str(len(doc.scripts)))
    disclosed = []
    for src in doc.scripts:
        if type(src) is not str or len(src) > 280:
            continue
        try:
            parsed = urlsplit(urljoin(INDEX, src))
        except ValueError:
            continue
        if (parsed.scheme == "https" and parsed.netloc == HOST
                and not parsed.query and not parsed.fragment
                and re.fullmatch(r"/[A-Za-z0-9_./-]{3,160}", parsed.path)):
            disclosed.append(parsed.path)
    for i, script in enumerate(sorted(set(disclosed))[:8], 1):
        print("RU_SAMARA_PUBLIC_JS_" + str(i) + "=" + script)
    print("RU_SAMARA_LIST_NATIVE_ID_ROWS=" + str(sum(
        bool(NATIVE_ID.search(" ".join(row["cells"]))) for row in doc.rows
    )))
    hints = disclosed_grid_paths(raw)
    print("RU_SAMARA_GRID_ROUTE_HINTS=" + str(len(hints)))
    for number, hint in enumerate(hints, 1):
        print("RU_SAMARA_GRID_ROUTE_HINT_" + str(number) + "=" + hint)
    verified, seen = [], set()
    for row in doc.rows:
        ids = set(NATIVE_ID.findall(" ".join(row["cells"])))
        if len(ids) != 1:
            continue
        notice_id = next(iter(ids))
        for href, title in row["links"]:
            original_url = strict_original_link(href)
            if (not original_url or notice_id in seen
                    or not 8 <= len(title) <= 550
                    or not re.search(r"[А-Яа-яЁё]", title)):
                continue
            seen.add(notice_id)
            verified.append((notice_id, title, original_url))
            break
    if len(verified) < REQUIRED:
        raise ValueError("No two linked independent original Samara municipal notices")
    return verified[:REQUIRED]


def original_detail(raw, notice_id, title, url):
    if (strict_original_link(url) != url or not NATIVE_ID.fullmatch(notice_id)):
        raise ValueError("Samara original detail URL/number not canonical")
    doc = document(raw)
    text = " ".join(" ".join(doc.visible).split())
    if notice_id not in text:
        raise ValueError("Independent Samara native notice ID missing")
    if title.casefold() not in text.casefold():
        raise ValueError("Independent Samara notice title missing")
    if not re.search(r"заказчик", text, re.I):
        raise ValueError("Original Samara buyer field missing")
    if not re.search(r"(?:стоимост|цен[аы]|НМЦК)", text, re.I):
        raise ValueError("Original Samara price field missing")
    return notice_id, title, url


async def real():
    with bounded_fetch(FetchPolicy(frozenset({HOST}), REQUIRED + 4,
                                   max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=25, trust_env=False, follow_redirects=False,
            headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
        ) as client:
            client.cookies.clear()
            response = await client.get(INDEX)
            client.cookies.clear()
            response.raise_for_status()
            if "html" not in response.headers.get("content-type", "").lower():
                raise ValueError("Original Samara registry not HTML")
            print("RU_SAMARA_HTTP_BYTES=" + str(len(response.content)))
            # Safe bounded status classification, never log body, cookies or
            # login tokens; HTTP 200 can still mean no public procurement.
            decoded = response.content.decode("utf-8-sig", "replace").casefold()
            for label, needles in (
                ("AUTH_GATE", ("авторизац", "войти в систему", "login", "sign in")),
                ("JS_REQUIRED", ("javascript", "enable javascript", "включите javascript")),
                ("BOT_GATE", ("captcha", "проверка браузера", "ддос", "ddos")),
            ):
                print("RU_SAMARA_" + label + "="
                      + str(any(needle in decoded for needle in needles)))
            try:
                rows = listing(response.content)
            except ValueError:
                # This independently documented native public grid is a second
                # fixed first-party GET, never a guessed URL or an auth bypass.
                # The adapter still fails closed if neither returned page
                # lists two independently linked original notices.
                client.cookies.clear()
                grid = await client.get(GRID_URL)
                client.cookies.clear()
                grid.raise_for_status()
                if "html" not in grid.headers.get("content-type", "").lower():
                    raise ValueError("Samara public native grid is not HTML")
                print("RU_SAMARA_GRID_HTTP_BYTES=" + str(len(grid.content)))
                print("RU_SAMARA_RESEARCH_ROUTE=OFFICIAL_GRID")
                try:
                    rows = listing(grid.content)
                except ValueError:
                    # Do not infer ingestion from a guessed endpoint or JSON
                    # field names. This one read-only disclosed-URL diagnostic
                    # cannot make the required real notice gate green.
                    await probe_disclosed_public_json(client, grid.content)
                    raise
            result = []
            for number, title, url in rows:
                client.cookies.clear()
                page = await client.get(url)
                client.cookies.clear()
                page.raise_for_status()
                if "html" not in page.headers.get("content-type", "").lower():
                    raise ValueError("Original Samara detail not HTML")
                result.append(original_detail(page.content, number, title, url))
            if len({n for n, _, _ in result}) != REQUIRED:
                raise ValueError("Samara original IDs not independent")
            return result


def main():
    try:
        verified = asyncio.run(real())
        print("RU_SAMARA_VERIFIED_ORIGINALS=" + str(len(verified)))
        print("RU_SAMARA_SMALL=PASS_RESEARCH_ONLY")
        code = 0 if len(verified) == REQUIRED else 2
    except (ValueError, ConnectorTransportError, httpx.HTTPError,
            OSError, TimeoutError) as exc:
        print("RU_SAMARA_SMALL=BLOCKED_" + type(exc).__name__)
        if isinstance(exc, ConnectorTransportError):
            print("RU_SAMARA_RETRYABLE=" + str(exc.retryable))
        code = 2
    print("PRODUCTION_CHANGED=NO")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
