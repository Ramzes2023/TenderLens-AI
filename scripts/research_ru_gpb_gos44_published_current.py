"""First-party GPB Gos44 CURRENT published listing -> two independent details.

Research-only, not a second unique feed: all notices are 44-FZ and overlap
with EIS. Never expose to customer catalog or count as distinct procurements.
No saved historical URLs, credentials, proxies, redirects or TLS exceptions.
"""
from __future__ import annotations

import asyncio
import re
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urljoin, urlsplit

import httpx

from app.sources.http import ConnectorTransportError, FetchPolicy, bounded_fetch, source_client

HOST = "gos.etpgpb.ru"
LIST_URL = "https://" + HOST + "/44/catalog/procedure/published"
BACKURL = "LzQ0L2NhdGFsb2cvcHJvY2VkdXJlL3B1Ymxpc2hlZA=="
MAX_BYTES = 2_200_000
MAX_CANDIDATES = 8
MAX_DETAILS = 2
IDENTITY = re.compile(r"(?<![0-9])([0-9]{19})(?![0-9])")
DETAIL = re.compile(r"/front/procedure/view/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}")


def canonical(href: str):
    if (type(href) is not str or not 0 < len(href) <= 1300
            or "%" in href or "\\" in href
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in href)):
        return None
    try:
        url = urlsplit(urljoin(LIST_URL, href))
        params = parse_qsl(url.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return None
    if (url.scheme != "https" or url.netloc != HOST or url.fragment
            or url.username or url.password or url.port is not None
            or not DETAIL.fullmatch(url.path)
            or params != [("backurl", BACKURL)]):
        return None
    return url.geturl()


class VisibleRows(HTMLParser):
    HIDDEN = frozenset({"head", "script", "style", "template", "noscript", "svg", "iframe"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = []
        self.row = None
        self.rows = []
        self.link = None

    def handle_starttag(self, tag, attrs):
        if tag in self.HIDDEN:
            self.hidden.append(tag)
            return
        if self.hidden:
            return
        if tag == "tr":
            self.row = {"text": [], "links": []}
        if tag == "a" and self.row is not None:
            self.link = {"href": dict(attrs).get("href"), "title": []}

    def handle_data(self, data):
        if self.hidden:
            return
        if self.row is not None:
            self.row["text"].append(data)
        if self.link is not None:
            self.link["title"].append(data)

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
            return
        if tag == "a" and self.link is not None:
            href = canonical(self.link["href"])
            title = " ".join(" ".join(self.link["title"]).split())
            if href and 5 <= len(title) <= 1600:
                self.row["links"].append((href, title))
            self.link = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


class VisibleDocument(HTMLParser):
    HIDDEN = VisibleRows.HIDDEN

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = []
        self.words = []

    def handle_starttag(self, tag, attrs):
        if tag in self.HIDDEN:
            self.hidden.append(tag)

    def handle_endtag(self, tag):
        if self.hidden and tag == self.hidden[-1]:
            self.hidden.pop()

    def handle_data(self, data):
        if not self.hidden:
            self.words.append(data)


def _parser(payload: bytes, cls):
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_BYTES or b"\0" in payload:
        raise ValueError("Invalid bounded official Gos44 document")
    parser = cls()
    parser.feed(payload.decode("utf-8-sig", "replace"))
    parser.close()
    return parser


def published_candidates(payload: bytes):
    rows = _parser(payload, VisibleRows).rows
    verified, seen = [], {}
    for row in rows:
        visible = " ".join(" ".join(row["text"]).split())
        ids = set(IDENTITY.findall(visible))
        if len(ids) != 1:
            continue
        number = next(iter(ids))
        for url, title in row["links"]:
            prev = seen.get(number)
            if prev is not None and prev != (url, title):
                raise ValueError("Conflicting first-party Gos44 EIS identity")
            if prev is None:
                seen[number] = (url, title)
                verified.append((number, title, url))
                break
        if len(verified) >= MAX_CANDIDATES:
            break
    if len(verified) < MAX_DETAILS:
        raise ValueError("Current Gos44 published list has fewer than two distinct originals")
    return verified


def _tokens(raw: str):
    return set(re.findall(r"[А-Яа-яЁёA-Za-z0-9]{3,}", raw.lower()))


def independently_verify_detail(body: bytes, number: str, title: str, original_url: str):
    if (type(number) is not str or not re.fullmatch(r"[0-9]{19}", number)
            or type(title) is not str or not 5 <= len(title) <= 1600
            or canonical(original_url) != original_url):
        raise ValueError("Noncanonical Gos44 original detail request")
    text = " ".join(" ".join(_parser(body, VisibleDocument).words).split())
    if not re.search(r"Сведения\s+о\s+процедуре\s+[А-ЯA-Z0-9()]+\s+" + re.escape(number) + r"(?![0-9])", text):
        raise ValueError("Official procedure heading does not corroborate EIS ID")
    if not re.search(r"Номер\s+извещения\s+" + re.escape(number) + r"(?![0-9])", text):
        raise ValueError("Official labeled 19-digit EIS notice is missing")
    match = re.search(
        r"Наименование\s+объекта\s+закупки\s+(.{5,1600}?)\s+Идентификационный\s+код\s+закупки",
        text,
    )
    if not match:
        raise ValueError("Official visible native procurement title not independently labeled")
    native_title = match.group(1).strip()
    listed, actual = _tokens(title), _tokens(native_title)
    if len(listed) < 2 or len(listed & actual) / len(listed) < .70:
        raise ValueError("GPB indexed/current detail original titles differ")
    return number, native_title, original_url


async def current_publisher_proof():
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 1 + MAX_CANDIDATES,
                                   max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=25, trust_env=False, follow_redirects=False,
            headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
        ) as client:
            page = await client.get(LIST_URL)
            page.raise_for_status()
            if "html" not in page.headers.get("content-type", "").lower():
                raise ValueError("Gos44 current public list is not HTML")
            candidates = published_candidates(page.content)
            accepted = []
            for number, title, url in candidates:
                try:
                    detail = await client.get(url)
                    detail.raise_for_status()
                    if "html" not in detail.headers.get("content-type", "").lower():
                        raise ValueError("Published Gos44 original detail not HTML")
                    accepted.append(independently_verify_detail(detail.content, number, title, url))
                except (ValueError, httpx.HTTPStatusError):
                    continue
                if len(accepted) >= MAX_DETAILS:
                    break
            if len({item[0] for item in accepted}) != MAX_DETAILS:
                raise ValueError("No two current, independently verified GPB Gos44 originals")
            return accepted


def main():
    try:
        result = asyncio.run(current_publisher_proof())
    except (ValueError, ConnectorTransportError, httpx.HTTPError, OSError, TimeoutError) as e:
        print("RU_GPB_GOS44_PUBLISHED=BLOCKED")
        print("FAILURE_CLASS=" + type(e).__name__)
        if isinstance(e, ConnectorTransportError):
            print("TRANSPORT_REASON=" + str(e.reason))
            print("RETRYABLE=" + str(e.retryable))
        print("WORKER_SQL_ACCEPTED=NO")
        print("EIS_44FZ_MIRROR_NOT_UNIQUE=YES")
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_GPB_GOS44_PUBLISHED=PASS_RESEARCH_ONLY")
    print("REAL_FIRSTPARTY_LIST_TO_INDEPENDENT_DETAILS=" + str(len(result)))
    print("WORKER_SQL_ACCEPTED=NO")
    print("EIS_44FZ_MIRROR_NOT_UNIQUE=YES")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
