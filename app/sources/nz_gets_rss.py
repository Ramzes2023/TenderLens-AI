"""Official New Zealand GETS procurement RSS adapter."""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from .http import source_client

from .eis_rss import SourceError
from .models import TenderNotice


NZ_GETS_RSS_URL = (
    "https://www.gets.govt.nz/ExternalRSSFeed.htm"
)

_GETS_HOSTS = {
    "gets.govt.nz",
    "www.gets.govt.nz",
}

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = html.unescape(str(value))

    text = re.sub(
        r"<br\s*/?>",
        " ",
        text,
        flags=re.IGNORECASE,
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


def _description_field(
    description: str,
    label: str,
) -> str | None:
    if not description:
        return None

    # Normal GETS table structure:
    #
    # <td><b>RFx ID: </b></td><td>12345678</td>
    #
    pattern = re.compile(
        rf"<b>\s*{re.escape(label)}\s*:?\s*</b>"
        rf".*?<td[^>]*>(.*?)</td>",
        flags=re.IGNORECASE | re.DOTALL,
    )

    match = pattern.search(
        description
    )

    if not match:
        # The live GETS feed currently contains malformed markup
        # for Close date:
        #
        # <b>Close date: </td><td>...
        #
        pattern = re.compile(
            rf"<b>\s*{re.escape(label)}\s*:?.*?</td>"
            rf"\s*<td[^>]*>(.*?)</td>",
            flags=re.IGNORECASE | re.DOTALL,
        )

        match = pattern.search(
            description
        )

    if not match:
        return None

    return _clean_text(
        match.group(1)
    )


def _query_rfx_id(
    url: str,
) -> str | None:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None

    if parsed.scheme != "https":
        return None

    if parsed.hostname not in _GETS_HOSTS:
        return None

    values = parse_qs(
        parsed.query
    ).get("id")

    if not values:
        return None

    value = _clean_text(
        values[0]
    )

    return value


def _canonical_detail_url(
    original_url: str,
    rfx_id: str,
) -> str:
    parsed = urlsplit(
        original_url
    )

    path = (
        "/"
        + parsed.path.lstrip("/")
    )

    query = urlencode({
        "id": rfx_id,
    })

    return (
        "https://www.gets.govt.nz"
        f"{path}?{query}"
    )


def _parse_pub_date(
    value: str | None,
) -> datetime:
    cleaned = _clean_text(value)

    if not cleaned:
        raise SourceError(
            "GETS returned an item without pubDate."
        )

    try:
        parsed = parsedate_to_datetime(
            cleaned
        )
    except (
        TypeError,
        ValueError,
        OverflowError,
    ):
        raise SourceError(
            "GETS returned an invalid pubDate."
        ) from None

    if parsed.tzinfo is None:
        raise SourceError(
            "GETS returned pubDate without timezone."
        )

    return parsed


def _parse_local_date(
    value: str | None,
    *,
    field_name: str,
) -> datetime:
    cleaned = _clean_text(value)

    if not cleaned:
        raise SourceError(
            f"GETS returned an item without {field_name}."
        )

    for date_format in (
        "%A, %d %B %Y %I:%M %p %z",
        "%A, %d %B %Y %H:%M %z",
    ):
        try:
            return datetime.strptime(
                cleaned,
                date_format,
            )
        except ValueError:
            continue

    raise SourceError(
        f"GETS returned an invalid {field_name}."
    )


def parse_nz_gets_rss(
    payload: bytes,
    *,
    source_name: str = "nz_gets",
    limit: int = 100,
) -> list[TenderNotice]:
    """Normalize official GETS RSS opportunities."""

    limit = max(
        1,
        min(int(limit), 100),
    )

    try:
        root = ET.fromstring(
            payload
        )
    except ET.ParseError:
        raise SourceError(
            "GETS returned invalid RSS XML."
        ) from None

    normalized: list[
        tuple[datetime, TenderNotice]
    ] = []

    seen: set[str] = set()

    for item in root.findall(".//item"):
        title = _clean_text(
            item.findtext("title")
        )

        link = _clean_text(
            item.findtext("link")
        )

        guid = _clean_text(
            item.findtext("guid")
        )

        description = (
            item.findtext("description")
            or ""
        )

        if not link:
            raise SourceError(
                "GETS returned an item without link."
            )

        if not guid:
            raise SourceError(
                "GETS returned an item without guid."
            )

        if link != guid:
            raise SourceError(
                "GETS returned mismatched link and guid."
            )

        query_id = _query_rfx_id(
            link
        )

        rfx_id = _description_field(
            description,
            "RFx ID",
        )

        if not query_id:
            raise SourceError(
                "GETS returned an item without RFx ID in URL."
            )

        if not rfx_id:
            raise SourceError(
                "GETS returned an item without RFx ID."
            )

        if query_id != rfx_id:
            raise SourceError(
                "GETS RFx ID does not match detail URL."
            )

        if rfx_id in seen:
            continue

        seen.add(
            rfx_id
        )

        organisation = _description_field(
            description,
            "Organisation",
        )

        if not organisation:
            raise SourceError(
                "GETS returned an item without Organisation."
            )

        open_date = _description_field(
            description,
            "Open date",
        )

        close_date = _description_field(
            description,
            "Close date",
        )

        # Validate both official local timestamps even though
        # TenderNotice currently stores only the deadline.
        _parse_local_date(
            open_date,
            field_name="Open date",
        )

        close_dt = _parse_local_date(
            close_date,
            field_name="Close date",
        )

        published_dt = _parse_pub_date(
            item.findtext("pubDate")
        )

        region = _description_field(
            description,
            "Region",
        )

        overview = _description_field(
            description,
            "Overview",
        )

        notice = TenderNotice(
            source=source_name,
            external_id=rfx_id[:500],
            title=(
                title
                or f"GETS RFx {rfx_id}"
            )[:1000],
            url=_canonical_detail_url(
                link,
                rfx_id,
            )[:2000],
            published_at=(
                published_dt.isoformat()
            ),
            tender_number=rfx_id[:500],
            customer=organisation,
            initial_price=None,
            currency=None,
            deadline=(
                close_dt.isoformat()
            ),
            region=region,
            summary=(
                overview[:4000]
                if overview
                else None
            ),
        )

        normalized.append(
            (
                published_dt,
                notice,
            )
        )

    # GETS currently orders the official RSS by close date,
    # not by publication date. VALYQON should return the
    # newest opportunities first, so sorting happens before
    # applying the requested limit.
    normalized.sort(
        key=lambda entry: (
            entry[0],
            entry[1].external_id,
        ),
        reverse=True,
    )

    return [
        notice
        for _, notice in normalized[:limit]
    ]


@dataclass(frozen=True)
class NzGetsRssSource:
    """Current procurement opportunities from New Zealand GETS."""

    timeout: float = 45.0
    name: str = "nz_gets"

    def __post_init__(self) -> None:
        if (
            self.timeout <= 0
            or self.timeout > 120
        ):
            raise ValueError(
                "timeout must be between 0 and 120 seconds."
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
                        "application/rss+xml,"
                        "application/xml,text/xml,*/*"
                    ),
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(Windows NT 10.0; Win64; x64) "
                        "VALYQON-AI procurement-source"
                    ),
                },
            ) as client:
                response = await client.get(
                    NZ_GETS_RSS_URL
                )

                response.raise_for_status()

                payload = response.content

                if (
                    len(payload)
                    > 10 * 1024 * 1024
                ):
                    raise SourceError(
                        "GETS RSS response exceeds "
                        "the safe 10 MiB limit."
                    )

                if payload.lstrip().lower().startswith(
                    b"<!doctype html"
                ):
                    raise SourceError(
                        "GETS returned HTML instead of RSS."
                    )

        except SourceError:
            raise
        except (
            httpx.HTTPError,
            OSError,
        ):
            raise SourceError(
                "Unable to fetch GETS notices."
            ) from None

        return parse_nz_gets_rss(
            payload,
            source_name=self.name,
            limit=limit,
        )


__all__ = [
    "NZ_GETS_RSS_URL",
    "NzGetsRssSource",
    "parse_nz_gets_rss",
]