"""Independent small quotation notices from Azerbaijan Deposit Insurance Fund.

Official single-page procurement articles (not the national eTender feed).
Accept only currently open public opportunities with explicit buyer, publication,
deadline, and first-party tender-document link. Fail closed on changed HTML.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
from html.parser import HTMLParser
from urllib.parse import urlsplit
import math
import re

import httpx

from .eis_rss import SourceError
from .http import ConnectorTransportError, FetchPolicy, _policy, bounded_fetch, source_client
from .models import TenderNotice
from .opportunities import validate_notice
from .transport_errors import SourceTransportError, transient_transport

SOURCE = "az_adif_small"
HOST = "adif.gov.az"
URL = "https://adif.gov.az/az/sale/"
BUYER = "Əmanətlərin Sığortalanması Fondu"
MAX_BYTES = 512 * 1024
MAX_ARTICLES = 100
MAX_RESULTS = 5
MONTHS = {
    "yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5,
    "iyun": 6, "iyul": 7, "avqust": 8, "sentyabr": 9,
    "oktyabr": 10, "noyabr": 11, "dekabr": 12,
}
DEADLINE = re.compile(
    r"Təkliflər\s+(\d{1,2})\s+([a-zçğıöşüə]+)\s+(20\d{2})-c[ıi]\s+il\s+saat\s+(\d{1,2}):(\d{2})",
    re.I)
PUBLISHED = re.compile(r"Elanın yerləşdirilmə tarixi:\s*(\d{2})\.(\d{2})\.(20\d{2})")


class Articles(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.current = None
        self.depth = 0
        self.in_p = 0
        self.pieces = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "template", "noscript"):
            self.hidden += 1
        if tag == "article":
            if self.current is None:
                self.current = {"paragraphs": [], "docs": []}
            self.depth += 1
        if self.current is None or self.hidden:
            return
        if tag == "p":
            if self.in_p == 0:
                self.pieces = []
            self.in_p += 1
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href:
                self.current["docs"].append(href)

    def handle_data(self, data):
        if self.current is not None and self.in_p and not self.hidden:
            self.pieces.append(data)

    def handle_endtag(self, tag):
        if tag == "p" and self.current is not None and self.in_p:
            self.in_p -= 1
            if not self.in_p:
                value = " ".join("".join(self.pieces).split())
                if value:
                    self.current["paragraphs"].append(value)
                self.pieces = []
        if tag == "article" and self.current is not None:
            self.depth -= 1
            if not self.depth:
                if self.in_p:
                    raise SourceError("AZ ADIF malformed public tender article.")
                self.items.append(self.current)
                self.current = None
        if tag in ("script", "style", "template", "noscript") and self.hidden:
            self.hidden -= 1


def _official_doc(raw):
    try:
        parsed = urlsplit(raw)
        if (parsed.scheme != "https" or parsed.hostname != HOST
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or parsed.query or parsed.fragment):
            return False
        return bool(re.fullmatch(
            r"/media/20\d{2}/\d{2}/\d{2}/[a-z0-9_-]{3,160}\.(?:docx|pdf)", parsed.path,
            re.I))
    except (TypeError, ValueError):
        return False


def parse_public_articles(html, *, today=None):
    if type(html) is not str or len(html.encode("utf-8")) > MAX_BYTES:
        raise SourceError("AZ ADIF malformed or oversized official HTML.")
    if today is None:
        today = date.today()
    if type(today) is not date:
        raise SourceError("AZ ADIF invalid freshness clock.")
    parser = Articles()
    parser.feed(html)
    if not 1 <= len(parser.items) <= MAX_ARTICLES or parser.current is not None:
        raise SourceError("AZ ADIF public procurement article structure changed.")
    accepted = {}
    for item in parser.items:
        ps = item["paragraphs"]
        if not ps:
            continue
        titles = [x for x in ps if BUYER.casefold() in x.casefold()
                  and "kotirovka sorğusu elan edir" in x.casefold()]
        if not titles:
            continue
        if len(titles) != 1:
            raise SourceError("AZ ADIF conflicting tender title.")
        title = titles[0]
        if not 24 <= len(title) <= 1000:
            raise SourceError("AZ ADIF invalid public tender title.")
        pub = [PUBLISHED.fullmatch(x) for x in ps if PUBLISHED.fullmatch(x)]
        bids = [DEADLINE.fullmatch(x) for x in ps if DEADLINE.fullmatch(x)]
        docs = list(dict.fromkeys(x for x in item["docs"] if _official_doc(x)))
        if len(pub) != 1 or len(bids) != 1 or not docs:
            raise SourceError("AZ ADIF tender missing deadline, posting, or first-party documents.")
        try:
            day, month, year = (int(x) for x in pub[0].groups())
            posted = date(year, month, day)
            d, monthname, yr, hr, minute = bids[0].groups()
            close = datetime(int(yr), MONTHS[monthname.lower()], int(d), int(hr), int(minute))
        except (ValueError, KeyError):
            raise SourceError("AZ ADIF impossible publication or deadline.") from None
        if close.date() < posted or posted > today + timedelta(days=1):
            raise SourceError("AZ ADIF inconsistent bid window.")
        if (today - posted).days > 90 or close.date() < today:
            continue  # Historical notices are not advertised as active opportunities.
        # First eligible document is the official tender specification, not a
        # generic bidder form: preferring "kotirovka" avoids shared documents.
        eligible = [x for x in docs if "kotirovka" in urlsplit(x).path.casefold()]
        if len(eligible) != 1:
            raise SourceError("AZ ADIF missing unique original tender specification.")
        document = eligible[0]
        identity = sha256((title.casefold() + "|" + posted.isoformat()).encode("utf-8")).hexdigest()[:32]
        notice = TenderNotice(
            source=SOURCE, external_id=identity, title=title, url=document,
            customer=BUYER, published_at=posted.isoformat(),
            deadline=close.isoformat(), region="Bakı", summary="Official small quotation; open bid window.")
        try:
            validate_notice(notice, SOURCE)
        except (TypeError, ValueError, OverflowError):
            raise SourceError("AZ ADIF malformed normalized notice.") from None
        if identity in accepted:
            raise SourceError("AZ ADIF conflicting duplicate public tender.")
        accepted[identity] = notice
        if len(accepted) >= MAX_RESULTS:
            break
    if not accepted:
        raise SourceError("AZ ADIF no currently open complete procurement quotations.")
    return list(accepted.values())


@dataclass(frozen=True)
class AzerbaijanAdifSmallSource:
    timeout: float = 15.0
    name: str = SOURCE

    def __post_init__(self):
        if type(self.timeout) not in (float, int) or not math.isfinite(self.timeout) or not 0 < self.timeout <= 30:
            raise ValueError("AZ ADIF request timeout must be bounded.")

    async def fetch(self, limit=5):
        if type(limit) is not int:
            raise SourceError("AZ ADIF result limit must be integer.")
        if _policy.get() is None:
            with bounded_fetch(FetchPolicy(frozenset({HOST}), 1, max_bytes=MAX_BYTES)):
                return await self._fetch(limit)
        return await self._fetch(limit)

    async def _fetch(self, limit):
        try:
            async with source_client(timeout=self.timeout, trust_env=False, follow_redirects=False) as client:
                response = await client.get(URL)
                response.raise_for_status()
                if "html" not in response.headers.get("content-type", "").lower():
                    raise SourceError("AZ ADIF procurement response not HTML.")
                return parse_public_articles(response.text)[:max(1, min(MAX_RESULTS, limit))]
        except (httpx.HTTPError, ConnectorTransportError, OSError) as error:
            if transient_transport(error):
                raise SourceTransportError("AZ ADIF official HTTPS temporarily unavailable.") from None
            raise SourceError("AZ ADIF strict official HTTPS unavailable.") from None
