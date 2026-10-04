"""Official UK Find a Tender OCDS API adapter."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from .eis_rss import SourceError
from .models import TenderNotice


UK_FTS_SEARCH_URL = (
    "https://www.find-tender.service.gov.uk/"
    "api/1.0/ocdsReleasePackages"
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = html.unescape(str(value))
    text = _HTML_TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()

    return text or None


def _first_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None

    try:
        return float(value)
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
) -> list[TenderNotice]:
    """Normalize a Find a Tender OCDS release package."""

    raw_releases = payload.get("releases")

    if not isinstance(raw_releases, list):
        raise SourceError(
            "UK Find a Tender returned an invalid releases response."
        )

    notices: list[TenderNotice] = []

    for release in raw_releases:
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
            raise SourceError(
                "UK Find a Tender returned a release without tender data."
            )

        tender_id = (
            _clean_text(tender.get("id"))
            or release_id
        )

        title = (
            _clean_text(tender.get("title"))
            or f"UK Find a Tender notice {release_id}"
        )

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
            deadline = _clean_text(
                tender_period.get("endDate")
            )

        summary = (
            _clean_text(tender.get("description"))
            or _clean_text(release.get("description"))
        )

        notices.append(
            TenderNotice(
                source=source_name,
                external_id=release_id[:500],
                title=title[:1000],
                url=_procurement_url(ocid)[:2000],
                published_at=_clean_text(
                    release.get("date")
                ),
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
            )
        )

    return notices


@dataclass(frozen=True)
class UkFindTenderApiSource:
    """Published UK procurement notices from Find a Tender."""

    timeout: float = 30.0
    name: str = "uk_fts"

    def __post_init__(self) -> None:
        if self.timeout <= 0 or self.timeout > 120:
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
        }

        try:
            async with httpx.AsyncClient(
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
                    UK_FTS_SEARCH_URL,
                    params=params,
                )

                response.raise_for_status()

                if len(response.content) > 10 * 1024 * 1024:
                    raise SourceError(
                        "UK Find a Tender response exceeds "
                        "the safe 10 MiB limit."
                    )

                try:
                    payload = response.json()
                except ValueError:
                    raise SourceError(
                        "UK Find a Tender returned invalid JSON."
                    ) from None

        except SourceError:
            raise
        except (httpx.HTTPError, OSError):
            raise SourceError(
                "Unable to fetch UK Find a Tender notices."
            ) from None

        if not isinstance(payload, dict):
            raise SourceError(
                "UK Find a Tender returned an invalid JSON object."
            )

        return parse_uk_fts_response(
            payload,
            source_name=self.name,
        )


__all__ = [
    "UK_FTS_SEARCH_URL",
    "UkFindTenderApiSource",
    "parse_uk_fts_response",
]
