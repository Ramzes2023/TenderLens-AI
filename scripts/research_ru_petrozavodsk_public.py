"""Fail-closed first-party Petrozavodsk municipal small-purchase discovery.

Only public, same-host purchase UUID links from the public listing are used;
an independently fetched detail must contain a distinct official procurement
number and exactly matching name. This is NOT a production adapter.
"""
from __future__ import annotations

import asyncio
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit
import uuid

import httpx
from app.sources.http import FetchPolicy, bounded_fetch, source_client, ConnectorTransportError

HOST = "eshop-ptz.ru"
LIST_URL = "https://eshop-ptz.ru/"
SECOND_LIST_URL = "https://eshop-ptz.ru/purchases"
MAX_BYTES = 1_800_000
DETAILS_REQUIRED = 2
NUMBER_RE = re.compile(r"^Закупка\s*№\s*(\d{12,18})\s+(.{8,400})$", re.I)


def normalize(value):
    return " ".join(value.split())


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.headings = [], []
        self.anchor = None
        self.heading = None
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "svg", "template", "noscript", "iframe"):
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag == "a":
            self.anchor = [dict(attrs).get("href"), []]
        if tag in ("h1", "h2", "h3", "h4"):
            self.heading = []

    def handle_data(self, data):
        if self.hidden:
            return
        if self.anchor is not None:
            self.anchor[1].append(data)
        if self.heading is not None:
            self.heading.append(data)

    def handle_endtag(self, tag):
        if self.hidden:
            if self.hidden[-1] == tag:
                self.hidden.pop()
            return
        if tag == "a" and self.anchor is not None:
            self.links.append((self.anchor[0],normalize(" ".join(self.anchor[1]))))
            self.anchor = None
        if tag in ("h1", "h2", "h3", "h4") and self.heading is not None:
            self.headings.append(normalize(" ".join(self.heading)))
            self.heading = None


def document(body):
    if type(body) is not bytes or not 0 < len(body) <= MAX_BYTES or b"\0" in body:
        raise ValueError("Empty or oversized municipal listing/detail")
    page = VisibleHTML()
    page.feed(body.decode("utf-8-sig","replace"))
    page.close()
    return page


def canonical_purchase(href):
    if (type(href) is not str or not 0 < len(href) <= 350 or "\\" in href
            or any(ch.isspace() or ord(ch) < 32 for ch in href)):
        return None
    try:
        url = urlsplit(urljoin(LIST_URL, href))
        if (url.scheme != "https" or url.netloc != HOST
                or url.port is not None or url.username is not None or url.password is not None
                or url.query or url.fragment):
            return None
        parts = url.path.split("/")
        if len(parts) != 3 or parts[1] != "purchases":
            return None
        if str(uuid.UUID(parts[2])) != parts[2].lower() or parts[2] != parts[2].lower():
            return None
        return LIST_URL + "purchases/" + parts[2]
    except ValueError:
        return None


def listing_links(body):
    rows, seen = [], set()
    for href, text in document(body).links:
        url = canonical_purchase(href)
        if not url or url in seen or not 8 <= len(text) <= 500:
            continue
        seen.add(url)
        # Listing label can include the publication number. Never invent it.
        match = NUMBER_RE.fullmatch(text)
        number = match.group(1) if match else None
        title = match.group(2) if match else text
        if not re.search(r"[А-Яа-яЁё]",title):
            continue
        rows.append((url, number, title))
    return rows


def verified_detail(body, listed_number, listed_title):
    headings = document(body).headings
    matches = [NUMBER_RE.fullmatch(h) for h in headings]
    matches = [match for match in matches if match]
    if len(matches) != 1:
        raise ValueError("No single independent municipal purchase heading")
    m = matches[0]
    number, title = m.group(1), normalize(m.group(2))
    if (listed_number is not None and listed_number != number) or title.casefold() != normalize(listed_title).casefold():
        raise ValueError("Municipal listing/detail number or title mismatch")
    return number, title


async def run():
    # 2 listing attempts + 2 linked canonical details. No session tricks.
    with bounded_fetch(FetchPolicy(frozenset({HOST}), 4, max_bytes=MAX_BYTES)):
        async with source_client(
            timeout=22, trust_env=False, follow_redirects=False,
            headers={"Accept":"text/html","User-Agent":"Mozilla/5.0"},
        ) as client:
            links = []
            for url in (LIST_URL, SECOND_LIST_URL):
                response = await client.get(url)
                response.raise_for_status()
                if "html" not in response.headers.get("content-type", "").lower():
                    raise ValueError("Public municipal listing is not HTML")
                links = listing_links(response.content)
                print("RU_PTZ_CANONICAL_LIST_LINKS=" + str(len(links)))
                if len(links) >= DETAILS_REQUIRED:
                    break
            if len(links) < DETAILS_REQUIRED:
                raise ValueError("No two independent official public purchase links")
            results, numbers = [], set()
            for url, listed_number, listed_title in links[:DETAILS_REQUIRED]:
                detail = await client.get(url)
                detail.raise_for_status()
                if "html" not in detail.headers.get("content-type", "").lower():
                    raise ValueError("Public municipal detail is not HTML")
                number,title=verified_detail(detail.content, listed_number, listed_title)
                if number in numbers:
                    raise ValueError("Municipal purchases share same number")
                numbers.add(number)
                results.append((number,title,url))
            return results


def main():
    try:
        results = asyncio.run(run())
        print("RU_PTZ_INDEPENDENT_DETAILS=" + str(len(results)))
        print("RU_PTZ_DISCOVERY=PASS_RESEARCH_ONLY" if len(results)==DETAILS_REQUIRED else "RU_PTZ_DISCOVERY=BLOCKED")
        print("PRODUCTION_CHANGED=NO")
        return 0 if len(results)==DETAILS_REQUIRED else 2
    except (ValueError, ConnectorTransportError, httpx.HTTPError, OSError, TimeoutError) as exc:
        print("RU_PTZ_DISCOVERY=BLOCKED_" + type(exc).__name__)
        if isinstance(exc, ConnectorTransportError):
            print("RU_PTZ_RETRYABLE=" + str(exc.retryable))
        print("PRODUCTION_CHANGED=NO")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
