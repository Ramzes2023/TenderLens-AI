"""Official Dagestan small purchases: strict current list -> original detail proof.

Read-only research. Never count a portal HTTP 200, cumulative totals, historic
search hits, anonymous API guesses or staged fixtures as verified tenders.
"""
from __future__ import annotations

import asyncio
from html.parser import HTMLParser
import re
from urllib.parse import parse_qsl, urljoin, urlsplit

import httpx
from app.sources.http import (
    FetchPolicy, bounded_fetch, source_client, ConnectorTransportError,
)

HOST = "goszakaz.e-dag.ru"
LIST = "https://" + HOST + "/smallpurchases/GzwSP/NoticesGrid"
DETAIL = "/smallpurchases/GzwSP/Notice"
MAX_BYTES = 1_800_000
REQUIRED = 2
IDENTITY = re.compile(r"[0-9]{5,12}\\Z")
NATIVE_ID = re.compile(r"ИМЗ[-–]20[0-9]{2}[-–][0-9]{4,8}", re.I)


def compact(raw):
    return " ".join(raw.split())


class PublicHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.visible, self.rows = [], [], []
        self.link = self.row = self.cell = None
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "svg", "iframe", "noscript", "template"}:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag == "a":
            self.link = [dict(attrs).get("href"), []]
        if tag == "tr":
            self.row = []
        if tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.hidden:
            return
        self.visible.append(data)
        if self.link is not None:
            self.link[1].append(data)
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if self.hidden:
            if self.hidden[-1] == tag:
                self.hidden.pop()
            return
        if tag == "a" and self.link is not None:
            self.links.append((self.link[0], compact(" ".join(self.link[1]))))
            self.link = None
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(compact(" ".join(self.cell)))
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def parse(data):
    if type(data) is not bytes or not 0 < len(data) <= MAX_BYTES or b"\\x00" in data:
        raise ValueError("Untrusted Dagestan public procurement HTML")
    html = PublicHTML()
    html.feed(data.decode("utf-8-sig", "replace"))
    html.close()
    return html


def canonical(href):
    if type(href) is not str or not 0 < len(href) <= 450 or "\\\\" in href:
        return None
    if any(x.isspace() or ord(x) < 32 for x in href):
        return None
    try:
        u = urlsplit(urljoin(LIST, href))
        params = parse_qsl(u.query, keep_blank_values=True, strict_parsing=True)
        if (u.scheme != "https" or u.netloc != HOST or u.username is not None
                or u.password is not None or u.port is not None
                or u.path != DETAIL or u.fragment
                or len(params) != 1 or params[0][0] != "noticeLink"
                or not IDENTITY.fullmatch(params[0][1])):
            return None
        number = params[0][1]
        return number, "https://" + HOST + DETAIL + "?noticeLink=" + number
    except ValueError:
        return None


def index_notices(data):
    html = parse(data)
    candidates = []
    seen = set()
    for href, title in html.links:
        dest = canonical(href)
        if dest is None or dest[0] in seen:
            continue
        if not 8 <= len(title) <= 600 or not re.search("[А-Яа-яЁё]", title):
            continue
        seen.add(dest[0])
        candidates.append((dest[0], title, dest[1]))
    if len(candidates) < REQUIRED:
        raise ValueError("Dagestan official first-party listing has fewer than two linked notices")
    return candidates[:REQUIRED]


def detail_proof(body, number, title, url):
    if canonical(url) != (number, url):
        raise ValueError("Wrong independent Dagestan detail identity")
    html = parse(body)
    visible = compact(" ".join(html.visible))
    if title.casefold() not in visible.casefold():
        raise ValueError("Official Dagestan notice title not confirmed on detail page")
    if not NATIVE_ID.search(visible):
        raise ValueError("Original regional small-purchase number absent")
    if not re.search(r"(Заказчик|Наименование заказчика)\\s*:", visible, re.I):
        raise ValueError("Official purchaser missing from detail page")
    if not re.search(r"(Цена|НМЦК|Начальная \\(максимальная\\) цена)", visible, re.I):
        raise ValueError("Original price missing from detail page")
    return number, title, url


async def prove_live():
    with bounded_fetch(FetchPolicy(frozenset({HOST}), REQUIRED + 1, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=25, trust_env=False, follow_redirects=False,
            headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
        ) as client:
            res = await client.get(LIST)
            res.raise_for_status()
            if "html" not in res.headers.get("content-type", "").lower():
                raise ValueError("Dagestan official listing is not HTML")
            parsed = parse(res.content)
            print("RU_DAG_PUBLIC_LIST_ANCHORS=" + str(len(parsed.links)))
            print("RU_DAG_NATIVE_DETAIL_ANCHORS=" + str(sum(
                canonical(href) is not None for href, _ in parsed.links)))
            cards = index_notices(res.content)
            verified = []
            for number, title, url in cards:
                detail = await client.get(url)
                detail.raise_for_status()
                if "html" not in detail.headers.get("content-type", "").lower():
                    raise ValueError("Dagestan independent detail not HTML")
                verified.append(detail_proof(detail.content, number, title, url))
            if len({v[0] for v in verified}) != REQUIRED:
                raise ValueError("Dagestan first-party procurement IDs are not distinct")
            return verified


def main():
    try:
        notices = asyncio.run(prove_live())
        print("RU_DAG_REAL_INDEPENDENT_NOTICES=" + str(len(notices)))
        print("RU_DAG_SMALL_PUBLIC=PASS_RESEARCH_ONLY")
        print("PRODUCTION_CHANGED=NO")
        return 0 if len(notices) == REQUIRED else 2
    except (ValueError, ConnectorTransportError, httpx.HTTPError, OSError,
            TimeoutError) as error:
        print("RU_DAG_SMALL_PUBLIC=BLOCKED_" + type(error).__name__)
        if isinstance(error, ConnectorTransportError):
            print("RU_DAG_RETRYABLE=" + str(error.retryable))
        print("PRODUCTION_CHANGED=NO")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
