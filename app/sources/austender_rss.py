"""Official AusTender current ATM RSS + detail-page adapter."""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qs, unquote_plus, urlsplit

import httpx

from .http import source_client

from .eis_rss import SourceError
from .models import TenderNotice


AUSTENDER_RSS_URL = (
    "https://www.tenders.gov.au/public_data/rss/rss.xml"
)

AUSTENDER_ATM_BASE_URL = (
    "https://www.tenders.gov.au/Atm/Show/"
)

_ATM_UUID_RE = re.compile(
    r"^/Atm/Show/"
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12})/?$"
)

_LIST_DESC_RE = re.compile(
    r'<div\s+class=["\']list-desc["\']>\s*'
    r"<span>(.*?)</span>\s*"
    r'<div\s+class=["\']list-desc-inner["\']>'
    r"(.*?)</div>\s*</div>",
    flags=re.IGNORECASE | re.DOTALL,
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class AusTenderRssItem:
    external_id: str
    title: str
    url: str
    published_at: str | None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = html.unescape(str(value))

    text = re.sub(
        r"<br\s*/?>",
        " | ",
        text,
        flags=re.IGNORECASE,
    )

    text = _HTML_TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip(" :|")

    return text or None


def _canonical_atm_url(external_id: str) -> str:
    return f"{AUSTENDER_ATM_BASE_URL}{external_id}"


def _extract_atm_uuid(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None

    if parsed.scheme != "https":
        return None

    if parsed.hostname not in {
        "www.tenders.gov.au",
        "tenders.gov.au",
    }:
        return None

    match = _ATM_UUID_RE.fullmatch(parsed.path)

    if not match:
        return None

    return match.group(1).lower()


def _parse_rss_date(value: str | None) -> str | None:
    cleaned = _clean_text(value)

    if not cleaned:
        return None

    try:
        parsed = parsedate_to_datetime(cleaned)
    except (TypeError, ValueError, OverflowError):
        return cleaned

    return parsed.date().isoformat()


def parse_austender_rss(
    payload: bytes,
) -> list[AusTenderRssItem]:
    """Parse current ATM discovery records from the official RSS feed."""

    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        raise SourceError(
            "AusTender returned invalid RSS XML."
        ) from None

    items: list[AusTenderRssItem] = []
    seen: set[str] = set()

    for item in root.findall(".//item"):
        link = _clean_text(item.findtext("link"))

        if not link:
            continue

        external_id = _extract_atm_uuid(link)

        # The live feed also contains /Advert/Show/ records.
        # Phase23E intentionally covers current ATM records only.
        if not external_id:
            continue

        if external_id in seen:
            continue

        seen.add(external_id)

        title = (
            _clean_text(item.findtext("title"))
            or f"AusTender ATM {external_id}"
        )

        items.append(
            AusTenderRssItem(
                external_id=external_id,
                title=title[:1000],
                url=_canonical_atm_url(external_id)[:2000],
                published_at=_parse_rss_date(
                    item.findtext("pubDate")
                ),
            )
        )

    return items


def _data_layer_field(
    page: str,
    key: str,
) -> str | None:
    pattern = re.compile(
        rf"'{re.escape(key)}'\s*:\s*"
        r"'((?:\\.|[^'])*)'",
        flags=re.DOTALL,
    )

    match = pattern.search(page)

    if not match:
        return None

    value = match.group(1)

    value = (
        value
        .replace("\\'", "'")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )

    return _clean_text(value)


def _detail_fields(page: str) -> dict[str, str]:
    fields: dict[str, str] = {}

    for raw_name, raw_value in _LIST_DESC_RE.findall(page):
        name = _clean_text(raw_name)
        value = _clean_text(raw_value)

        if not name:
            continue

        fields[name] = value or ""

    return fields


def _parse_publish_date(
    value: str | None,
    fallback: str | None,
) -> str | None:
    cleaned = _clean_text(value)

    if not cleaned:
        return fallback

    for date_format in (
        "%d-%b-%Y",
        "%d-%B-%Y",
    ):
        try:
            return datetime.strptime(
                cleaned,
                date_format,
            ).date().isoformat()
        except ValueError:
            continue

    return cleaned


def _parse_timezone_close(page: str) -> str | None:
    match = re.search(
        r'href=["\']([^"\']*'
        r"TimeZone\?[^\"\']+)['\"]",
        page,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    href = html.unescape(match.group(1))

    try:
        query = parse_qs(urlsplit(href).query)
    except ValueError:
        return None

    values = query.get("CloseDateTime")

    if not values:
        return None

    raw = unquote_plus(values[0]).strip()

    try:
        parsed = datetime.strptime(
            raw,
            "%m/%d/%Y %H:%M:%S",
        )
    except ValueError:
        return None

    # AusTender explicitly labels this value as ACT Local Time.
    # We preserve the local wall-clock time instead of inventing
    # a UTC offset without timezone metadata from the source.
    return parsed.isoformat()


def _parse_display_close(
    value: str | None,
) -> str | None:
    cleaned = _clean_text(value)

    if not cleaned:
        return None

    cleaned = re.sub(
        r"\|\s*Show close time for other time zones.*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    cleaned = re.sub(
        r"\s*\(ACT Local Time\)\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    for date_format in (
        "%d-%b-%Y %I:%M %p",
        "%d-%B-%Y %I:%M %p",
    ):
        try:
            parsed = datetime.strptime(
                cleaned,
                date_format,
            )
            return parsed.isoformat()
        except ValueError:
            continue

    return cleaned or None


def _parse_deadline(
    page: str,
    fields: dict[str, str],
) -> str | None:
    return (
        _parse_timezone_close(page)
        or _parse_display_close(
            fields.get("Close Date & Time")
        )
    )


def _normalize_region(
    value: str | None,
) -> str | None:
    cleaned = _clean_text(value)

    if not cleaned:
        return None

    parts = [
        part.strip()
        for part in cleaned.split("|")
        if part.strip()
    ]

    if not parts:
        return None

    return ", ".join(parts)


def _parse_estimated_value(
    fields: dict[str, str],
) -> tuple[float | None, str | None]:
    value = fields.get("Estimated Value (AUD)")

    cleaned = _clean_text(value)

    if not cleaned:
        return None, None

    amounts = re.findall(
        r"\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        cleaned,
    )

    # A range such as "From $20,000 to $25,000" cannot be
    # represented faithfully by TenderNotice.initial_price.
    # Keep AUD metadata but do not invent a single value.
    if len(amounts) != 1:
        return None, "AUD"

    lower = cleaned.casefold()

    if "from " in lower or " to " in lower:
        return None, "AUD"

    try:
        amount = float(
            amounts[0].replace(",", "")
        )
    except ValueError:
        return None, "AUD"

    return amount, "AUD"


def _fallback_title(
    rss_title: str,
    tender_number: str | None,
) -> str:
    title = _clean_text(rss_title)

    if not title:
        return "AusTender opportunity"

    if tender_number:
        prefix = f"{tender_number}:"

        if title.casefold().startswith(
            prefix.casefold()
        ):
            stripped = title[len(prefix):].strip()

            if stripped:
                return stripped

    return title


def parse_austender_detail_page(
    payload: bytes | str,
    *,
    external_id: str,
    url: str,
    rss_title: str,
    rss_published_at: str | None = None,
    source_name: str = "austender",
) -> TenderNotice:
    """Normalize one official AusTender ATM detail page."""

    if isinstance(payload, bytes):
        page = payload.decode(
            "utf-8",
            errors="replace",
        )
    else:
        page = payload

    fields = _detail_fields(page)

    tender_number = (
        _clean_text(fields.get("ATM ID"))
        or _data_layer_field(page, "atmID")
    )

    title = (
        _data_layer_field(page, "atmTitle")
        or _fallback_title(
            rss_title,
            tender_number,
        )
    )

    customer = (
        _clean_text(fields.get("Agency"))
        or _data_layer_field(
            page,
            "atmAgencyName",
        )
    )

    region = (
        _normalize_region(fields.get("Location"))
        or _normalize_region(
            _data_layer_field(
                page,
                "atmLocationState",
            )
        )
    )

    initial_price, currency = (
        _parse_estimated_value(fields)
    )

    summary = _clean_text(
        fields.get("Description")
    )

    return TenderNotice(
        source=source_name,
        external_id=external_id[:500],
        title=title[:1000],
        url=url[:2000],
        published_at=_parse_publish_date(
            fields.get("Publish Date"),
            rss_published_at,
        ),
        tender_number=(
            tender_number[:500]
            if tender_number
            else None
        ),
        customer=customer,
        initial_price=initial_price,
        currency=currency,
        deadline=_parse_deadline(
            page,
            fields,
        ),
        region=region,
        summary=(
            summary[:4000]
            if summary
            else None
        ),
    )


@dataclass(frozen=True)
class AusTenderRssSource:
    """Current Australian Government ATM notices from AusTender."""

    timeout: float = 45.0
    max_concurrency: int = 5
    name: str = "austender"

    def __post_init__(self) -> None:
        if self.timeout <= 0 or self.timeout > 120:
            raise ValueError(
                "timeout must be between 0 and 120 seconds."
            )

        if (
            self.max_concurrency < 1
            or self.max_concurrency > 20
        ):
            raise ValueError(
                "max_concurrency must be between 1 and 20."
            )

    async def fetch(
        self,
        limit: int = 20,
    ) -> list[TenderNotice]:
        limit = max(1, min(int(limit), 100))

        try:
            async with source_client(
                timeout=self.timeout,
                follow_redirects=True,
                trust_env=True,
                headers={
                    "Accept": (
                        "text/html,application/rss+xml,"
                        "application/xml,text/xml,*/*"
                    ),
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(Windows NT 10.0; Win64; x64) "
                        "VALYQON-AI procurement-source"
                    ),
                },
            ) as client:
                rss_response = await client.get(
                    AUSTENDER_RSS_URL,
                )

                rss_response.raise_for_status()

                rss_payload = rss_response.content

                if len(rss_payload) > 5 * 1024 * 1024:
                    raise SourceError(
                        "AusTender RSS response exceeds "
                        "the safe 5 MiB limit."
                    )

                items = parse_austender_rss(
                    rss_payload,
                )[:limit]

                semaphore = __import__(
                    "asyncio"
                ).Semaphore(
                    self.max_concurrency
                )

                async def fetch_detail(
                    item: AusTenderRssItem,
                ) -> TenderNotice:
                    async with semaphore:
                        response = await client.get(
                            item.url,
                        )

                        response.raise_for_status()

                        if (
                            len(response.content)
                            > 5 * 1024 * 1024
                        ):
                            raise SourceError(
                                "AusTender ATM detail page "
                                "exceeds the safe 5 MiB limit."
                            )

                        return parse_austender_detail_page(
                            response.content,
                            external_id=item.external_id,
                            url=item.url,
                            rss_title=item.title,
                            rss_published_at=(
                                item.published_at
                            ),
                            source_name=self.name,
                        )

                import asyncio

                return list(
                    await asyncio.gather(
                        *(
                            fetch_detail(item)
                            for item in items
                        )
                    )
                )

        except SourceError:
            raise
        except (httpx.HTTPError, OSError):
            raise SourceError(
                "Unable to fetch AusTender notices."
            ) from None


__all__ = [
    "AUSTENDER_ATM_BASE_URL",
    "AUSTENDER_RSS_URL",
    "AusTenderRssItem",
    "AusTenderRssSource",
    "parse_austender_detail_page",
    "parse_austender_rss",
]