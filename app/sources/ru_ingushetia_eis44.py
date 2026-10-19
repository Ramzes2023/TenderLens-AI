"""Strict opt-in EIS 44-FZ discovery for the Republic of Ingushetia.

The regional RSS query parameter is a *candidate*, not proof of scope.
Only notices whose own EIS metadata corroborates Ingushetia are accepted.
A live CI job must establish that this candidate is actually populated.
Do not count these as a second independent publication beside EIS.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

from .eis_rss import EIS_EXTENDED_RSS_URL, EisRssSource, SourceError
from .models import TenderNotice
from .opportunities import validate_notice

SOURCE_ID = "ru_ingushetia_eis44"
REGION = "Республика Ингушетия"
# This filter must be verified against the genuine live EIS response by CI.
RSS_URL = EIS_EXTENDED_RSS_URL + "?fz44=on&regions=06&pageNumber=1"
_NUMBER = re.compile(r"[0-9]{19}\Z")
_REGION = re.compile(r"\bингушети(?:я|и|ю|ей)\b", re.I)


def normalize_ingushetia_notice(notice: TenderNotice) -> TenderNotice | None:
    """Fail closed on unproven origin/law; skip records without regional proof."""
    if not isinstance(notice, TenderNotice) or notice.source != SOURCE_ID:
        raise SourceError("Ingushetia requires its own EIS 44-FZ notice")
    number = notice.tender_number
    parts = urlsplit(notice.url)
    args = parse_qs(parts.query, keep_blank_values=True)
    if (
        type(number) is not str
        or not _NUMBER.fullmatch(number)
        or parts.scheme != "https"
        or parts.netloc != "zakupki.gov.ru"
        or not parts.path.startswith("/epz/order/notice/")
        or set(args) != {"regNumber"}
        or args["regNumber"] != [number]
        or parts.fragment
    ):
        raise SourceError("Ingushetia original 44-FZ identity was not verified")
    # Never infer the buyer's region from a search URL, tender title,
    # procedure prefix or vendor catalog. Require first-party RSS fields.
    evidence = " ".join(filter(None, (notice.customer, notice.region)))
    if not _REGION.search(evidence):
        return None
    result = replace(notice, external_id=number, region=REGION, enrichment=None)
    validate_notice(result, SOURCE_ID)
    return result


@dataclass(frozen=True)
class IngushetiaEis44Source:
    timeout: float = 25
    ca_bundle_file: Path | None = None
    system_trust: bool = False
    name: str = SOURCE_ID

    async def fetch(self, limit: int = 20) -> list[TenderNotice]:
        if self.name != SOURCE_ID or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid Ingushetia source settings")
        # Fetch up to 100 official 44-FZ entries so strict scope checks
        # do not silently accept the first unrelated national results.
        upstream = EisRssSource(
            urls=(RSS_URL,), timeout=self.timeout, name=SOURCE_ID,
            direct=True, system_trust=self.system_trust,
            ca_bundle_file=self.ca_bundle_file,
        )
        items = await upstream.fetch(limit=100)
        verified: list[TenderNotice] = []
        seen: set[str] = set()
        for original in items:
            item = normalize_ingushetia_notice(original)
            if item is None:
                continue
            if item.external_id not in seen:
                verified.append(item)
                seen.add(item.external_id)
            if len(verified) >= limit:
                break
        return verified
