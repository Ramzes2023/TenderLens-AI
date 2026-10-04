"""Official CanadaBuys open tender notices dataset adapter."""
from __future__ import annotations

import csv
import html
import io
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx

from .eis_rss import SourceError
from .models import TenderNotice


CANADABUYS_OPEN_TENDERS_URL = (
    "https://canadabuys.canada.ca/opendata/pub/"
    "openTenderNotice-ouvertAvisAppelOffres.csv"
)

CANADABUYS_SEARCH_URL = (
    "https://canadabuys.canada.ca/en/tender-opportunities"
)

_REFERENCE = "referenceNumber-numeroReference"
_AMENDMENT = "amendmentNumber-numeroModification"
_SOLICITATION = "solicitationNumber-numeroSollicitation"
_PUBLICATION_DATE = "publicationDate-datePublication"
_AMENDMENT_DATE = "amendmentDate-dateModification"
_CLOSING_DATE = "tenderClosingDate-appelOffresDateCloture"

_TITLE_EN = "title-titre-eng"
_TITLE_FR = "title-titre-fra"

_STATUS_EN = "tenderStatus-appelOffresStatut-eng"

_REGION_DELIVERY_EN = "regionsOfDelivery-regionsLivraison-eng"
_REGION_DELIVERY_FR = "regionsOfDelivery-regionsLivraison-fra"
_REGION_OPPORTUNITY_EN = "regionsOfOpportunity-regionAppelOffres-eng"
_REGION_OPPORTUNITY_FR = "regionsOfOpportunity-regionAppelOffres-fra"

_CUSTOMER_EN = "contractingEntityName-nomEntitContractante-eng"
_CUSTOMER_FR = "contractingEntityName-nomEntitContractante-fra"

_NOTICE_URL_EN = "noticeURL-URLavis-eng"
_NOTICE_URL_FR = "noticeURL-URLavis-fra"

_DESCRIPTION_EN = "tenderDescription-descriptionAppelOffres-eng"
_DESCRIPTION_FR = "tenderDescription-descriptionAppelOffres-fra"

_REQUIRED_FIELDS = {
    _REFERENCE,
    _SOLICITATION,
    _PUBLICATION_DATE,
    _CLOSING_DATE,
    _TITLE_EN,
}

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = html.unescape(str(value))
    text = _HTML_TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()

    return text or None


def _pick(
    row: dict[str, str],
    *keys: str,
) -> str | None:
    for key in keys:
        value = _clean_text(row.get(key))

        if value:
            return value

    return None


def _safe_url(value: Any) -> str | None:
    cleaned = _clean_text(value)

    if not cleaned:
        return None

    parsed = urlsplit(cleaned)

    if parsed.scheme not in {"http", "https"}:
        return None

    if not parsed.hostname:
        return None

    return cleaned


def _fallback_url(
    reference: str,
    solicitation: str | None,
) -> str:
    term = solicitation or reference

    query = urlencode({
        "words": term,
    })

    return f"{CANADABUYS_SEARCH_URL}?{query}"


def _notice_url(
    row: dict[str, str],
    *,
    reference: str,
    solicitation: str | None,
) -> str:
    direct = (
        _safe_url(row.get(_NOTICE_URL_EN))
        or _safe_url(row.get(_NOTICE_URL_FR))
    )

    if direct:
        return direct

    return _fallback_url(
        reference,
        solicitation,
    )


def _activity_date(
    row: dict[str, str],
) -> str:
    return (
        _pick(
            row,
            _AMENDMENT_DATE,
            _PUBLICATION_DATE,
        )
        or ""
    )


