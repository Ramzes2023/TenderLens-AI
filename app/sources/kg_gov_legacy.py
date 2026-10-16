"""Official Kyrgyz legacy procurement notices from the verified server-rendered list.

The former homepage was JSF-only; this exact official listing endpoint returns
current, complete HTML tender rows with real detail links. Default-disabled.
No unapproved routes, proxy, cookies, API keys, pagination, or query terms.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
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

LIST_URL = "https://zakupki.gov.kg/popp/view/order/list.xhtml"
DETAIL_BASE = "https://zakupki.gov.kg/popp/view/order/view.xhtml?id="
HOST = "zakupki.gov.kg"
MAX_BYTES = 1024 * 1024
DATE = re.compile(r"^\d{2}\.\d{2}\.20\d{2} \d{2}:\d{2}$")
IDENTIFIER = re.compile(r"^2\d{14}$")
DETAIL_LINK = re.compile(r"^view\.xhtml\?id=([1-9]\d{6,12})$")
AMOUNT = re.compile(r"^[0-9][0-9 ,.\u00a0]{0,25}$")


class _Listing(_Tables):
    """Official HTML tables with whitespace-sensitive nested div labels."""

    def handle_starttag(self, tag, attrs):
        super().handle_starttag(tag, attrs)
        if tag in {"div", "br", "span"} and self.cell is not None:
            self.cell.append(" ")

    def handle_endtag(self, tag):
        if tag in {"div", "span"} and self.cell is not None:
            self.cell.append(" ")
        super().handle_endtag(tag)


def _value(cell, label):
    if type(cell) is not str:
        raise SourceError("KG malformed field.")
    data = " ".join(cell.split())
    # The official JSF source sometimes omits a space before an untranslated
    # method label (e.g. procurement method???REQUEST_FOR_QUOTATION???).
    if not data.casefold().startswith(label.casefold()):
        raise SourceError("KG official listing field labels changed.")
    remainder = data[len(label):]
    if not remainder or not (remainder[0].isspace() or remainder.startswith("???")):
        raise SourceError("KG official listing field boundary changed.")
    value = remainder.strip()
    if not value or len(value) > 2000:
        raise SourceError("KG incomplete or oversized official field.")
    return value


def _money(value):
    if not AMOUNT.fullmatch(value):
        raise SourceError("KG unrecognized planned amount.")
    normalized = value.replace(",", "").replace(" ", "").replace("\u00a0", "")
    if normalized.count(".") > 1:
        raise SourceError("KG invalid official planned amount.")
    try:
        amount = float(normalized)
    except ValueError:
        raise SourceError("KG invalid amount.") from None
    if not math.isfinite(amount) or amount < 0 or amount > 1e18:
        raise SourceError("KG amount out of range.")
    return amount


def _date(value):
    if not DATE.fullmatch(value):
        raise SourceError("KG unrecognized official publication/deadline date.")
    return datetime.strptime(value, "%d.%m.%Y %H:%M")


def parse_kg_legacy_list(html: str):
    if not isinstance(html, str) or len(html.encode("utf-8")) > MAX_BYTES:
        raise SourceError("KG invalid or oversized official listing.")
    parser = _Listing()
    parser.feed(html)
    if parser.table is not None:
        raise SourceError("KG incomplete HTML table.")
    table_candidates = []
    for table in parser.tables:
        if not table or len(table) > 101:
            continue
        rows = [row for row in table if len(row) == 11 and row and
                re.match(r"^number\s+2\d{14}$", row[0], re.I)]
        if rows:
            table_candidates.append((table, rows))
    if len(table_candidates) != 1:
        raise SourceError("KG public tender table missing or ambiguous.")
    table, data_rows = table_candidates[0]
    if not 1 <= len(data_rows) <= 20:
        raise SourceError("KG official listing row count changed.")
    out = {}
    for row in data_rows:
        number = _value(row[0], "number")
        if not IDENTIFIER.fullmatch(number):
            raise SourceError("KG unrecognized notice number.")
        buyer = _value(row[1], "Name of company")
        kind = _value(row[2], "Type of procurement")
        title = _value(row[3], "purchase Name")
        method = _value(row[5], "procurement method")
        amount = _money(_value(row[6], "Planned amount"))
        published = _date(_value(row[7], "Date published"))
        deadline = _date(_value(row[8], "Bids Submission Deadline"))
        if deadline < published or len(buyer) < 4 or len(title) < 5 or len(kind) > 120 or len(method) > 160:
            raise SourceError("KG incomplete public notice fields.")
        links = parser.links.get(id(row), [])
        match = DETAIL_LINK.fullmatch(links[0][1]) if len(links) == 1 and links[0][0] == 4 else None
        if match is None:
            raise SourceError("KG unverified official detail link.")
        detail_url = DETAIL_BASE + match.group(1)
        if urlsplit(detail_url).hostname != HOST:
            raise SourceError("KG unapproved detail host.")
        notice = TenderNotice(
            source="kg_gov_legacy",
            external_id=number,
            tender_number=number,
            title=title,
            url=detail_url,
            customer=buyer,
            published_at=published.isoformat(),
            deadline=deadline.isoformat(),
            initial_price=amount,
            currency="KGS",
            summary=f"Procurement type: {kind}; Method: {method}",
        )
        try:
            validate_notice(notice, "kg_gov_legacy")
        except (ValueError, TypeError):
            raise SourceError("KG invalid normalized official tender.") from None
        if number in out:
            raise SourceError("KG duplicate notice number.")
        out[number] = notice
    return list(out.values())


@dataclass(frozen=True)
class KyrgyzstanGovLegacySource:
    timeout: float = 12.0
    name: str = "kg_gov_legacy"

    def __post_init__(self):
        if type(self.timeout) not in (float, int) or not math.isfinite(self.timeout) or not 0 < self.timeout <= 30:
            raise ValueError("KG timeout must be between 0 and 30 seconds.")

    async def fetch(self, limit: int = 20):
        if _policy.get() is None:
            with bounded_fetch(FetchPolicy(frozenset({HOST}), 1, max_bytes=MAX_BYTES)):
                return await self._fetch(limit)
        return await self._fetch(limit)

    async def _fetch(self, limit):
        if type(limit) is not int:
            raise SourceError("KG invalid record limit.")
        requested = max(1, min(limit, 20))
        try:
            async with source_client(timeout=self.timeout, trust_env=False, follow_redirects=False) as client:
                response = await client.get(LIST_URL)
                response.raise_for_status()
                if "text/html" not in response.headers.get("content-type", "").lower():
                    raise SourceError("KG official list was not HTML.")
                return parse_kg_legacy_list(response.text)[:requested]
        except (httpx.HTTPError, ConnectorTransportError, OSError) as error:
            if transient_transport(error):
                raise SourceTransportError("KG official HTTPS temporarily unavailable.") from None
            raise SourceError("KG official HTTPS retrieval failed.") from None
