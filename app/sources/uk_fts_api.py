"""Official UK Find a Tender OCDS API adapter."""
from __future__ import annotations

import html
import re
import math
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from .http import source_client

from .eis_rss import SourceError
from .models import TenderNotice
from .enrichment import enrichment
from .international import request_json, diagnostic, source_date, retryable


UK_FTS_SEARCH_URL = (
    "https://www.find-tender.service.gov.uk/"
    "api/1.0/ocdsReleasePackages"
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _release_date(value: Any) -> datetime:
    # Offsets are mandatory: never silently interpret local time as UTC.
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise SourceError('UK Find a Tender returned an invalid offset date.') from None


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return None

    text = html.unescape(str(value))
    text = _HTML_TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()

    return text or None


def _first_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None

    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    except (TypeError, ValueError):
        return None


def _procurement_url(ocid: str) -> str:
    encoded = quote(ocid, safe="-")
    return (
        "https://www.find-tender.service.gov.uk/"
        f"procurement/{encoded}"
    )


def _regions(tender: dict[str, Any]) -> str | None:
    items = tender.get("items")

    if not isinstance(items, list):
        return None

    result: list[str] = []
    seen: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            continue

        addresses = item.get("deliveryAddresses")

        if isinstance(addresses, list):
            for address in addresses:
                if not isinstance(address, dict):
                    continue

                region = _clean_text(address.get("region"))

                if not region:
                    continue

                key = region.casefold()

                if key in seen:
                    continue

                seen.add(key)
                result.append(region)

    return ", ".join(result) if result else None


def _buyer_name(release: dict[str, Any]) -> str | None:
    buyer = release.get("buyer")

    if isinstance(buyer, dict):
        name = _clean_text(buyer.get("name"))

        if name:
            return name

    return None


def parse_uk_fts_response(
    payload: dict[str, Any],
    *,
    source_name: str = "uk_fts",
    now: datetime | None = None,
) -> list[TenderNotice]:
    """Normalize a Find a Tender OCDS release package."""

    raw_releases = payload.get("releases")

    if not isinstance(raw_releases, list):
        raise SourceError(
            "UK Find a Tender returned an invalid releases response."
        )

    notices: list[TenderNotice] = []

    # A release is an update, not a new opportunity. Keep the latest supplied
    # release per process BEFORE filtering, so cancellation supersedes tender.
    latest: dict[str, dict[str, Any]] = {}
    for release in raw_releases:
        if not isinstance(release, dict) or not _clean_text(release.get('ocid')):
            raise SourceError('UK Find a Tender returned an invalid release identity.')
        ocid = _clean_text(release['ocid'])
        date = _release_date(release.get('date'))
        previous = latest.get(ocid)
        if previous is None or date >= _release_date(previous.get('date')):
            latest[ocid] = release

    for release in latest.values():
        if not isinstance(release, dict):
            raise SourceError(
                "UK Find a Tender returned an invalid release object."
            )

        release_id = _clean_text(release.get("id"))
        ocid = _clean_text(release.get("ocid"))

        if not release_id:
            raise SourceError(
                "UK Find a Tender returned a release without id."
            )

        if not ocid:
            raise SourceError(
                "UK Find a Tender returned a release without ocid."
            )

        tender = release.get("tender")

        if not isinstance(tender, dict):
            continue  # Non-tender stages are legitimate OCDS releases.

        tags = release.get('tag')
        if not isinstance(tags, list) or not set(tags) & {'tender', 'tenderUpdate', 'tenderAmendment'}:
            continue
        if tender.get('status') != 'active':
            continue
        period = tender.get('tenderPeriod')
        end = period.get('endDate') if isinstance(period, dict) else None
        if end and _release_date(end) <= (now or datetime.now(timezone.utc)):
            continue

        tender_id = (
            _clean_text(tender.get("id"))
            or release_id
        )

        title = (
            _clean_text(tender.get("title"))
        )
        if not title:
            raise SourceError('UK Find a Tender returned a tender without title.')

        value = tender.get("value")
        initial_price = None
        currency = None

        if isinstance(value, dict):
            initial_price = _first_float(
                value.get("amount")
            )
            currency = _clean_text(
                value.get("currency")
            )

        tender_period = tender.get("tenderPeriod")
        deadline = None

        if isinstance(tender_period, dict):
            deadline = source_date(_clean_text(tender_period.get('endDate')))

        summary = (
            _clean_text(tender.get("description"))
            or _clean_text(release.get("description"))
        )

        notices.append(
            TenderNotice(
                source=source_name,
                external_id=ocid[:500],
                title=title[:1000],
                url=(f'https://www.find-tender.service.gov.uk/Notice/{release_id}'
                     if re.fullmatch(r'\d{6}-\d{4}', release_id) else _procurement_url(ocid))[:2000],
                published_at=source_date(_clean_text(release.get('date'))),
                tender_number=tender_id[:500],
                customer=_buyer_name(release),
                initial_price=initial_price,
                currency=currency,
                deadline=deadline,
                region=_regions(tender),
                summary=(
                    summary[:4000]
                    if summary
                    else None
                ),
                enrichment=enrichment(
                    source_name, ocid[:500],
                    public_metadata={'attribution': 'UK Find a Tender / Open Government Licence',
                                     'raw_release_id': release_id, 'raw_ocid': ocid,
                                     'original_language': release.get('language'),
                                     'deadline_state': 'reported' if deadline else 'not_supplied'},
                    locations=[
                        [{'path': f'tender.items[{i}].deliveryAddresses[{j}].country', 'value': address['country']}]
                        for i, item in enumerate(tender.get('items', []) or []) if isinstance(item, dict)
                        for j, address in enumerate(item.get('deliveryAddresses', []) or [])
                        if isinstance(address, dict) and isinstance(address.get('country'), str)
                    ],
                    classifications=[
                        {'scheme': classification.get('scheme'), 'code': classification.get('id'),
                         'path': f'tender.items[{i}].classification', 'role': 'primary'}
                        for i, item in enumerate(tender.get('items', []) or []) if isinstance(item, dict)
                        for classification in [item.get('classification')]
                        if isinstance(classification, dict)
                    ],
                    dates={
                        'publication': {'path': 'date', 'value': release.get('date'), 'semantics': 'release_date'},
                        'deadline': {'path': 'tender.tenderPeriod.endDate',
                                     'value': tender_period.get('endDate') if isinstance(tender_period, dict) else None},
                    },
                ),
            )
        )

    return notices


@dataclass(frozen=True)
class UkFindTenderApiSource:
    """Published UK procurement notices from Find a Tender."""

    timeout: float = 30.0
    name: str = "uk_fts"

    def __post_init__(self) -> None:
        if not math.isfinite(self.timeout) or self.timeout <= 0 or self.timeout > 120:
            raise ValueError(
                "timeout must be between 0 and 120 seconds."
            )

    async def fetch(
        self,
        limit: int = 20,
    ) -> list[TenderNotice]:
        limit = max(1, min(int(limit), 100))

        params = {
            "stages": "tender",
            "limit": str(limit),
            # Bound the public feed to recent publications, rather than the
            # oldest historical releases. Extract trusted cursors only.
            "updatedFrom": (datetime.now(timezone.utc) - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S'),
            "updatedTo": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'),
        }

        try:
            async with source_client(
                timeout=self.timeout,
                follow_redirects=False,
                trust_env=False,
                headers={
                    "Accept": "application/json",
                    "User-Agent": (
                        "VALYQON-AI (+procurement-source)"
                    ),
                },
            ) as client:
                releases = []
                cursors = set()
                for page in range(2):
                    payload = await request_json(client, 'GET', UK_FTS_SEARCH_URL,
                                                 hosts={'www.find-tender.service.gov.uk'}, params=params)
                    if not isinstance(payload.get('releases'), list):
                        raise SourceError('UK Find a Tender returned an invalid releases response.')
                    releases.extend(payload['releases'])
                    links = payload.get('links', {})
                    next_url = links.get('next') if isinstance(links, dict) else None
                    if not next_url or not payload['releases']:
                        break
                    # Extract only a cursor. Never request a feed-supplied URL.
                    from urllib.parse import urlsplit, parse_qs
                    from .international import official_url
                    official_url(next_url, {'www.find-tender.service.gov.uk'})
                    parts = urlsplit(next_url)
                    if parts.path != '/api/1.0/ocdsReleasePackages':
                        raise SourceError('UK Find a Tender returned an invalid pagination path.')
                    cursor = parse_qs(parts.query).get('cursor', [None])[0]
                    if not cursor or len(cursor) > 2000 or cursor in cursors:
                        raise SourceError('UK Find a Tender returned an invalid pagination cursor.')
                    cursors.add(cursor)
                    params['cursor'] = cursor
                payload = {'releases': releases}

        except SourceError:
            raise
        except (httpx.HTTPError, OSError, ValueError) as error:
            failure = SourceError('Unable to fetch UK Find a Tender notices. ' + diagnostic(error))
            failure.retryable = retryable(error)
            raise failure from None

        if not isinstance(payload, dict):
            raise SourceError(
                "UK Find a Tender returned an invalid JSON object."
            )

        return parse_uk_fts_response(
            payload,
            source_name=self.name,
        )[:limit]


__all__ = [
    "UK_FTS_SEARCH_URL",
    "UkFindTenderApiSource",
    "parse_uk_fts_response",
]
