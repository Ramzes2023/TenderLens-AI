"""Government of Kazakhstan publicly accessible HTML tender announcements.

Complements, does NOT replace the separately credentialed KZ Goszakup API.
Observed official data: old.goszakup.gov.kz /ru/search/announce.
Default disabled. Real HTTPS -> leased-worker -> disposable SQLite is required.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import ssl
import math
import re
from urllib.parse import urlsplit

import httpx

from .am_armeps import _Tables
from .eis_rss import SourceError
from .http import ConnectorTransportError, FetchPolicy, _policy, bounded_fetch, source_client
from .models import TenderNotice
from .opportunities import validate_notice
from .transport_errors import SourceTransportError, transient_transport

HOST = "old.goszakup.gov.kz"
INDEX_URL = "https://old.goszakup.gov.kz/ru/search/announce?count_record=50&page=1"
DETAIL_PREFIX = "https://old.goszakup.gov.kz/ru/announce/index/"
MAX_BODY = 1024 * 1024
DATE = re.compile(r"20\d{2}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?")
IDENTIFIER = re.compile(r"\b([1-9]\d{6,11})-[1-9]\d*\b")
AMOUNT = re.compile(r"^(?:\d{1,3}(?:[ \u00a0]\d{3})+|\d{1,15})(?:[.,]\d{2})?$")
HEADERS = ("№", "Наименование объявления", "Способ", "Начало приема заявок",
           "Окончание приема заявок", "Сумма, тг.", "Статус")


def _date(value):
    if type(value) is not str or len(value) > 120:
        raise SourceError("KZ malformed procurement date.")
    found = DATE.search(value)
    if found is None:
        raise SourceError("KZ start/end procurement date missing.")
    # Exact-match date after whitespace normalization: partial dates forbidden.
    text = " ".join(value.split())
    if DATE.fullmatch(text) is None:
        raise SourceError("KZ unexpected official date format.")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise SourceError("KZ invalid procurement timestamp.")


def _amount(value):
    text = " ".join(value.replace("\u00a0", " ").split())
    if not AMOUNT.fullmatch(text):
        raise SourceError("KZ invalid publicly advertised tender amount.")
    amount = float(text.replace(" ", "").replace(",", "."))
    if not math.isfinite(amount) or not 0 <= amount <= 1e18:
        raise SourceError("KZ published amount invalid.")
    return amount


def _detail_link(links, announcement_id):
    matches = []
    for column, raw in links:
        if column != 0:
            continue
        parsed = urlsplit(raw)
        if (parsed.scheme not in ("", "https") or parsed.hostname not in (None, HOST)
                or parsed.port not in (None, 443) or parsed.username or parsed.password
                or parsed.query or parsed.fragment):
            continue
        if parsed.path == "/ru/announce/index/" + announcement_id:
            matches.append(DETAIL_PREFIX + announcement_id)
    if len(matches) != 1:
        raise SourceError("KZ detail link not independently verified.")
    return matches[0]


def parse_kz_public_html(html):
    if type(html) is not str or len(html.encode("utf-8")) > MAX_BODY:
        raise SourceError("KZ invalid or oversized official listing.")
    parser = _Tables()
    parser.feed(html)
    if parser.table is not None:
        raise SourceError("KZ unclosed official listing table.")
    tables = [t for t in parser.tables if t and
              tuple(t[0]) == HEADERS and 5 <= len(t) - 1 <= 50]
    if len(tables) != 1:
        raise SourceError("KZ 7-column official procurement table missing/changed.")
    table = tables[0]
    result = {}
    for row in table[1:]:
        if len(row) != 7 or not all(row):
            raise SourceError("KZ incomplete official listing row.")
        first, buyer_title, method, opened, deadline, amount, status = row
        match = IDENTIFIER.search(first)
        if not match:
            raise SourceError("KZ invalid procurement announcement identifier.")
        announce_id = match.group(1)
        info = re.fullmatch(r"(.{7,1000}?)\s*Организатор:\s*(.{4,2000})", buyer_title, re.S)
        if not info:
            raise SourceError("KZ title / organizer public fields missing.")
        title, buyer = info.group(1).strip(), info.group(2).strip()
        start_time, end_time = _date(opened), _date(deadline)
        if start_time > end_time or len(method) > 300 or len(status) > 250:
            raise SourceError("KZ inconsistent tender period/status.")
        detail = _detail_link(parser.links[id(row)], announce_id)
        notice = TenderNotice(
            source="kz_gov_html", external_id=announce_id,
            tender_number=first.strip(), title=title, url=detail,
            customer=buyer, deadline=end_time.isoformat(),
            initial_price=_amount(amount), currency="KZT",
            summary=f"Method: {method}; Application start: {start_time.isoformat()}; Status: {status}",
        )
        try:
            validate_notice(notice, "kz_gov_html")
        except (ValueError, TypeError, OverflowError):
            raise SourceError("KZ normalized public notice failed validation.") from None
        if announce_id in result:
            raise SourceError("KZ conflicting/duplicate public tender identifier.")
        result[announce_id] = notice
    return list(result.values())


@dataclass(frozen=True)
class KazakhstanGovHtmlSource:
    timeout: float = 15.0
    name: str = "kz_gov_html"

    def __post_init__(self):
        if type(self.timeout) not in (float, int) or not math.isfinite(self.timeout) or not 0 < self.timeout <= 30:
            raise ValueError("KZ public source timeout must be finite and bounded.")

    async def fetch(self, limit=20):
        if _policy.get() is None:
            with bounded_fetch(FetchPolicy(frozenset({HOST}), 1, max_bytes=MAX_BODY)):
                return await self._fetch(limit)
        return await self._fetch(limit)

    async def _fetch(self, limit):
        if type(limit) is not int:
            raise SourceError("KZ public source limit must be integer.")
        requested = max(1, min(limit, 20))
        try:
            # Match the already verified GitHub-hosted government HTTPS probe:
            # system CA trust + transparent procurement-verifier UA, never TLS bypass.
            async with source_client(timeout=self.timeout, trust_env=False,
                                     follow_redirects=False,
                                     verify=ssl.create_default_context()) as client:
                response = await client.get(
                    INDEX_URL,
                    headers={"User-Agent": "VALYQON-cis-official-public-readonly/1.0",
                             "Accept": "text/html"},
                )
                response.raise_for_status()
                if "text/html" not in response.headers.get("content-type", "").lower():
                    raise SourceError("KZ government listing not HTML.")
                return parse_kz_public_html(response.text)[:requested]
        except (httpx.HTTPError, ConnectorTransportError, OSError) as error:
            if transient_transport(error):
                raise SourceTransportError("KZ public government HTML temporarily unavailable.") from None
            raise SourceError("KZ government bounded HTTPS retrieval failed: " + type(error).__name__) from None
