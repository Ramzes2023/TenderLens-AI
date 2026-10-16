"""Opt-in 44-FZ EIS official public search listing, not legacy 404 RSS.

Source is deliberately listing-only: official detail links currently return 404
from the probe host. Never claim independent detail confirmation from this data.
Uses only vetted application-scoped CA, strict official HTTPS, no TLS bypass.
"""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import parse_qs, urljoin, urlsplit

from .http import FetchPolicy, _policy, bounded_fetch, source_client
from .models import TenderNotice
from .opportunities import validate_notice

SOURCE_ID = "eis_44_html"
HOST = "zakupki.gov.ru"
LIST_URL = f"https://{HOST}/epz/order/extendedsearch/results.html?fz44=on&pageNumber=1"
MAX_BYTES = 1_200_000
MAX_RECORDS = 10
NUMBER = re.compile(r"[0-9]{18,20}")
NOTICE_PATH = re.compile(r"/epz/order/notice/[a-z0-9-]{2,24}/view/common-info\.html")


def _clean(parts):
    return " ".join(" ".join(parts).split())


class _PublicCards(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.card = None
        self.depth = 0
        self.in_link = False
        self.cards = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.card is None:
            if tag == "div" and "search-registry-entry-block" in a.get("class", "").split():
                self.card = {"text": [], "links": []}
                self.depth = 1
            return
        if tag == "div":
            self.depth += 1
        if tag == "a" and a.get("href"):
            self.card["links"].append([a["href"], []])
            self.in_link = True

    def handle_data(self, data):
        if self.card is not None:
            self.card["text"].append(data)
            if self.in_link and self.card["links"]:
                self.card["links"][-1][1].append(data)

    def handle_endtag(self, tag):
        if self.card is None:
            return
        if tag == "a":
            self.in_link = False
        if tag == "div":
            self.depth -= 1
            if self.depth == 0:
                self.cards.append(self.card)
                self.card = None
                self.in_link = False


def parse_official_44_listing(payload, limit=MAX_RECORDS):
    if type(limit) is not int or not 1 <= limit <= MAX_RECORDS:
        raise ValueError("Invalid EIS public listing bound")
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_BYTES or b"\x00" in payload:
        raise ValueError("Invalid EIS public listing bytes")
    reader = _PublicCards()
    reader.feed(payload.decode("utf-8-sig", "replace"))
    reader.close()
    notices = []
    seen = {}
    for card in reader.cards:
        text = _clean(card["text"])
        # Explicit source-result law marker is mandatory, not an HTTP query hint.
        if not text.startswith("44-ФЗ "):
            raise ValueError("Official EIS result lacks 44-FZ card law marker")
        details = []
        for href, text_parts in card["links"]:
            if type(href) is not str or len(href) > 2000:
                continue
            try:
                url = urlsplit(urljoin(f"https://{HOST}/", href))
                params = parse_qs(url.query, keep_blank_values=True)
            except ValueError:
                continue
            if (url.scheme != "https" or url.netloc != HOST
                    or not NOTICE_PATH.fullmatch(url.path)
                    or url.fragment or set(params) != {"regNumber"}
                    or len(params["regNumber"]) != 1):
                continue
            identity = params["regNumber"][0]
            if not NUMBER.fullmatch(identity):
                continue
            if identity not in _clean(text_parts):
                continue
            details.append((identity, url.geturl()))
        # Exactly one main procurement number: no guessing about which notice
        # a multi-link block represents.
        if len(set(details)) != 1:
            raise ValueError("Missing or ambiguous official 44-FZ notice link")
        identity, url = details[0]
        match = re.search(r"^44-ФЗ\s+(.+?)\s+№\s*" + re.escape(identity) + r"(?:\s|$)", text)
        if not match:
            raise ValueError("Unverifiable EIS notice title/number alignment")
        title = match.group(1).strip()
        if len(title) < 5 or len(title) > 800:
            raise ValueError("Invalid EIS procurement title")
        # All values below come from that same official search-result card.
        notice = TenderNotice(
            source=SOURCE_ID,
            external_id=identity,
            tender_number=identity,
            title=title,
            url=url,
        )
        validate_notice(notice, SOURCE_ID)
        if identity in seen:
            if seen[identity] != notice:
                raise ValueError("Conflicting EIS 44-FZ procurement identity")
            continue
        seen[identity] = notice
        notices.append(notice)
        if len(notices) == limit:
            break
    if not notices:
        raise ValueError("EIS 44-FZ public result has no verifiable cards")
    return notices


@dataclass(frozen=True)
class Eis44PublicHtmlSource:
    ca_bundle_file: Path
    timeout: float = 20
    name: str = SOURCE_ID

    def __post_init__(self):
        if (self.name != SOURCE_ID or not isinstance(self.ca_bundle_file, Path)
                or not self.ca_bundle_file.is_file()
                or type(self.timeout) not in (int, float)
                or not 0 < self.timeout <= 30):
            raise ValueError("Official EIS public HTML requires a vetted application CA file")

    async def fetch(self, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid EIS public listing limit")
        constraint = (bounded_fetch(FetchPolicy(frozenset({HOST}), 1,
                                              max_bytes=MAX_BYTES))
                      if _policy.get() is None else nullcontext())
        with constraint:
            async with source_client(
                timeout=self.timeout,
                trust_env=False,
                follow_redirects=False,
                verify=str(self.ca_bundle_file),
                headers={"Accept": "text/html"},
            ) as client:
                response = await client.get(LIST_URL)
                response.raise_for_status()
                if "html" not in response.headers.get("content-type", "").lower():
                    raise ValueError("EIS public results not HTML")
                return parse_official_44_listing(response.content, limit=min(limit, MAX_RECORDS))
