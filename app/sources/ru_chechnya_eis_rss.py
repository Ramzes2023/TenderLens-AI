"""Chechen Republic 44-FZ EIS RSS: verified regional subset, opt-in only.

The operator supplies an RSS link COPIED from an EIS regional advanced search.
No undocumented region query IDs are guessed here.  Every returned notice also
needs independently visible regional evidence in the EIS notice itself.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .eis_rss import EisRssSource, SourceError, validate_eis_direct_urls
from .models import TenderNotice

SOURCE_KEY = "ru_chechnya_eis"
OFFICIAL_HOMEPAGE = "https://zakupki.gov.ru/"
REGION_NAME = "Чеченская Республика"

# EIS descriptions/metadata vary across years and grammatical cases.
# Title or free-text summary is NOT regional proof on its own.
_REGION = re.compile(
    r"(?:\bчеченск\w*\s+республик\w*\b|"
    r"\bреспублик\w*\s+чеченск\w*\b|"
    r"\bреспублик\w*\s+чечн\w*\b|"
    r"\bгрозн(?:ый|ого|ом|ому|ым)\b)",
    re.IGNORECASE,
)


def is_chechnya_notice(notice: TenderNotice) -> bool:
    """Require location or contracting-authority evidence; never infer from title."""
    return any(
        bool(_REGION.search(value))
        for value in (notice.region or "", notice.customer or "")
    )


def validate_chechnya_feed_urls(urls: tuple[str, ...]) -> None:
    if not urls or len(urls) > 5:
        raise ValueError("Chechnya EIS requires 1-5 operator-provided regional RSS URLs")
    # Enforce the HTTPS EIS host and exact feed endpoint, even for non-direct mode.
    validate_eis_direct_urls(urls, allow_extensionless_rss=True)
    for url in urls:
        query = parse_qs(urlsplit(url).query, keep_blank_values=True)
        if query.get("fz44") != ["on"] or query.get("fz223") == ["on"]:
            raise ValueError("Chechnya feed must explicitly request EIS 44-FZ")
        terms = " ".join(query.get("searchString", ()))
        # A regional customer filter is configured using the official EIS UI.
        # Some EIS versions use different geographic query keys, so a
        # Chechnya text query is also permitted. The notice-level gate is
        # mandatory in both cases.
        region_hint = any("chech" in k.lower() or "region" in k.lower()
                          or k in {"customerPlace", "deliveryPlace"}
                          for k in query)
        if not region_hint and not _REGION.search(terms):
            raise ValueError("Use the EIS regional advanced search RSS link, not a nationwide feed")


@dataclass(frozen=True)
class ChechnyaEisRssSource:
    urls: tuple[str, ...]
    timeout: float = 30.0
    ca_bundle_file: Path | None = None
    direct: bool = False
    system_trust: bool = False
    name: str = SOURCE_KEY

    def __post_init__(self):
        validate_chechnya_feed_urls(self.urls)
        if self.name != SOURCE_KEY:
            raise ValueError("Chechnya source identity must be stable")

    async def fetch(self, limit: int = 20) -> list[TenderNotice]:
        if not 1 <= int(limit) <= 100:
            raise ValueError("limit must be between 1 and 100")
        upstream = EisRssSource(
            urls=self.urls, timeout=self.timeout, ca_bundle_file=self.ca_bundle_file,
            name=self.name, direct=self.direct, system_trust=self.system_trust,
            allow_extensionless_rss=True,
        )
        # EIS emits a limited feed, not a paginated regional API. Inspect all
        # available entries before applying the requested output cap.
        notices = await upstream.fetch(limit=100)
        seen: set[str] = set()
        selected: list[TenderNotice] = []
        for notice in notices:
            if not is_chechnya_notice(notice):
                continue
            original_link = urlsplit(notice.url)
            numbers = parse_qs(original_link.query, keep_blank_values=True).get("regNumber", [])
            if (original_link.scheme != "https" or original_link.netloc != "zakupki.gov.ru"
                    or not original_link.path.startswith("/epz/order/notice/")
                    or original_link.fragment or len(numbers) != 1
                    or not re.fullmatch(r"[0-9]{19}", numbers[0])
                    or notice.tender_number != numbers[0]):
                # Never persist an ambiguous title-derived number as an EIS original.
                continue
            official_number = numbers[0]
            # RSS GUID can change when EIS republishes an amended notice.
            # A validated original number is the durable source identity, not
            # the feed item's publisher-local GUID or position in the feed.
            if official_number in seen:
                continue
            seen.add(official_number)
            enrichment = notice.enrichment
            if enrichment is not None:
                enrichment = {**enrichment, "external_id": official_number}
            selected.append(replace(
                notice, external_id=official_number, enrichment=enrichment,
            ))
            if len(selected) >= int(limit):
                break
        return selected
