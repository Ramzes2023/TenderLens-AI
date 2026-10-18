"""Samara public small-purchase FIRST-PARTY list→independent details research.

No third-party aggregator, indexed historical tenders, guessable detail URL,
session/cookie, production writes, redirect, TLS downgrade, or fixture-as-live.
Only URLs physically disclosed by a fresh official HTML listing are followed.
"""
from __future__ import annotations

import asyncio
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit

import httpx
from app.sources.http import (
    FetchPolicy, bounded_fetch, source_client, ConnectorTransportError,
)

HOST = "webtorgi.samregion.ru"
# Official regional small-purchase public registry, not the portal root.\n# The government resolution and published operator instructions identify this path.\nINDEX = "https://webtorgi.samregion.ru/smallpurchases/Menu/Page/1"
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
    with bounded_fetch(FetchPolicy(frozenset({HOST}), REQUIRED + 1,
                                   max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=25, trust_env=False, follow_redirects=False,
            headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
        ) as client:
            response = await client.get(INDEX)
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
            rows = listing(response.content)
            result = []
            for number, title, url in rows:
                page = await client.get(url)
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
