"""Official TED Search API v3 procurement source adapter."""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from .http import source_client

from .eis_rss import SourceError
from .models import TenderNotice
from .enrichment import enrichment
from .international import source_date, closed, request_json, diagnostic, retryable


TED_SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"

TED_FIELDS = (
    "publication-number",
    "notice-title",
    "buyer-name",
    "publication-date",
    "deadline-receipt-tender-date-lot",
    "total-value",
    "total-value-cur",
    "place-of-performance",
    "description-proc",
    "notice-type",
)


def _text_values(value: Any) -> list[str]:
    """Flatten TED scalar/list/multilingual response values into text."""

    if value is None:
        return []

    if isinstance(value, str):
        cleaned = " ".join(value.split())
        return [cleaned] if cleaned else []

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [str(value)]

    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_text_values(item))
        return result

    if isinstance(value, dict):
        result: list[str] = []

        # Prefer English/value-like fields when TED returns multilingual data.
        preferred = (
            "eng",
            "en",
            "value",
            "text",
            "label",
        )

        consumed: set[str] = set()

        for key in preferred:
            if key in value:
                consumed.add(key)
                result.extend(_text_values(value[key]))

        for key, item in value.items():
            if key in consumed:
                continue
            result.extend(_text_values(item))

        return result

    return []


def _first_text(value: Any) -> str | None:
    values = _text_values(value)
    return values[0] if values else None


def _unique_join(value: Any) -> str | None:
    result: list[str] = []
    seen: set[str] = set()

    for item in _text_values(value):
        key = item.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return ", ".join(result) if result else None


def _first_float(value: Any) -> float | None:
    for item in _text_values(value):
        normalized = item.replace("\u00a0", "").replace(" ", "")

        # TED numeric values are normally JSON numbers or decimal strings.
        if "," in normalized and "." not in normalized:
            normalized = normalized.replace(",", ".")
        else:
            normalized = normalized.replace(",", "")

        try:
            number = float(normalized)
            return number if math.isfinite(number) and number >= 0 else None
        except ValueError:
            continue

    return None


def _notice_url(publication_number: str) -> str:
    encoded = quote(publication_number, safe="-")
    return f"https://ted.europa.eu/en/notice/-/detail/{encoded}"


def parse_ted_search_response(
    payload: dict[str, Any],
    *,
    source_name: str = "ted",
    now: datetime | None = None,
) -> list[TenderNotice]:
    """Normalize one TED Search API response into VALYQON notices."""

    raw_notices = payload.get("notices")

    if not isinstance(raw_notices, list):
        raise SourceError("TED returned an invalid notices response.")

    notices: list[TenderNotice] = []
    seen: set[str] = set()

    for raw in raw_notices:
        if not isinstance(raw, dict):
            raise SourceError("TED returned an invalid notice object.")

        notice_type = _first_text(raw.get('notice-type'))
        # ACTIVE scope includes result/award notices: keep competition notices.
        if notice_type and notice_type.casefold() not in {
            'cn-standard', 'cn-social', 'cn-desg', 'subco', 'pin-cfc-standard',
            'pin-cfc-social', 'qu-sy', '16', '17', '18', '19', '20', '21', '22', '23', '24',
        }:
            continue

        publication_number = _first_text(
            raw.get("publication-number")
        )

        if not publication_number:
            raise SourceError(
                "TED returned a notice without publication-number."
            )

        if publication_number in seen:
            continue
        seen.add(publication_number)

        # Some historical public TED captures do not include notice-title.
        # Keep the official identifier visible without inventing a procurement title.
        title = _first_text(raw.get("notice-title")) or f"TED notice {publication_number}"

        deadline = (
            _first_text(
                raw.get("deadline-receipt-tender-date-lot")
            )
            or _first_text(raw.get("deadline-date-lot"))
            or _first_text(raw.get("deadline"))
        )

        try:
            deadline = source_date(deadline)
            published = source_date(_first_text(raw.get('publication-date')))
        except ValueError:
            raise SourceError('TED returned an invalid date.') from None
        if closed(deadline, now=now):
            continue

        notices.append(
            TenderNotice(
                source=source_name,
                external_id=publication_number[:500],
                title=title[:1000],
                url=_notice_url(publication_number)[:2000],
                published_at=published,
                tender_number=publication_number[:500],
                customer=_first_text(raw.get("buyer-name")),
                initial_price=_first_float(
                    raw.get("total-value")
                ),
                currency=_first_text(
                    raw.get("total-value-cur")
                ),
                deadline=deadline,
                region=_unique_join(
                    raw.get("place-of-performance")
                ),
                summary=(
                    _first_text(raw.get("description-proc")) or None
                ),
                enrichment=enrichment(
                    source_name, publication_number[:500],
                    locations=[[{'path': 'place-of-performance', 'value': value}]
                               for value in _text_values(raw.get('place-of-performance'))],
                    # Search-field documentation does not establish per-notice
                    # response-field or lot binding: no CPV claim is inferred.
                    classifications=[],
                    public_metadata={
                        'attribution': 'Publications Office of the European Union / TED',
                        'reference_url': _notice_url(publication_number),
                        'original_language': None,
                        'available_title_languages': list(raw.get('notice-title', {})) if isinstance(raw.get('notice-title'), dict) else [],
                        'notice_type': notice_type,
                        'deadline_state': 'reported' if deadline else 'not_supplied',
                        'raw_publication_date': raw.get('publication-date'),
                    },
                    dates={
                        'publication': {'path': 'publication-date', 'value': published},
                        'deadline': {'path': next((key for key in ('deadline-receipt-tender-date-lot',
                                                  'deadline-date-lot', 'deadline') if _first_text(raw.get(key))), 'deadline'),
                                     'value': next((raw[key] for key in ('deadline-receipt-tender-date-lot',
                                                   'deadline-date-lot', 'deadline') if _first_text(raw.get(key))), None)},
                    },
                ),
            )
        )

    return notices


