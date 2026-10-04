"""Official TED Search API v3 procurement source adapter."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from .eis_rss import SourceError
from .models import TenderNotice


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
            return float(normalized)
        except ValueError:
            continue

    return None


def _notice_url(publication_number: str) -> str:
    encoded = quote(publication_number, safe="-")
    return f"https://ted.europa.eu/en/notice/{encoded}/html"


def parse_ted_search_response(
    payload: dict[str, Any],
    *,
    source_name: str = "ted",
) -> list[TenderNotice]:
    """Normalize one TED Search API response into VALYQON notices."""

    raw_notices = payload.get("notices")

    if not isinstance(raw_notices, list):
        raise SourceError("TED returned an invalid notices response.")

    notices: list[TenderNotice] = []

    for raw in raw_notices:
        if not isinstance(raw, dict):
            raise SourceError("TED returned an invalid notice object.")

        publication_number = _first_text(
            raw.get("publication-number")
        )

        if not publication_number:
            raise SourceError(
                "TED returned a notice without publication-number."
            )

        title = (
            _first_text(raw.get("notice-title"))
            or f"TED notice {publication_number}"
        )

        deadline = (
            _first_text(
                raw.get("deadline-receipt-tender-date-lot")
            )
            or _first_text(raw.get("deadline-date-lot"))
            or _first_text(raw.get("deadline"))
        )

        notices.append(
            TenderNotice(
                source=source_name,
                external_id=publication_number[:500],
                title=title[:1000],
                url=_notice_url(publication_number)[:2000],
                published_at=_first_text(
                    raw.get("publication-date")
                ),
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
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                trust_env=True,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "VALYQON-AI (+procurement-source)",
                },
            ) as client:
                response = await client.post(
                    TED_SEARCH_URL,
                    json=request_body,
                )
                response.raise_for_status()

                if len(response.content) > 10 * 1024 * 1024:
                    raise SourceError(
                        "TED response exceeds the safe 10 MiB limit."
                    )

                try:
                    payload = response.json()
                except ValueError:
                    raise SourceError(
                        "TED returned invalid JSON."
                    ) from None

        except SourceError:
            raise
        except (httpx.HTTPError, OSError):
            raise SourceError(
                "Unable to fetch TED notices."
            ) from None

        if not isinstance(payload, dict):
            raise SourceError("TED returned an invalid JSON object.")

        return parse_ted_search_response(
            payload,
            source_name=self.name,
        )


__all__ = [
    "TED_FIELDS",
    "TED_SEARCH_URL",
    "TedApiSource",
    "parse_ted_search_response",
]
