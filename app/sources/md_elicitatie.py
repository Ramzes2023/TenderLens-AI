"""Real Moldova e-Licitație marketplace: public municipal and small purchases.

Independent accredited MTender operator, NOT official MTender OCDS API.
Fail-closed notice identity, buyer, amount, date and detail requirements.
The source stays disabled pending genuine hosted live worker + SQLite + search CI.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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

HOST = "e-licitatie.md"
INDEX_URL = "https://e-licitatie.md/achizitii"
BASE = "https://e-licitatie.md"
MAX_BODY = 1024 * 1024
MAX_DETAILS = 5
MAX_CANDIDATES = 10
DETAIL_PATH = re.compile(r"/achizitii/([1-9]\d{3,8})/([a-z0-9][a-z0-9-]{2,200})/?")
OCID = re.compile(r"ocds-b3wdp1-MD-\d{10,18}", re.I)
DATE = r"(\d{1,2}/\d{1,2}/20\d{2}\s+\d{1,2}:\d{2})"
AMOUNT = re.compile(r"(\d{1,3}(?:[,.\s\u00a0]\d{3})*(?:[.,]\d{2}))\s*MDL\b", re.I)


class _Visible(HTMLParser):
    """HTML cards/headings, excluding scripts/styles; no JavaScript eval."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tokens = []
        self.links = []
        self.headings = []
        self.hidden = []
        self.anchors = []
        self.heading = None

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "noscript"}:
            self.hidden.append(tag)
            return
        if self.hidden:
            return
        if tag == "a":
            self.anchors.append([dict(attrs).get("href", ""), []])
        if tag in {"h1", "h2"}:
            self.heading = [tag, []]

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
            return
        if tag == "a" and self.anchors:
            url, parts = self.anchors.pop()
            self.links.append((" ".join(parts).strip(), url))
        if self.heading is not None and tag == self.heading[0]:
            kind, parts = self.heading
            self.headings.append((kind, " ".join(parts).strip()))
            self.heading = None

    def handle_data(self, data):
        if self.hidden:
            return
        value = " ".join(data.split())
        if value:
            self.tokens.append(value)
            if self.anchors:
                self.anchors[-1][1].append(value)
            if self.heading is not None:
                self.heading[1].append(value)


def _visible(html):
    if not isinstance(html, str) or len(html.encode("utf-8")) > MAX_BODY:
        raise SourceError("MD e-Licitație malformed or oversized HTML.")
    result = _Visible()
    result.feed(html)
    return result


def _approved(raw):
    if not isinstance(raw, str):
        return None
    try:
        parts = urlsplit(raw)
        if (parts.scheme not in ("", "https") or parts.username or parts.password
                or parts.query or parts.fragment or parts.port not in (None, 443)
                or (parts.scheme and parts.hostname != HOST)
                or (not parts.scheme and parts.netloc)):
            return None
        match = DETAIL_PATH.fullmatch(parts.path)
    except ValueError:
        return None
    return BASE + parts.path.rstrip("/") if match is not None else None


def discover_index(html):
    """Require actual displayed tender anchors; reject JS-only or foreign URLs."""
    found = {}
    for title, raw in _visible(html).links:
        url = _approved(raw)
        if url is not None and 8 <= len(title) <= 1000:
            if url in found and found[url] != title:
                raise SourceError("MD e-Licitație conflicting card titles.")
            found[url] = title
    if not 2 <= len(found) <= 100:
        raise SourceError("MD e-Licitație no multiple genuine public tender links.")
    return tuple(found.items())


def _date(value):
    try:
        return datetime.strptime(" ".join(value.split()), "%d/%m/%Y %H:%M")
    except ValueError:
        raise SourceError("MD e-Licitație unrecognized local date.") from None


def _price(value):
    value = value.replace("\u00a0", "").replace(" ", "")
    if not re.fullmatch(r"\d{1,3}(?:[,.]\d{3})*(?:[.,]\d{2})", value):
        raise SourceError("MD e-Licitație invalid estimate.")
    separator = max(value.rfind("."), value.rfind(","))
    parsed = float(re.sub(r"[,.]", "", value[:separator]) + "." + value[separator + 1:])
    if not math.isfinite(parsed) or not 0 <= parsed <= 1e18:
        raise SourceError("MD e-Licitație amount out of bounds.")
    return parsed


def _normalized(text):
    return " ".join(text.split()).casefold()