@dataclass(frozen=True)
class TedApiSource:
    """Published EU procurement notices from the official TED Search API."""

    query: str = "OJ = () SORT BY publication-date DESC"
    scope: str = "ACTIVE"
    timeout: float = 30.0
    name: str = "ted"

    def __post_init__(self):
        if not math.isfinite(self.timeout) or not 0 < self.timeout <= 120:
            raise ValueError('timeout must be finite and between 0 and 120 seconds.')

    def for_search_terms(self, terms, **kwargs):
        # Only literal words enter expert syntax, never user operators.
        import re
        phrases = [' '.join(re.findall(r'[^\W_]+', str(term), re.UNICODE))[:120]
                   for term in tuple(terms)[:10]]
        phrases = [phrase for phrase in phrases if phrase]
        if not phrases:
            return self
        query = '(' + ' OR '.join(f'FT = "{phrase}"' for phrase in phrases) + ')'
        return replace(self, query=query + ' SORT BY publication-date DESC')

    async def fetch(self, limit: int = 20) -> list[TenderNotice]:
        limit = max(1, min(int(limit), 100))

        request_body = {
            "query": self.query,
            "fields": list(TED_FIELDS),
            "page": 1,
            "limit": limit,
            "scope": self.scope,
            "checkQuerySyntax": False,
            "paginationMode": "PAGE_NUMBER",
        }

        try:
            async with source_client(
                timeout=self.timeout,
                follow_redirects=False,
                trust_env=False,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "VALYQON-AI (+procurement-source)",
                },
            ) as client:
                payload = await request_json(client, 'POST', TED_SEARCH_URL,
                                             hosts={'api.ted.europa.eu'}, json=request_body)
                if payload.get('timedOut'):
                    raise SourceError('TED search timed out; results are incomplete.')

        except SourceError:
            raise
        except (httpx.HTTPError, OSError, ValueError) as error:
            failure = SourceError('Unable to fetch TED notices. ' + diagnostic(error))
            failure.retryable = retryable(error)
            raise failure from None

        if not isinstance(payload, dict):
            raise SourceError("TED returned an invalid JSON object.")

        return parse_ted_search_response(
            payload,
            source_name=self.name,
        )[:limit]


__all__ = [
    "TED_FIELDS",
    "TED_SEARCH_URL",
    "TedApiSource",
    "parse_ted_search_response",
]
