"""Official South Africa eTenders active opportunities adapter."""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .http import source_client

from .eis_rss import SourceError
from .models import TenderNotice


ZA_ETENDERS_ACTIVE_TENDERS_URL = (
    "https://admin.etenders.gov.za/"
    "Home/TenderOpportunities/"
)

ZA_ETENDERS_OPPORTUNITIES_URL = (
    "https://admin.etenders.gov.za/"
    "Home/opportunities"
)

_SAST = timezone(
    timedelta(hours=2)
)

_HTML_TAG_RE = re.compile(
    r"<[^>]+>"
)

_WS_RE = re.compile(
    r"\s+"
)

_PLACEHOLDERS = {
    "",
    "-",
    "n/a",
    "na",
    "none",
    "null",
    "not available",
    "<not available>",
}


def _clean_text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    text = html.unescape(
        str(value)
    )

    text = _HTML_TAG_RE.sub(
        " ",
        text,
    )

    text = _WS_RE.sub(
        " ",
        text,
    ).strip()

    return text or None


def _useful_text(
    value: Any,
) -> str | None:
    cleaned = _clean_text(
        value
    )

    if not cleaned:
        return None

    if cleaned.lower() in _PLACEHOLDERS:
        return None

    return cleaned


def _required_text(
    value: Any,
    *,
    field_name: str,
) -> str:
    cleaned = _clean_text(
        value
    )

    if not cleaned:
        raise SourceError(
            "South Africa eTenders returned "
            f"a tender without {field_name}."
        )

    return cleaned


def _parse_local_datetime(
    value: Any,
    *,
    field_name: str,
) -> datetime:
    cleaned = _required_text(
        value,
        field_name=field_name,
    )

    try:
        parsed = datetime.fromisoformat(
            cleaned
        )
    except ValueError:
        raise SourceError(
            "South Africa eTenders returned "
            f"an invalid {field_name}."
        ) from None

    # The live portal currently emits local South African
    # timestamps without an explicit UTC offset.
    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=_SAST
        )

    return parsed


def _external_id(
    value: Any,
) -> str:
    cleaned = _required_text(
        value,
        field_name="id",
    )

    try:
        numeric_id = int(
            cleaned
        )
    except ValueError:
        raise SourceError(
            "South Africa eTenders returned "
            "a non-numeric tender id."
        ) from None

    if numeric_id <= 0:
        raise SourceError(
            "South Africa eTenders returned "
            "an invalid tender id."
        )

    return str(
        numeric_id
    )


def _summary(
    row: dict[str, Any],
) -> str | None:
    parts: list[str] = []

    tender_type = _useful_text(
        row.get("type")
    )

    category = _useful_text(
        row.get("category")
    )

    conditions = _useful_text(
        row.get("conditions")
    )

    delivery = _useful_text(
        row.get("delivery")
    )

    if tender_type:
        parts.append(
            f"Tender type: {tender_type}."
        )

    if category:
        parts.append(
            f"Category: {category}."
        )

    if conditions:
        parts.append(
            f"Special conditions: {conditions}"
        )

    if delivery:
        parts.append(
            f"Delivery: {delivery}"
        )

    if not parts:
        return None

    return " ".join(parts)[:4000]


