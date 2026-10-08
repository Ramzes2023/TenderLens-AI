"""Official India CPPP current tenders adapter."""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote, urljoin

import httpx

from .http import page_limit, source_client

from .eis_rss import SourceError
from .models import TenderNotice


INDIA_CPPP_HOME_URL = (
    "https://eprocure.gov.in/eprocure/app"
)

INDIA_CPPP_LIST_URL = (
    "https://eprocure.gov.in/eprocure/app"
    "?page=FrontEndListTendersbyDate"
    "&service=page"
)

_IST = timezone(
    timedelta(
        hours=5,
        minutes=30,
    )
)

_MAX_PAGES = 50

_MAX_PAGE_BYTES = (
    2 * 1024 * 1024
)

_HTML_TAG_RE = re.compile(
    r"<[^>]+>"
)

_WS_RE = re.compile(
    r"\s+"
)

_ROW_RE = re.compile(
    r"^\d+\.\s+"
    r"(?P<published>"
    r"\d{2}-[A-Za-z]{3}-\d{4}\s+"
    r"\d{2}:\d{2}\s+[AP]M"
    r")\s+"
    r"(?P<deadline>"
    r"\d{2}-[A-Za-z]{3}-\d{4}\s+"
    r"\d{2}:\d{2}\s+[AP]M"
    r")\s+"
    r"(?P<opening>"
    r"\d{2}-[A-Za-z]{3}-\d{4}\s+"
    r"\d{2}:\d{2}\s+[AP]M"
    r")\s+"
    r"\[(?P<title>.*?)\]\s+"
    r"\[(?P<reference>.*?)\]"
    r"\[(?P<tender_id>[^\]]+)\]\s+"
    r"(?P<organisation>.*?)\s*>?$",
    flags=re.I,
)


@dataclass(frozen=True)
class _CpppRow:
    external_id: str
    tender_number: str
    title: str
    customer: str
    published_at: datetime
    deadline: datetime
    opening_at: datetime

    @property
    def fingerprint(
        self,
    ) -> tuple[str, ...]:
        return (
            self.tender_number,
            self.title,
            self.customer,
            self.published_at.isoformat(),
            self.deadline.isoformat(),
            self.opening_at.isoformat(),
        )


def _clean_html(
    value: str,
) -> str:
    value = _HTML_TAG_RE.sub(
        " ",
        value,
    )

    value = html.unescape(
        value
    )

    return _WS_RE.sub(
        " ",
        value,
    ).strip()


def _required(
    value: Any,
    *,
    field_name: str,
) -> str:
    if value is None:
        raise SourceError(
            "India CPPP returned "
            f"a tender without {field_name}."
        )

    text = _WS_RE.sub(
        " ",
        str(value),
    ).strip()

    if not text:
        raise SourceError(
            "India CPPP returned "
            f"a tender without {field_name}."
        )

    return text


def _parse_datetime(
    value: str,
    *,
    field_name: str,
) -> datetime:
    cleaned = _required(
        value,
        field_name=field_name,
    )

    try:
        parsed = datetime.strptime(
            cleaned,
            "%d-%b-%Y %I:%M %p",
        )
    except ValueError:
        raise SourceError(
            "India CPPP returned "
            f"an invalid {field_name}."
        ) from None

    return parsed.replace(
        tzinfo=_IST
    )


def _customer(
    value: str,
) -> str:
    cleaned = _required(
        value,
        field_name="organisation",
    )

    parts = [
        part.strip()
        for part in cleaned.split("||")
        if part.strip()
    ]

    if not parts:
        raise SourceError(
            "India CPPP returned "
            "a tender without organisation."
        )

    return " > ".join(
        parts
    )


def _decode_payload(
    payload: bytes,
) -> str:
    if not payload:
        raise SourceError(
            "India CPPP returned "
            "an empty response."
        )

    if (
        len(payload)
        > _MAX_PAGE_BYTES
    ):
        raise SourceError(
            "India CPPP response "
            "exceeds the safe 2 MiB limit."
        )

    try:
        return payload.decode(
            "utf-8"
        )
    except UnicodeDecodeError:
        return payload.decode(
            "utf-8",
            errors="replace",
        )


def _extract_rows(
    payload: bytes,
) -> list[_CpppRow]:
    text = _decode_payload(
        payload
    )

    html_rows = re.findall(
        r"<tr\b[^>]*>(.*?)</tr>",
        text,
        flags=re.I | re.S,
    )

    rows: list[_CpppRow] = []

    for row_html in html_rows:
        links = re.findall(
            r'''href=["']([^"']+)["']''',
            row_html,
            flags=re.I,
        )

        has_direct_link = any(
            (
                "DirectLink" in link
                or "%24DirectLink" in link
            )
            for link in links
        )

        if not has_direct_link:
            continue

        row_text = _clean_html(
            row_html
        )

        match = _ROW_RE.match(
            row_text
        )

        if not match:
            raise SourceError(
                "India CPPP returned "
                "an unexpected tender row structure."
            )

        data = match.groupdict()

        external_id = _required(
            data.get("tender_id"),
            field_name="Tender ID",
        )

        tender_number = _required(
            data.get("reference"),
            field_name=(
                "Tender Reference Number"
            ),
        )

        title = _required(
            data.get("title"),
            field_name="Tender Title",
        )

        customer = _customer(
            data.get("organisation") or ""
        )

        published_at = _parse_datetime(
            data["published"],
            field_name="Published Date",
        )

        deadline = _parse_datetime(
            data["deadline"],
            field_name=(
                "Bid Submission End Date"
            ),
        )

        opening_at = _parse_datetime(
            data["opening"],
            field_name="Bid Opening Date",
        )

        rows.append(
            _CpppRow(
                external_id=external_id,
                tender_number=tender_number,
                title=title,
                customer=customer,
                published_at=published_at,
                deadline=deadline,
                opening_at=opening_at,
            )
        )

    return rows