def parse_canadabuys_csv(
    payload: bytes,
    *,
    source_name: str = "canada_buys",
    limit: int = 100,
) -> list[TenderNotice]:
    """Normalize the official CanadaBuys open notices CSV."""

    limit = max(1, min(int(limit), 100))

    try:
        text = payload.decode(
            "utf-8-sig",
            errors="strict",
        )
    except UnicodeDecodeError:
        raise SourceError(
            "CanadaBuys returned invalid UTF-8 CSV."
        ) from None

    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise SourceError(
            "CanadaBuys returned CSV without headers."
        )

    fields = set(reader.fieldnames)

    missing_fields = sorted(
        _REQUIRED_FIELDS - fields
    )

    if missing_fields:
        raise SourceError(
            "CanadaBuys CSV schema is missing required fields: "
            + ", ".join(missing_fields)
        )

    rows = [
        row
        for row in reader
        if any(
            _clean_text(value)
            for value in row.values()
        )
    ]

    rows.sort(
        key=lambda row: (
            _activity_date(row),
            _pick(row, _PUBLICATION_DATE) or "",
            _pick(row, _REFERENCE) or "",
        ),
        reverse=True,
    )

    notices: list[TenderNotice] = []
    seen: set[str] = set()

    for row in rows:
        reference = _pick(
            row,
            _REFERENCE,
        )

        if not reference:
            raise SourceError(
                "CanadaBuys returned a tender without referenceNumber."
            )

        # The live dataset currently has no missing or duplicate
        # referenceNumber values. Amendment number is deliberately
        # excluded from identity so updates do not become new tenders.
        if reference in seen:
            continue

        seen.add(reference)

        solicitation = _pick(
            row,
            _SOLICITATION,
        )

        title = (
            _pick(
                row,
                _TITLE_EN,
                _TITLE_FR,
            )
            or f"CanadaBuys tender {reference}"
        )

        customer = _pick(
            row,
            _CUSTOMER_EN,
            _CUSTOMER_FR,
        )

        region = _pick(
            row,
            _REGION_DELIVERY_EN,
            _REGION_OPPORTUNITY_EN,
            _REGION_DELIVERY_FR,
            _REGION_OPPORTUNITY_FR,
        )

        summary = _pick(
            row,
            _DESCRIPTION_EN,
            _DESCRIPTION_FR,
        )

        notices.append(
            TenderNotice(
                source=source_name,
                external_id=reference[:500],
                title=title[:1000],
                url=_notice_url(
                    row,
                    reference=reference,
                    solicitation=solicitation,
                )[:2000],
                published_at=_pick(
                    row,
                    _PUBLICATION_DATE,
                ),
                tender_number=(
                    solicitation or reference
                )[:500],
                customer=customer,
                initial_price=None,
                currency=None,
                deadline=_pick(
                    row,
                    _CLOSING_DATE,
                ),
                region=region,
                summary=(
                    summary[:4000]
                    if summary
                    else None
                ),
            )
        )

        if len(notices) >= limit:
            break

    return notices


@dataclass(frozen=True)
class CanadaBuysDatasetSource:
    """Open Canadian tender notices from the official CSV dataset."""

    timeout: float = 45.0
    name: str = "canada_buys"

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

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                trust_env=True,
                headers={
                    "Accept": "text/csv,*/*",
                    "User-Agent": (
                        "VALYQON-AI (+procurement-source)"
                    ),
                },
            ) as client:
                response = await client.get(
                    CANADABUYS_OPEN_TENDERS_URL,
                )

                response.raise_for_status()

                payload = response.content

                if len(payload) > 25 * 1024 * 1024:
                    raise SourceError(
                        "CanadaBuys dataset exceeds "
                        "the safe 25 MiB limit."
                    )

                if payload.lstrip().lower().startswith(
                    b"<!doctype html"
                ):
                    raise SourceError(
                        "CanadaBuys returned HTML instead of CSV."
                    )

        except SourceError:
            raise
        except (httpx.HTTPError, OSError):
            raise SourceError(
                "Unable to fetch CanadaBuys open tender dataset."
            ) from None

        return parse_canadabuys_csv(
            payload,
            source_name=self.name,
            limit=limit,
        )


__all__ = [
    "CANADABUYS_OPEN_TENDERS_URL",
    "CANADABUYS_SEARCH_URL",
    "CanadaBuysDatasetSource",
    "parse_canadabuys_csv",
]
