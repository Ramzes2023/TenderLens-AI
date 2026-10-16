"""Bounded first-page adapter for the verified official Tajikistan capture.

No detail enrichment or pagination contract is claimed. Activation is disabled.
"""
from dataclasses import dataclass
from datetime import datetime
import math
import re

import httpx

from .am_armeps import _Tables
from .eis_rss import SourceError
from .transport_errors import SourceTransportError, transient_transport
from .http import ConnectorTransportError, FetchPolicy, _policy, bounded_fetch, source_client
from .models import TenderNotice
from .opportunities import validate_notice

LISTING_URL = "https://eprocurement.gov.tj/ru/searchanno"
ORIGIN = "https://eprocurement.gov.tj"
MAX_BYTES = 1024 * 1024
HEADERS = ["№", "Организатор", "Закупающая организация", "Название объявления",
           "Метод закупки", "Вид предмета закупки", "Дата начала приема заявок",
           "Дата окончания приема заявок", "Кол-во лотов", "Статус"]


class _ListingTables(_Tables):
    def handle_starttag(self, tag, attrs):
        if self.hidden:
            if tag in {"script", "style"}:
                self.hidden += 1
            return
        super().handle_starttag(tag, attrs)
        if tag in {"div", "br"} and self.cell is not None:
            self.cell.append(" ")

    def handle_endtag(self, tag):
        if self.hidden and tag not in {"script", "style"}:
            return
        if tag == "div" and self.cell is not None:
            self.cell.append(" ")
        super().handle_endtag(tag)


def parse_tj_listing(html, *, listing_url=LISTING_URL):
    if listing_url != LISTING_URL:
        raise SourceError("TJ unapproved listing URL.")
    if not isinstance(html, str) or len(html.encode("utf-8")) > MAX_BYTES:
        raise SourceError("TJ invalid or oversized HTML.")
    parser = _ListingTables()
    parser.feed(html)
    tables = [t for t in parser.tables if t and t[0] == HEADERS]
    if len(tables) != 1 or parser.table is not None or not 1 < len(tables[0]) <= 1001:
        raise SourceError("TJ listing structure unverified or changed.")
    result = {}
    for row in tables[0][1:]:
        if len(row) != 10 or not all(row):
            raise SourceError("TJ incomplete listing row.")
        identifier, organizer, customer, title, method, kind, start, end, lots, status = row
        if not re.fullmatch(r"[1-9][0-9]{0,29}", identifier) or not re.fullmatch(r"[0-9]{1,6}", lots):
            raise SourceError("TJ invalid ID or lot count.")
        links = parser.links[id(row)]
        match = re.fullmatch(r"(?:https://eprocurement\.gov\.tj)?/ru/announce/index/([1-9][0-9]{0,29})", links[0][1]) if len(links) == 1 and links[0][0] == 3 else None
        if match is None:
            raise SourceError("TJ unsafe or mismatched detail URL.")
        detail_id = match.group(1)
        relative = f"/ru/announce/index/{detail_id}"
        try:
            if not all(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}", d) for d in (start, end)):
                raise ValueError()
            start_date, end_date = [datetime.strptime(d, "%Y-%m-%d %H:%M:%S") for d in (start, end)]
            if end_date < start_date:
                raise ValueError()
            notice = TenderNotice(source="tj_eprocurement", external_id=detail_id, tender_number=identifier,
                title=title, url=ORIGIN + relative, customer=customer,
                deadline=end_date.isoformat(),
                summary=f"Organizer: {organizer}; Method: {method}; Kind: {kind}; "
                        f"Application start: {start_date.isoformat()}; Lot count: {lots}; Status: {status}")
            validate_notice(notice, "tj_eprocurement")
        except ValueError:
            raise SourceError("TJ invalid normalized public fields.") from None
        previous = result.get(notice.identity)
        if previous is not None and previous != notice:
            raise SourceError("TJ conflicting duplicate ID.")
        result[notice.identity] = notice
    return list(result.values())


@dataclass(frozen=True)
class TajikistanEprocurementSource:
    timeout: float = 10.0
    name: str = "tj_eprocurement"

    def __post_init__(self):
        if type(self.timeout) not in (int, float) or not math.isfinite(self.timeout) or not 0 < self.timeout <= 30:
            raise ValueError("timeout must be between 0 and 30 seconds.")

    async def fetch(self, limit=20):
        if _policy.get() is None:
            with bounded_fetch(FetchPolicy(frozenset({"eprocurement.gov.tj"}), 1, max_bytes=MAX_BYTES)):
                return await self._fetch(limit)
        return await self._fetch(limit)

    async def _fetch(self, limit):
        requested = max(1, min(int(limit), 100))
        try:
            async with source_client(timeout=self.timeout, trust_env=False, follow_redirects=False) as client:
                response = await client.get(LISTING_URL)
                response.raise_for_status()
                if "text/html" not in response.headers.get("content-type", "").lower():
                    raise SourceError("TJ response is not HTML.")
                return parse_tj_listing(response.text)[:requested]
        except (httpx.HTTPError, ConnectorTransportError, OSError) as error:
            if transient_transport(error):
                raise SourceTransportError("Temporary source transport failure.") from None
            raise SourceError("TJ bounded HTTPS retrieval failed.") from None
