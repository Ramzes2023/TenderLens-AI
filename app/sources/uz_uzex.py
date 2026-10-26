"""Uzbekistan official UzEx open tender / selection adapter, disabled by default.

All discovery comes from the official public TradeList HTTPS API.
Only bounded public metadata are normalized; no credentials or tenant terms.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import zip_longest
import math
import re

import httpx

from .eis_rss import SourceError
from .http import ConnectorTransportError, FetchPolicy, _policy, bounded_fetch, source_client
from .models import TenderNotice
from .opportunities import validate_notice
from .transport_errors import SourceTransportError, transient_transport

API_URL = "https://apietender.uzex.uz/api/common/TradeList"
DETAIL_PREFIX = "https://etender.uzex.uz/lot/"
HOST = "apietender.uzex.uz"
MAX_BODY = 512 * 1024
PER_TYPE = 20


def _nonempty(row, key):
    value = row.get(key)
    return value.strip() if type(value) is str and value.strip() else None


def _date(value):
    if type(value) is not str or len(value) > 80 or not re.match(r"^20\d\d-\d\d-\d\d", value):
        raise SourceError("UzEx invalid observed notice date.")
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise SourceError("UzEx invalid observed notice date.") from None


def parse_uzex_tradelist(data, *, type_id: int, allow_incomplete: bool = False):
    """Normalize verified official rows; optionally exclude bounded blank titles/buyers.

    A source-published incomplete row is NOT a tender. All IDs, identities,
    amounts, currencies, dates and remaining rows still fail closed. Direct
    consumers and parser contract tests use strict mode by default.
    """
    if type_id not in (1, 2) or type(data) is not list or not 0 < len(data) <= PER_TYPE:
        raise SourceError("UzEx changed public list shape.")
    if type(allow_incomplete) is not bool:
        raise SourceError("UzEx invalid missing-row policy.")
    result = {}
    seen_official_ids = set()
    incomplete = 0
    for row in data:
        if type(row) is not dict:
            raise SourceError("UzEx malformed public notice row.")
        identifier = row.get("id")
        if (type(identifier) is not int or not 100 <= identifier <= 999999999999
                or row.get("type_id") != type_id):
            raise SourceError("UzEx invalid official notice identity.")
        # Even excluded incomplete rows must have valid native identities and
        # cannot repeat another record. An attacker cannot smuggle duplicates.
        if identifier in seen_official_ids:
            raise SourceError("UzEx duplicate official lot in response.")
        seen_official_ids.add(identifier)
        title = _nonempty(row, "name")
        customer = _nonempty(row, "seller_name")
        if not title or not customer or len(title) < 8 or len(customer) < 4:
            # Live official TypeId=1 contained 19 valid rows plus one native
            # row with missing title/buyer. Persist only real verified records.
            # More than two per feed means probable upstream schema change.
            if allow_incomplete:
                incomplete += 1
                if incomplete > 2:
                    raise SourceError("UzEx too many incomplete official rows.")
                continue
            raise SourceError("UzEx missing procurement title or organization.")
        start = _date(row.get("start_date"))
        end = _date(row.get("end_date"))
        if (start.tzinfo is None) != (end.tzinfo is None) or end < start:
            raise SourceError("UzEx inconsistent official date interval.")
        price = row.get("cost")
        if type(price) not in (int, float) or not math.isfinite(price) or not 0 <= price <= 1e18:
            raise SourceError("UzEx invalid procurement amount.")
        currency = _nonempty(row, "currency_codeabc")
        if currency is not None and not re.fullmatch(r"[A-Z]{3}", currency):
            raise SourceError("UzEx invalid ISO currency.")
        display = _nonempty(row, "display_no")
        if display is not None and (len(display) > 500 or not re.fullmatch(r"[0-9]{6,30}", display)):
            raise SourceError("UzEx invalid official lot display number.")
        notice = TenderNotice(
            source="uz_uzex",
            external_id=f"{type_id}-{identifier}",
            tender_number=display,
            title=title,
            url=DETAIL_PREFIX + str(identifier),
            customer=customer,
            published_at=start.isoformat(),
            deadline=end.isoformat(),
            currency=currency,
            initial_price=float(price),
            summary="Official UzEx public " + ("tender" if type_id == 1 else "best-offer selection"),
        )
        try:
            validate_notice(notice, "uz_uzex")
        except ValueError:
            raise SourceError("UzEx invalid normalized public notice.") from None
        if notice.external_id in result:
            if result[notice.external_id] != notice:
                raise SourceError("UzEx conflicting duplicate lot.")
            raise SourceError("UzEx duplicate official lot in response.")
        result[notice.external_id] = notice
    if not result:
        raise SourceError("UzEx no complete original tender rows.")
    return list(result.values())


def _uzex_public_rows(payload):
    """Official public TradeList may return a direct list or a data/items list.

    Never interpret an opaque mapping, an error response, or an ID-only record
    as an actual tender. Only complete first-party rows can survive the
    independent per-notice validator.
    """
    if type(payload) is list:
        return payload
    if type(payload) is dict:
        if payload.get("success") is False or payload.get("ok") is False:
            raise SourceError("UzEx public API reported failure.")
        for field in ("data", "items"):
            if type(payload.get(field)) is list:
                return payload[field]
    raise SourceError("UzEx changed public list envelope.")


def parse_uzex_current_batch(data, *, type_id: int):
    """Keep independently valid official current rows; no ID-only acceptance.

    TradeList sometimes includes incomplete individual entries. Reject those
    entries without losing other strictly verified original tenders. The
    entire batch still fails when no complete original remains, when the
    official list shape changes, or when a duplicate original ID appears.
    """
    if type_id not in (1, 2) or type(data) is not list or not 0 < len(data) <= PER_TYPE:
        raise SourceError("UzEx changed public list shape.")
    accepted = []
    seen = set()
    for row in data:
        try:
            notices = parse_uzex_tradelist([row], type_id=type_id)
        except SourceError:
            # A bad individual row is not a verified original; skipping
            # does not turn its synthetic/unknown fields into tender data.
            continue
        item = notices[0]
        if item.external_id in seen:
            raise SourceError("UzEx duplicated official original in current batch.")
        seen.add(item.external_id)
        accepted.append(item)
    if not accepted:
        raise SourceError("UzEx no independently verified tender rows in current batch.")
    return accepted


@dataclass(frozen=True)
class UzbekistanUzexSource:
    timeout: float = 12.0
    name: str = "uz_uzex"

    def __post_init__(self):
        if type(self.timeout) not in (float, int) or not math.isfinite(self.timeout) or not 0 < self.timeout <= 30:
            raise ValueError("UzEx timeout must be between 0 and 30 seconds.")

    async def fetch(self, limit: int = 20):
        if _policy.get() is None:
            with bounded_fetch(FetchPolicy(frozenset({HOST}), 2, max_bytes=MAX_BODY)):
                return await self._fetch(limit)
        return await self._fetch(limit)

    async def _fetch(self, limit):
        if type(limit) is not int:
            raise SourceError("UzEx invalid record limit.")
        requested = max(1, min(limit, 20))
        series = []
        try:
            async with source_client(timeout=self.timeout, trust_env=False, follow_redirects=False) as client:
                for type_id in (1, 2):
                    response = await client.post(
                        API_URL,
                        json={"TypeId": type_id, "From": 1, "To": PER_TYPE, "System_Id": 0},
                        headers={"Accept": "application/json",
                                 "User-Agent": "VALYQON-public-procurement-adapter/1.0"},
                    )
                    response.raise_for_status()
                    if "json" not in response.headers.get("content-type", "").lower():
                        raise SourceError("UzEx official response was not JSON.")
                    if len(response.content) > MAX_BODY:
                        raise SourceError("UzEx oversized official response.")
                    series.append(parse_uzex_tradelist(
                        response.json(), type_id=type_id, allow_incomplete=True,
                    ))
        except (httpx.HTTPError, ConnectorTransportError, OSError) as error:
            if transient_transport(error):
                raise SourceTransportError("UzEx official HTTPS temporarily unavailable.") from None
            raise SourceError("UzEx official HTTPS acquisition failed.") from None
        except (ValueError, UnicodeError):
            raise SourceError("UzEx invalid official JSON.") from None
        output = []
        # Bound result size while representing both official open tenders and
        # best-offer selections, without fetching from hidden/private routes.
        # The two official categories need not contain the same number of
        # complete rows: a source-owned row with a missing buyer/title may be
        # rejected within its own category. zip(*series) silently truncated
        # every remaining valid notice in the longer category. Interleave
        # using zip_longest so no independently validated original is lost.
        # No synthetic placeholder is ever accepted as a procurement notice.
        for pair in zip_longest(*series):
            output.extend(notice for notice in pair if notice is not None)
            if len(output) >= requested:
                return output[:requested]
        return output[:requested]
