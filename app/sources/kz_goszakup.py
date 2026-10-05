"""Official Kazakhstan Public Procurement Open API adapter."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from .eis_rss import SourceError
from .models import TenderNotice


KZ_GOSZAKUP_API_BASE_URL = "https://ows.goszakup.gov.kz"
KZ_GOSZAKUP_ANNOUNCEMENTS_URL = (
    KZ_GOSZAKUP_API_BASE_URL + "/trd-buy"
)
KZ_GOSZAKUP_PUBLIC_ANNOUNCEMENT_BASE_URL = (
    "https://goszakup.gov.kz/ru/announce/index"
)

_MAX_RESPONSE_BYTES = 10 * 1024 * 1024
_MAX_PAGES = 20


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = " ".join(str(value).split())

    if not text or text.lower() == "null":
        return None

    return text


def _normalize_datetime(value: Any) -> str | None:
    text = _clean_text(value)

    if not text:
        return None

    if (
        len(text) >= 19
        and text[4] == "-"
        and text[7] == "-"
        and text[10] == " "
        and text[13] == ":"
        and text[16] == ":"
    ):
        return text[:10] + "T" + text[11:]

    return text


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = _clean_text(value)

    if not text:
        return None

    normalized = text.replace(" ", "").replace("\u00a0", "")

    if "," in normalized and "." not in normalized:
        normalized = normalized.replace(",", ".")

    try:
        return float(normalized)
    except ValueError:
        return None


def _announcement_url(advert_id: str) -> str:
    return (
        f"{KZ_GOSZAKUP_PUBLIC_ANNOUNCEMENT_BASE_URL}/"
        f"{advert_id}"
    )


def parse_kz_goszakup_response(
    payload: dict[str, Any],
    *,
    source_name: str = "kz_goszakup",
) -> list[TenderNotice]:
    """Normalize one Kazakhstan procurement announcements page."""

    raw_items = payload.get("items")

    if not isinstance(raw_items, list):
        raise SourceError(
            "Kazakhstan procurement API returned "
            "an invalid items response."
        )

    notices: list[TenderNotice] = []

    for raw in raw_items:
        if not isinstance(raw, dict):
            raise SourceError(
                "Kazakhstan procurement API returned "
                "an invalid announcement object."
            )

        advert_id = _clean_text(raw.get("id"))

        if not advert_id:
            raise SourceError(
                "Kazakhstan procurement API returned "
                "an announcement without id."
            )

        number = (
            _clean_text(raw.get("number_anno"))
            or advert_id
        )

        title = (
            _clean_text(raw.get("name_ru"))
            or _clean_text(raw.get("name_kz"))
            or f"Kazakhstan procurement announcement {number}"
        )

        amount = _float_or_none(
            raw.get("total_sum")
        )

        organizer_bin = _clean_text(
            raw.get("org_bin")
        )

        customer = None

        if organizer_bin:
            customer = f"Organizer BIN {organizer_bin}"

        name_kz = _clean_text(
            raw.get("name_kz")
        )

        summary = None

        if (
            name_kz
            and name_kz.casefold() != title.casefold()
        ):
            summary = name_kz

        notices.append(
            TenderNotice(
                source=source_name,
                external_id=advert_id[:500],
                title=title[:1000],
                url=_announcement_url(
                    advert_id
                )[:2000],
                published_at=_normalize_datetime(
                    raw.get("publish_date")
                ),
                tender_number=number[:500],
                customer=customer,
                initial_price=amount,
                currency=(
                    "KZT"
                    if amount is not None
                    else None
                ),
                deadline=_normalize_datetime(
                    raw.get("end_date")
                ),
                region=None,
                summary=(
                    summary[:4000]
                    if summary
                    else None
                ),
            )
        )

    return notices


def _next_page_url(value: Any) -> str | None:
    next_page = _clean_text(value)

    if not next_page:
        return None

    candidate = urljoin(
        KZ_GOSZAKUP_API_BASE_URL + "/",
        next_page,
    )

    parsed = urlparse(candidate)

    if (
        parsed.scheme != "https"
        or parsed.netloc != "ows.goszakup.gov.kz"
        or parsed.path not in {
            "/trd-buy",
            "/trd-buy/",
        }
    ):
        raise SourceError(
            "Kazakhstan procurement API returned "
            "an unsafe next_page URL."
        )

    return candidate


@dataclass(frozen=True)
class KazakhstanGoszakupApiSource:
    """Kazakhstan public procurement announcements."""

    api_token: str
    timeout: float = 30.0
    name: str = "kz_goszakup"

    def __post_init__(self) -> None:
        if not self.api_token.strip():
            raise ValueError(
                "Kazakhstan procurement API token "
                "must not be empty."
            )

        if self.timeout <= 0 or self.timeout > 120:
            raise ValueError(
                "timeout must be between 0 and 120 seconds."
            )

    async def fetch(
        self,
        limit: int = 20,
    ) -> list[TenderNotice]:
        requested_limit = max(
            1,
            min(
                int(limit),
                100,
            ),
        )

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": (
                f"Bearer {self.api_token}"
            ),
            "User-Agent": (
                "VALYQON-AI (+procurement-source)"
            ),
        }

        next_url: str | None = (
            KZ_GOSZAKUP_ANNOUNCEMENTS_URL
        )

        visited_urls: set[str] = set()
        notices_by_id: dict[
            tuple[str, str],
            TenderNotice,
        ] = {}

        page_count = 0

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                trust_env=True,
                headers=headers,
            ) as client:
                while (
                    next_url
                    and len(notices_by_id)
                    < requested_limit
                ):
                    if next_url in visited_urls:
                        raise SourceError(
                            "Kazakhstan procurement API "
                            "repeated next_page URL."
                        )

                    if page_count >= _MAX_PAGES:
                        raise SourceError(
                            "Kazakhstan procurement API "
                            "exceeded the safe page limit."
                        )

                    visited_urls.add(next_url)
                    page_count += 1

                    response = await client.get(
                        next_url
                    )

                    response.raise_for_status()

                    if (
                        len(response.content)
                        > _MAX_RESPONSE_BYTES
                    ):
                        raise SourceError(
                            "Kazakhstan procurement API "
                            "response exceeds the safe "
                            "10 MiB limit."
                        )

                    try:
                        payload = response.json()
                    except ValueError:
                        raise SourceError(
                            "Kazakhstan procurement API "
                            "returned invalid JSON."
                        ) from None

                    if not isinstance(
                        payload,
                        dict,
                    ):
                        raise SourceError(
                            "Kazakhstan procurement API "
                            "returned an invalid JSON object."
                        )

                    page_notices = (
                        parse_kz_goszakup_response(
                            payload,
                            source_name=self.name,
                        )
                    )

                    for notice in page_notices:
                        previous = notices_by_id.get(
                            notice.identity
                        )

                        if (
                            previous is not None
                            and previous != notice
                        ):
                            raise SourceError(
                                "Kazakhstan procurement API "
                                "returned conflicting "
                                "duplicate announcement IDs."
                            )

                        notices_by_id[
                            notice.identity
                        ] = notice

                        if (
                            len(notices_by_id)
                            >= requested_limit
                        ):
                            break

                    if (
                        len(notices_by_id)
                        >= requested_limit
                    ):
                        break

                    next_url = _next_page_url(
                        payload.get("next_page")
                    )

        except SourceError:
            raise
        except (httpx.HTTPError, OSError):
            # Never expose request headers because Authorization
            # contains the official API bearer token.
            raise SourceError(
                "Unable to fetch Kazakhstan "
                "procurement announcements."
            ) from None

        return list(
            notices_by_id.values()
        )[:requested_limit]


__all__ = [
    "KZ_GOSZAKUP_API_BASE_URL",
    "KZ_GOSZAKUP_ANNOUNCEMENTS_URL",
    "KZ_GOSZAKUP_PUBLIC_ANNOUNCEMENT_BASE_URL",
    "KazakhstanGoszakupApiSource",
    "parse_kz_goszakup_response",
]
