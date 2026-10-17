"""Read-only, independently corroborated commercial procedures on two RU platforms.

Never follow a session URL or borrowed EIS 223-FZ link, and do not count an
HTTP 200 page or example detail as proof of an operational tender feed.
A listing must link to two different first-party detail pages with matching
platform-only numbers and names. No production or credentials.
"""
from __future__ import annotations

import asyncio
from html.parser import HTMLParser
import re
import sys
from urllib.parse import parse_qsl, quote, urljoin, urlsplit

import httpx
from app.sources.http import FetchPolicy, bounded_fetch, source_client, ConnectorTransportError

PLATFORMS = {
    "torgi_online": ("etp.etptorgionline.ru", "/app/section/commerc/SearchLots/page"),
    "r_tender": ("etp.r-tender.ru", "/app/section/kommerctorg/SearchLots/page"),
}
BYTES_MAX = 1_800_000
LIST_LIMIT = 2
UUID_PATTERN = re.compile(r"Score[a-z0-9]{15,70}\Z")
# An explicitly first-party procedure, not an 11-digit EIS registry identity.
NUMBER = re.compile(r"(?:[0-9]{8,12}DP|[A-ZА-Я]{1,4}-20[0-9]{2}-[0-9]{5,8})\Z")


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.visible = [], []
        self.link = None
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "svg", "template", "noscript", "iframe"}:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag == "a":
            self.link = [dict(attrs).get("href"), []]

    def handle_data(self, data):
        if self.hidden:
            return
        self.visible.append(data)
        if self.link is not None:
            self.link[1].append(data)

    def handle_endtag(self, tag):
        if self.hidden:
            if self.hidden[-1] == tag:
                self.hidden.pop()
            return
        if tag == "a" and self.link is not None:
            href, parts = self.link
            self.links.append((href, " ".join(" ".join(parts).split())))
            self.link = None


def read_html(body):
    if type(body) is not bytes or not 0 < len(body) <= BYTES_MAX or b"\0" in body:
        raise ValueError("Untrusted or oversized commercial HTML")
    doc = VisibleHTML()
    doc.feed(body.decode("utf-8-sig", "replace"))
    doc.close()
    return doc


def canonical_card(host: str, href: str):
    if (host not in {x[0] for x in PLATFORMS.values()}
            or type(href) is not str or not 0 < len(href) <= 450
            or "\\" in href or any(ch.isspace() or ord(ch) < 32 for ch in href)):
        return None
    try:
        u = urlsplit(urljoin("https://" + host + "/", href))
        pairs = parse_qsl(u.query, keep_blank_values=True, strict_parsing=True)
        if (u.scheme != "https" or u.netloc != host or u.username is not None
                or u.password is not None or u.port is not None
                or u.fragment or u.path != "/app/OfferCard/page"
                or len(pairs) != 1 or pairs[0][0] != "OfferCard.offerUUID"
                or not UUID_PATTERN.fullmatch(pairs[0][1])):
            return None
        return "https://" + host + "/app/OfferCard/page?OfferCard.offerUUID=" + pairs[0][1]
    except ValueError:
        return None


def listing_cards(body, host):
    page = read_html(body)
    grouped = {}
    for href, text in page.links:
        url = canonical_card(host, href)
        if not url:
            continue
        # Read only stable native procedure ID + title from the anchor itself.
        # Do not create a notice from "numberless" search controls.
        match = re.match(r"(?:Закупка\s+)?(?!3\d{10}\b)([0-9]{8,12}DP|[A-ZА-Я]{1,4}-20\d{2}-\d{5,8})\s*[:–—-]\s*(.{8,600})\Z", text)
        if not match or not NUMBER.fullmatch(match.group(1)):
            continue
        number, title = match.group(1), match.group(2).strip()
        if not re.search(r"[А-Яа-яЁё]", title):
            continue
        if url in grouped and grouped[url] != (number, title):
            raise ValueError("Conflicting first-party commercial detail listing")
        grouped[url] = (number, title)
    if len(grouped) < LIST_LIMIT:
        raise ValueError("No two native first-party commercial cards linked by public listing")
    return [(num, title, url) for url, (num, title) in list(grouped.items())[:LIST_LIMIT]]


def verify_detail(body, host, number, title, url):
    if (not NUMBER.fullmatch(number) or canonical_card(host, url) != url
            or not 8 <= len(title) <= 600):
        raise ValueError("Invalid canonical commercial notice identity")
    content = " ".join(" ".join(read_html(body).visible).split())
    if "Коммерческая закупка" not in content:
        raise ValueError("Native commercial provenance not visible")
    if re.search(r"Реестровый номер\s+3\d{10}\s+ЕИС", content):
        raise ValueError("External 223-FZ EIS mirror, not native commercial procurement")
    if not re.search(r"Номер процедуры\s+" + re.escape(number) + r"(?![0-9A-Za-z])", content):
        raise ValueError("Commercial number not confirmed on official detail")
    if not re.search(r"Наименование\s+закупки\s+" + re.escape(title) + r"(?:\s|$)", content, re.I):
        raise ValueError("Listing title not corroborated on official detail")
    return (number, title, url)


async def probe(source_id: str):
    if source_id not in PLATFORMS:
        raise ValueError("Source is not explicitly allowed")
    host, path = PLATFORMS[source_id]
    async with source_client(
        timeout=24, follow_redirects=False, trust_env=False,
        headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
    ) as client:
        with bounded_fetch(FetchPolicy(frozenset({host}), LIST_LIMIT+1, max_bytes=BYTES_MAX)):
            list_resp = await client.get("https://" + host + path)
            list_resp.raise_for_status()
            if "html" not in list_resp.headers.get("content-type", "").lower():
                raise ValueError("Public commercial listing not HTML")
            cards = listing_cards(list_resp.content, host)
            results = []
            for number, title, url in cards:
                detail = await client.get(url)
                detail.raise_for_status()
                if "html" not in detail.headers.get("content-type", "").lower():
                    raise ValueError("First-party commercial detail not HTML")
                results.append(verify_detail(detail.content, host, number, title, url))
            return results


def main(source):
    try:
        verified = asyncio.run(probe(source))
    except (ValueError, ConnectorTransportError, httpx.HTTPError, OSError, TimeoutError) as exc:
        print("RU_COMMERCIAL_DISCOVERY=BLOCKED_" + type(exc).__name__)
        if isinstance(exc, ConnectorTransportError):
            print("RU_COMMERCIAL_TRANSPORT_RETRYABLE=" + str(exc.retryable))
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_COMMERCIAL_SOURCE=" + source)
    print("RU_COMMERCIAL_GENUINE_DETAIL_COUNT=" + str(len(verified)))
    print("RU_COMMERCIAL_DISCOVERY=" + ("PASS_RESEARCH_NOT_INTEGRATED" if len(verified)==2 else "BLOCKED"))
    print("PRODUCTION_CHANGED=NO")
    return 0 if len(verified)==2 else 2


if __name__ == "__main__":
    if len(sys.argv)!=2 or sys.argv[1] not in PLATFORMS:
        raise SystemExit("Select only torgi_online or r_tender")
    raise SystemExit(main(sys.argv[1]))