def parse_marketplace_detail(html, *, url, expected_title):
    if _approved(url) != url or type(expected_title) is not str or not 8 <= len(expected_title) <= 1000:
        raise SourceError("MD e-Licitație invalid indexed detail identity.")
    page = _visible(html)
    headings = [s for kind, s in page.headings if kind == "h1"]
    if len(headings) != 1 or not headings[0].startswith("Achiziție - "):
        raise SourceError("MD e-Licitație detail heading missing.")
    title = headings[0][len("Achiziție - "):].strip()
    if _normalized(title) != _normalized(expected_title):
        raise SourceError("MD e-Licitație card/detail title mismatch.")
    buyers = [s[len("Achiziție "):].strip() for kind, s in page.headings
              if kind == "h2" and s.startswith("Achiziție ")]
    if len(buyers) != 1 or not 4 <= len(buyers[0]) <= 2000:
        raise SourceError("MD e-Licitație named procuring authority missing.")

    text = " ".join(page.tokens)
    match = re.search(r"Informa[țţ]ie\s+general[ăa]\b(.*?)Surse de finan[țţ]are\b", text, re.I)
    if match is None:
        raise SourceError("MD e-Licitație bounded general information unavailable.")
    body = match.group(1)
    ids = list(OCID.finditer(body))
    if len(ids) != 1:
        raise SourceError("MD e-Licitație distinct OCDS identity missing.")
    ocid = ids[0].group(0)
    amounts = AMOUNT.findall(body[:ids[0].start()])
    if len(amounts) != 1:
        raise SourceError("MD e-Licitație notice-level amount missing.")
    published = re.search(r"publicat[ăa]\s+" + DATE, body, re.I)
    submission = re.search(r"depunere\s+" + DATE, body, re.I)
    if published is None or submission is None:
        raise SourceError("MD e-Licitație public publication/deadline missing.")
    start, end = _date(published.group(1)), _date(submission.group(1))
    if end < start:
        raise SourceError("MD e-Licitație deadline before publication.")
    external = DETAIL_PATH.fullmatch(urlsplit(url).path).group(1)
    notice = TenderNotice(
        source="md_elicitatie", external_id=ocid, tender_number=ocid,
        title=title, url=url, customer=buyers[0],
        published_at=start.isoformat(), deadline=end.isoformat(),
        initial_price=_price(amounts[0]), currency="MDL",
        summary=f"Moldova e-Licitație public notice {external}; accredited MTender marketplace",
    )
    try:
        validate_notice(notice, "md_elicitatie")
    except (TypeError, ValueError):
        raise SourceError("MD e-Licitație normalized public notice invalid.") from None
    return notice


@dataclass(frozen=True)
class MoldovaELicitatieSource:
    timeout: float = 12.0
    name: str = "md_elicitatie"

    def __post_init__(self):
        if (type(self.timeout) not in (float, int) or not math.isfinite(self.timeout)
                or not 0 < self.timeout <= 30):
            raise ValueError("MD e-Licitație timeout out of range.")

    async def fetch(self, limit=5):
        if _policy.get() is None:
            with bounded_fetch(FetchPolicy(frozenset({HOST}), 1 + MAX_CANDIDATES, max_bytes=MAX_BODY)):
                return await self._fetch(limit)
        return await self._fetch(limit)

    async def _fetch(self, limit):
        if type(limit) is not int:
            raise SourceError("MD e-Licitație limit must be an integer.")
        count = max(1, min(limit, MAX_DETAILS))
        accepted, seen = [], set()
        try:
            async with source_client(timeout=self.timeout, trust_env=False,
                                     follow_redirects=False) as client:
                listing = await client.get(INDEX_URL)
                listing.raise_for_status()
                if "html" not in listing.headers.get("content-type", "").lower():
                    raise SourceError("MD e-Licitație listing was not HTML.")
                for url, title in discover_index(listing.text)[:MAX_CANDIDATES]:
                    detail = await client.get(url)
                    detail.raise_for_status()
                    if "html" not in detail.headers.get("content-type", "").lower():
                        raise SourceError("MD e-Licitație detail was not HTML.")
                    try:
                        notice = parse_marketplace_detail(detail.text, url=url, expected_title=title)
                    except SourceError:
                        continue  # A malformed single card never becomes a real opportunity.
                    if notice.identity in seen:
                        raise SourceError("MD e-Licitație conflicting duplicate notice.")
                    accepted.append(notice)
                    seen.add(notice.identity)
                    if len(accepted) >= count:
                        break
        except (httpx.HTTPError, ConnectorTransportError, OSError) as error:
            if transient_transport(error):
                raise SourceTransportError("MD e-Licitație official HTTPS temporarily unavailable.") from None
            raise SourceError("MD e-Licitație HTTPS failed.") from None
        if not accepted:
            raise SourceError("MD e-Licitație no complete verified public tenders.")
        return accepted