def parse_za_etenders_response(
    payload: bytes,
    *,
    source_name: str = "za_etenders",
    limit: int = 100,
) -> list[TenderNotice]:
    """Normalize current South Africa eTenders opportunities."""

    limit = max(
        1,
        min(int(limit), 100),
    )

    try:
        data = json.loads(
            payload
        )
    except (
        json.JSONDecodeError,
        UnicodeDecodeError,
    ):
        raise SourceError(
            "South Africa eTenders returned invalid JSON."
        ) from None

    if not isinstance(
        data,
        list,
    ):
        raise SourceError(
            "South Africa eTenders returned "
            "an unexpected JSON structure."
        )

    normalized: list[
        tuple[
            datetime,
            int,
            TenderNotice,
        ]
    ] = []

    seen: set[str] = set()

    for row in data:
        if not isinstance(
            row,
            dict,
        ):
            raise SourceError(
                "South Africa eTenders returned "
                "an invalid tender record."
            )

        external_id = _external_id(
            row.get("id")
        )

        if external_id in seen:
            continue

        seen.add(
            external_id
        )

        tender_number = _required_text(
            row.get("tender_No"),
            field_name="tender_No",
        )

        description = _required_text(
            row.get("description"),
            field_name="description",
        )

        customer = _required_text(
            row.get("department"),
            field_name="department",
        )

        published_dt = _parse_local_datetime(
            row.get("date_Published"),
            field_name="date_Published",
        )

        deadline_dt = _parse_local_datetime(
            row.get("closing_Date"),
            field_name="closing_Date",
        )

        region = _useful_text(
            row.get("province")
        )

        notice = TenderNotice(
            source=source_name,
            external_id=external_id[:500],
            title=description[:1000],
            url=(
                ZA_ETENDERS_OPPORTUNITIES_URL
            )[:2000],
            published_at=(
                published_dt.isoformat()
            ),
            tender_number=(
                tender_number[:500]
            ),
            customer=customer,
            initial_price=None,
            currency=None,
            deadline=(
                deadline_dt.isoformat()
            ),
            region=region,
            summary=_summary(
                row
            ),
        )

        normalized.append(
            (
                published_dt,
                int(external_id),
                notice,
            )
        )

    # The live endpoint currently arrives newest-first,
    # but sorting here makes that ordering deterministic
    # before the requested limit is applied.
    normalized.sort(
        key=lambda entry: (
            entry[0],
            entry[1],
        ),
        reverse=True,
    )

    return [
        notice
        for _, _, notice
        in normalized[:limit]
    ]


@dataclass(frozen=True)
class ZaETendersSource:
    """Active opportunities from South Africa eTenders."""

    timeout: float = 60.0
    name: str = "za_etenders"

    def __post_init__(self) -> None:
        if (
            self.timeout <= 0
            or self.timeout > 120
        ):
            raise ValueError(
                "timeout must be between "
                "0 and 120 seconds."
            )

    async def fetch(
        self,
        limit: int = 20,
    ) -> list[TenderNotice]:
        limit = max(
            1,
            min(int(limit), 100),
        )

        try:
            async with source_client(
                timeout=self.timeout,
                follow_redirects=True,
                trust_env=True,
                headers={
                    "Accept": (
                        "application/json,*/*"
                    ),
                    "Referer": (
                        ZA_ETENDERS_OPPORTUNITIES_URL
                    ),
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(Windows NT 10.0; Win64; x64) "
                        "VALYQON-AI procurement-source"
                    ),
                },
            ) as client:
                response = await client.get(
                    ZA_ETENDERS_ACTIVE_TENDERS_URL,
                    params={
                        "status": 1,
                    },
                )

                response.raise_for_status()

                payload = response.content

                if (
                    len(payload)
                    > 15 * 1024 * 1024
                ):
                    raise SourceError(
                        "South Africa eTenders response "
                        "exceeds the safe 15 MiB limit."
                    )

                if payload.lstrip().lower().startswith(
                    (
                        b"<!doctype html",
                        b"<html",
                    )
                ):
                    raise SourceError(
                        "South Africa eTenders returned "
                        "HTML instead of JSON."
                    )

        except SourceError:
            raise
        except (
            httpx.HTTPError,
            OSError,
        ):
            raise SourceError(
                "Unable to fetch South Africa "
                "eTenders opportunities."
            ) from None

        return parse_za_etenders_response(
            payload,
            source_name=self.name,
            limit=limit,
        )


__all__ = [
    "ZA_ETENDERS_ACTIVE_TENDERS_URL",
    "ZA_ETENDERS_OPPORTUNITIES_URL",
    "ZaETendersSource",
    "parse_za_etenders_response",
]