def _next_page_url(
    payload: bytes,
) -> str | None:
    text = _decode_payload(
        payload
    )

    links = re.findall(
        r'''href=["']([^"']+)["']''',
        text,
        flags=re.I,
    )

    for raw_link in links:
        link = html.unescape(
            raw_link
        )

        decoded = unquote(
            link
        )

        if (
            "component=$TablePages.linkFwd"
            in decoded
        ):
            return urljoin(
                INDIA_CPPP_HOME_URL,
                link,
            )

    return None


def _to_notice(
    row: _CpppRow,
    *,
    source_name: str,
) -> TenderNotice:
    return TenderNotice(
        source=source_name,
        external_id=row.external_id[:500],
        title=row.title[:1000],
        url=INDIA_CPPP_LIST_URL[:2000],
        published_at=(
            row.published_at.isoformat()
        ),
        tender_number=(
            row.tender_number[:500]
        ),
        customer=row.customer,
        initial_price=None,
        currency=None,
        deadline=(
            row.deadline.isoformat()
        ),
        region=None,
        summary=None,
    )


def parse_india_cppp_listing(
    payload: bytes,
    *,
    source_name: str = "india_cppp",
    limit: int = 100,
) -> list[TenderNotice]:
    """Normalize one India CPPP tender-list page."""

    limit = max(
        1,
        min(int(limit), 100),
    )

    rows = _extract_rows(
        payload
    )

    if not rows:
        raise SourceError(
            "India CPPP returned "
            "no tender rows."
        )

    seen: dict[
        str,
        _CpppRow,
    ] = {}

    for row in rows:
        existing = seen.get(
            row.external_id
        )

        if existing is not None:
            if (
                existing.fingerprint
                != row.fingerprint
            ):
                raise SourceError(
                    "India CPPP returned "
                    "conflicting duplicate Tender IDs."
                )

            continue

        seen[
            row.external_id
        ] = row

    return [
        _to_notice(
            row,
            source_name=source_name,
        )
        for row in list(
            seen.values()
        )[:limit]
    ]


@dataclass(frozen=True)
class IndiaCpppSource:
    """Current tenders from India's official CPPP portal."""

    timeout: float = 60.0
    name: str = "india_cppp"

    def __post_init__(
        self,
    ) -> None:
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

        headers = {
            "Accept": "text/html,*/*",
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "VALYQON-AI procurement-source"
            ),
        }

        seen: dict[
            str,
            _CpppRow,
        ] = {}

        page_signatures: set[
            tuple[str, ...]
        ] = set()

        try:
            async with source_client(
                timeout=self.timeout,
                follow_redirects=True,
                trust_env=True,
                headers=headers,
            ) as client:

                response = await client.get(
                    INDIA_CPPP_LIST_URL
                )

                response.raise_for_status()

                for _ in range(
                    page_limit(_MAX_PAGES)
                ):
                    payload = (
                        response.content
                    )

                    rows = _extract_rows(
                        payload
                    )

                    if not rows:
                        if not seen:
                            raise SourceError(
                                "India CPPP returned "
                                "no tender rows."
                            )

                        break

                    signature = tuple(
                        row.external_id
                        for row in rows
                    )

                    if (
                        signature
                        in page_signatures
                    ):
                        break

                    page_signatures.add(
                        signature
                    )

                    for row in rows:
                        existing = seen.get(
                            row.external_id
                        )

                        if (
                            existing
                            is not None
                        ):
                            if (
                                existing.fingerprint
                                != row.fingerprint
                            ):
                                raise SourceError(
                                    "India CPPP returned "
                                    "conflicting duplicate "
                                    "Tender IDs."
                                )

                            continue

                        seen[
                            row.external_id
                        ] = row

                        if (
                            len(seen)
                            >= limit
                        ):
                            break

                    if (
                        len(seen)
                        >= limit
                    ):
                        break

                    next_url = (
                        _next_page_url(
                            payload
                        )
                    )

                    if not next_url:
                        break

                    if _ + 1 >= page_limit(_MAX_PAGES):
                        break

                    response = (
                        await client.get(
                            next_url,
                            headers={
                                "Referer": str(
                                    response.url
                                ),
                            },
                        )
                    )

                    response.raise_for_status()

        except SourceError:
            raise
        except (
            httpx.HTTPError,
            OSError,
        ):
            raise SourceError(
                "Unable to fetch "
                "India CPPP tenders."
            ) from None

        if not seen:
            raise SourceError(
                "India CPPP returned "
                "no usable tenders."
            )

        return [
            _to_notice(
                row,
                source_name=self.name,
            )
            for row in list(
                seen.values()
            )[:limit]
        ]


__all__ = [
    "INDIA_CPPP_HOME_URL",
    "INDIA_CPPP_LIST_URL",
    "IndiaCpppSource",
    "parse_india_cppp_listing",
]
