"""Official SAM.gov Contract Opportunities Public API v2 adapter."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import httpx

from .http import source_client

from .eis_rss import SourceError
from .models import TenderNotice


SAM_GOV_SEARCH_URL = "https://api.sam.gov/opportunities/v2/search"


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = " ".join(str(value).split())
    return text if text and text.lower() != "null" else None


def _nested_text(
    value: Any,
    *path: str,
) -> str | None:
    current = value

    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)

    return _clean_text(current)


def _place_of_performance(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None

    parts: list[str] = []
    seen: set[str] = set()

    candidates = (
        _nested_text(value, "city", "name"),
        _nested_text(value, "state", "name"),
        _nested_text(value, "state", "code"),
        _nested_text(value, "country", "name"),
        _nested_text(value, "country", "code"),
        _clean_text(value.get("zip")),
    )

    for item in candidates:
        if not item:
            continue

        key = item.casefold()

        if key in seen:
            continue

        seen.add(key)
        parts.append(item)

    return ", ".join(parts) if parts else None


def _customer_name(raw: dict[str, Any]) -> str | None:
    hierarchy = _clean_text(raw.get("fullParentPathName"))

    if hierarchy:
        return hierarchy

    fallback = [
        _clean_text(raw.get("department")),
        _clean_text(raw.get("subTier")),
        _clean_text(raw.get("office")),
    ]

    result: list[str] = []
    seen: set[str] = set()

    for item in fallback:
        if not item:
            continue

        key = item.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return " / ".join(result) if result else None


def _notice_url(notice_id: str) -> str:
    return f"https://sam.gov/opp/{notice_id}/view"


def parse_sam_gov_response(
    payload: dict[str, Any],
    *,
    source_name: str = "sam_gov",
) -> list[TenderNotice]:
    """Normalize one SAM.gov Opportunities API response."""

    raw_notices = payload.get("opportunitiesData")

    if not isinstance(raw_notices, list):
        raise SourceError(
            "SAM.gov returned an invalid opportunitiesData response."
        )

    notices: list[TenderNotice] = []

    for raw in raw_notices:
        if not isinstance(raw, dict):
            raise SourceError(
                "SAM.gov returned an invalid opportunity object."
            )

        notice_id = _clean_text(raw.get("noticeId"))

        if not notice_id:
            raise SourceError(
                "SAM.gov returned an opportunity without noticeId."
            )

        title = (
            _clean_text(raw.get("title"))
            or f"SAM.gov opportunity {notice_id}"
        )

        tender_number = (
            _clean_text(raw.get("solicitationNumber"))
            or notice_id
        )

        deadline = (
            _clean_text(raw.get("responseDeadLine"))
            or _clean_text(raw.get("reponseDeadLine"))
        )

        notices.append(
            TenderNotice(
                source=source_name,
                external_id=notice_id[:500],
                title=title[:1000],
                url=_notice_url(notice_id)[:2000],
                published_at=_clean_text(
                    raw.get("postedDate")
                ),
                tender_number=tender_number[:500],
                customer=_customer_name(raw),
                initial_price=None,
                currency=None,
                deadline=deadline,
                region=_place_of_performance(
                    raw.get("placeOfPerformance")
                ),
                summary=None,
            )
        )

    return notices


@dataclass(frozen=True)
class SamGovApiSource:
    """Published U.S. federal opportunities from SAM.gov."""

    api_key: str
    lookback_days: int = 7
    timeout: float = 30.0
    name: str = "sam_gov"

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError(
                "SAM.gov API key must not be empty."
            )

        if self.lookback_days < 0 or self.lookback_days > 365:
            raise ValueError(
                "lookback_days must be between 0 and 365."
            )

        if self.timeout <= 0 or self.timeout > 120:
            raise ValueError(
                "timeout must be between 0 and 120 seconds."
            )

    def _date_range(
        self,
        *,
        today: date | None = None,
    ) -> tuple[str, str]:
        end = today or date.today()
        start = end - timedelta(days=self.lookback_days)

        return (
            start.strftime("%m/%d/%Y"),
            end.strftime("%m/%d/%Y"),
        )

    async def fetch(self, limit: int = 20) -> list[TenderNotice]:
        limit = max(1, min(int(limit), 100))

        posted_from, posted_to = self._date_range()

        params = {
            "api_key": self.api_key,
            "postedFrom": posted_from,
            "postedTo": posted_to,
            "limit": str(limit),
            "offset": "0",
        }

        try:
            async with source_client(
                timeout=self.timeout,
                follow_redirects=True,
                trust_env=True,
                headers={
                    "Accept": "application/json",
                    "User-Agent": (
                        "VALYQON-AI (+procurement-source)"
                    ),
                },
            ) as client:
                response = await client.get(
                    SAM_GOV_SEARCH_URL,
                    params=params,
                )

                response.raise_for_status()

                if len(response.content) > 10 * 1024 * 1024:
                    raise SourceError(
                        "SAM.gov response exceeds "
                        "the safe 10 MiB limit."
                    )

                try:
                    payload = response.json()
                except ValueError:
                    raise SourceError(
                        "SAM.gov returned invalid JSON."
                    ) from None

        except SourceError:
            raise
        except (httpx.HTTPError, OSError):
            # Never expose request URLs here because api_key is a query
            # parameter required by the official SAM.gov public API.
            raise SourceError(
                "Unable to fetch SAM.gov opportunities."
            ) from None

        if not isinstance(payload, dict):
            raise SourceError(
                "SAM.gov returned an invalid JSON object."
            )

        return parse_sam_gov_response(
            payload,
            source_name=self.name,
        )


__all__ = [
    "SAM_GOV_SEARCH_URL",
    "SamGovApiSource",
    "parse_sam_gov_response",
]
