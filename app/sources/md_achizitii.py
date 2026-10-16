"""Bounded public tenders from Moldova's accredited Achizitii.md marketplace.

This is a commercial MTender participant platform, NOT the government OCDS API.
Only public pages with a real notice title, buyer, value, dates and MTender OCID
are ingested. No authentication, tenant queries, cookies, redirects or production
activation. The catalog registers this source as non-official and disabled.
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

INDEX_URL = "https://achizitii.md/ro/"
DETAIL_ROOT = "https://achizitii.md"
MAX_BODY = 1024 * 1024
MAX_DETAILS = 5
HOST = "achizitii.md"
DETAIL_PATH = re.compile(r"^/ro/public/tender/([1-9]\d{6,10})/$")
OCID = re.compile(r"^ocds-b3wdp1-MD-\d{10,18}$", re.I)
MONTHS = {"ian":1, "feb":2, "mar":3, "apr":4, "mai":5, "iun":6, "iul":7,
          "aug":8, "sep":9, "oct":10, "nov":11, "dec":12}
CALENDAR = re.compile(r"^(\d{1,2})\s+([a-zăîșț]{3,12})\s+(20\d{2}),?\s+(\d{1,2}):(\d{2})$", re.I)
NUMBER = re.compile(r"^(?:\d{1,3}(?:[\s\u00a0.,]\d{3})+|\d{1,12})(?:[,.]\d{2})?$")


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tokens = []
        self.hidden = 0
        self.href_stack = []
        self.links = []

    def handle_starttag(self, tag, attributes):
        if tag in {"script", "style", "template", "noscript"}:
            self.hidden += 1
        if tag == "a":
            href = dict(attributes).get("href")
            self.href_stack.append(href if isinstance(href, str) else "")
        elif tag in {"div", "li", "p", "br", "h1", "h2", "h3", "td", "th"}:
            if not self.hidden:
                self.tokens.append((" ", ""))

    def handle_endtag(self, tag):
        if tag in {"script", "style", "template", "noscript"}:
            self.hidden = max(0, self.hidden - 1)
        if tag == "a" and self.href_stack:
            self.href_stack.pop()
        if tag in {"div", "li", "p", "h1", "h2", "h3", "td", "th"}:
            if not self.hidden:
                self.tokens.append((" ", ""))

    def handle_data(self, data):
        if not self.hidden:
            value = " ".join(data.split())
            if value:
                href = self.href_stack[-1] if self.href_stack else ""
                self.tokens.append((value, href))


def _approved_href(raw):
    try:
        parts = urlsplit(raw)
        if (parts.scheme and (parts.scheme != "https" or parts.hostname != HOST)
                or parts.username or parts.password or parts.fragment or parts.query
                or parts.port not in (None, 443)):
            return None
        if DETAIL_PATH.fullmatch(parts.path):
            return DETAIL_ROOT + parts.path
    except ValueError:
        return None
    return None


def discover_index(html):
    """Discover the actual bounded public detail anchors, never JS data."""
    if not isinstance(html, str) or len(html.encode("utf-8")) > MAX_BODY:
        raise SourceError("MD listing oversized or malformed.")
    parser = VisibleHTML()
    parser.feed(html)
    discovered = {}
    for token, href in parser.tokens:
        if not href or len(token) < 7:
            continue
        url = _approved_href(href)
        if url:
            discovered[url] = True
    if not 1 <= len(discovered) <= 200:
        raise SourceError("MD marketplace no verified detail URLs.")
    return tuple(discovered)


def _plain_tokens(raw):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_BODY:
        raise SourceError("MD malformed official marketplace HTML.")
    p = VisibleHTML()
    p.feed(raw)
    return [value for value, _ in p.tokens if value.strip()]


def _after(tokens, label, *, limit=5):
    boundaries = {
        "datele achizitiei", "datele achiziției", "codul fiscal/idno",
        "adresa", "web site", "persoana de contact", "data publicării",
        "data ultimilor modificări", "achizitii.md id", "mtender id",
        "informaţia despre solicitant", "informația despre solicitant",
        "valorea estimată", "valoarea estimată fără tva",
    }
    for i, token in enumerate(tokens):
        if token.casefold().startswith(label.casefold() + " "):
            fused = token[len(label):].strip()
            if not fused or len(fused) > 2000:
                raise SourceError("MD malformed same-element detail field.")
            return fused
        if token.casefold() == label.casefold():
            for candidate in tokens[i+1:i+1+limit]:
                if candidate.strip() and candidate.casefold() != label.casefold():
                    if candidate.strip().casefold() in boundaries:
                        raise SourceError("MD detail field ended without a value.")
                    return candidate.strip()
    raise SourceError("MD mandatory detail field missing.")


def _calendar(text):
    match = CALENDAR.fullmatch(text.strip())
    if match is None:
        raise SourceError("MD unrecognized Romanian publication/deadline date.")
    d, month, year, hour, minute = match.groups()
    numeric = MONTHS.get(month.lower()[:3])
    if numeric is None:
        raise SourceError("MD unexpected Romanian month.")
    try:
        return datetime(int(year), numeric, int(d), int(hour), int(minute))
    except ValueError:
        raise SourceError("MD invalid normalized date.") from None


def _amount(text):
    text = text.replace("\xa0", " ").strip()
    if not re.fullmatch(r"[\d\s.,]+\s*MDL", text):
        raise SourceError("MD estimated price missing or extra fields.")
    raw = text[:-3].strip()
    if not NUMBER.fullmatch(raw):
        raise SourceError("MD estimate malformed.")
    # Integer thousands groups may be spaced; a comma denotes a decimal
    # only when followed by exactly two trailing digits.
    if re.search(r"[,.]\d{2}$", raw):
        main, fractional = raw[:-3], raw[-2:]
        digits = re.sub(r"[^\d]", "", main)
        value = float(digits + "." + fractional)
    else:
        value = float(re.sub(r"[^\d]", "", raw))
    if not math.isfinite(value) or not 0 <= value <= 1e18:
        raise SourceError("MD estimated price out of bounds.")
    return value


def parse_marketplace_detail(html, *, url):
    approved = _approved_href(url)
    if approved != url:
        raise SourceError("MD invalid public detail URL.")
    tender_id = DETAIL_PATH.fullmatch(urlsplit(url).path).group(1)
    tokens = _plain_tokens(html)
    # The marketplace renders the unique public procedure ID and linked title
    # near the top of each page, followed by the applicant information card.
    if tender_id not in tokens:
        raise SourceError("MD detail identity mismatch.")
    index = tokens.index(tender_id)
    title = next((t for t in tokens[index+1:index+8] if 7 <= len(t) <= 1000 and
                  "ați completat" not in t.casefold()), None)
    if title is None:
        raise SourceError("MD public detail title missing.")
    buyer = _after(tokens, "Denumirea", limit=3)
    if len(buyer) < 4 or len(buyer) > 2000:
        raise SourceError("MD public buyer missing.")
    publication = _calendar(_after(tokens, "Data publicării", limit=3))
    ocid = _after(tokens, "MTender ID", limit=3)
    if not OCID.fullmatch(ocid):
        raise SourceError("MD OCID not linked to detail.")
    expected = _after(tokens, "Valoarea estimată fără TVA", limit=3)
    amount = _amount(expected)
    # Full public tender page provides a dedicated proposal submission window,
    # distinct from the clarification period.
    proposals = tokens.index("Propunerea ofertelor") if "Propunerea ofertelor" in tokens else -1
    if proposals < 0:
        raise SourceError("MD bid deadline stage unavailable.")
    until_index = next((i for i in range(proposals+1, min(proposals+12, len(tokens)))
                        if tokens[i] == "până la"), None)
    if until_index is None or until_index+1 >= len(tokens):
        raise SourceError("MD proposal submission deadline not observed.")
    deadline_raw = tokens[until_index+1]
    # Some pages use dd.mm.yyyy in the stage, others Romanian short month.
    if re.fullmatch(r"\d{2}\.\d{2}\.20\d{2} \d{2}:\d{2}", deadline_raw):
        deadline = datetime.strptime(deadline_raw, "%d.%m.%Y %H:%M")
    else:
        deadline = _calendar(deadline_raw)
    if deadline < publication:
        raise SourceError("MD deadline precedes official publication.")
    notice = TenderNotice(
        source="md_achizitii",
        external_id=tender_id,
        tender_number=ocid,
        title=title,
        url=url,
        customer=buyer,
        published_at=publication.isoformat(),
        deadline=deadline.isoformat(),
        initial_price=amount,
        currency="MDL",
        summary="Public Moldova MTender platform procedure: " + ocid,
    )
    try:
        validate_notice(notice, "md_achizitii")
    except (TypeError, ValueError):
        raise SourceError("MD normalized notice rejected.") from None
    return notice


@dataclass(frozen=True)
class MoldovaAchizitiiSource:
    timeout: float = 12.0
    name: str = "md_achizitii"

    def __post_init__(self):
        if type(self.timeout) not in (float, int) or not math.isfinite(self.timeout) or not 0 < self.timeout <= 30:
            raise ValueError("MD marketplace timeout out of bounds.")

    async def fetch(self, limit=5):
        if _policy.get() is None:
            with bounded_fetch(FetchPolicy(frozenset({HOST}), 1+MAX_DETAILS, max_bytes=MAX_BODY)):
                return await self._fetch(limit)
        return await self._fetch(limit)

    async def _fetch(self, limit):
        if type(limit) is not int:
            raise SourceError("MD record limit must be integral.")
        count = max(1, min(limit, MAX_DETAILS))
        result = []
        try:
            async with source_client(timeout=self.timeout, trust_env=False, follow_redirects=False) as client:
                response = await client.get(INDEX_URL)
                response.raise_for_status()
                if "html" not in response.headers.get("content-type", "").lower():
                    raise SourceError("MD index was not HTML.")
                urls = discover_index(response.text)[:count]
                for url in urls:
                    detail = await client.get(url)
                    detail.raise_for_status()
                    if "html" not in detail.headers.get("content-type", "").lower():
                        raise SourceError("MD public detail was not HTML.")
                    result.append(parse_marketplace_detail(detail.text, url=url))
        except (httpx.HTTPError, ConnectorTransportError, OSError) as error:
            if transient_transport(error):
                raise SourceTransportError("MD public procurement temporarily unavailable.") from None
            raise SourceError("MD public procurement HTTPS failed.") from None
        if not result or len({r.identity for r in result}) != len(result):
            raise SourceError("MD empty or duplicate procurement records.")
        return result
