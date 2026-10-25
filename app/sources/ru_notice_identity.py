"""Conservative Russian upstream notice identity for cross-platform audit only.

This is a PURE classifier, not a replacement for (source, external_id) storage.
A marketplace copy of a public EIS notice must not inflate the count of
independent original Russian procurement publications. When original identity
cannot be corroborated, keep source-local keys; never invent EIS numbers.
"""
from __future__ import annotations

import re
from app.sources.models import TenderNotice

_EIS_44 = re.compile(r"[0-9]{19}\Z")
_EIS_223 = re.compile(r"3[0-9]{10}\Z")
_SOURCE_KEY = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")

# Only sources that explicitly identify the EIS original in their own
# adapter contract. Non-EIS platform number formats are never reclassified.
_EIS_44_ORIGINAL = frozenset({"eis", "eis_44_html", "fabrikant_44_public", "ru_ingushetia_fabrikant44"})
_EIS_223_ORIGINAL = frozenset({"eis", "eis_223"})

def original_notice_key(notice: TenderNotice) -> tuple[str, str]:
    """Return stable, conservative original-publication identity.

    This never removes records or asserts that any feed was verified or active.
    EIS originals have trusted 44-FZ (19 digit) or 223-FZ (11 digit) number
    only for approved adapters. Otherwise preserve local source namespace.
    """
    if type(notice) is not TenderNotice:
        # Subclasses may introduce legal provenance; validate subclass
        # through isinstance without allowing arbitrary objects.
        if not isinstance(notice, TenderNotice):
            raise TypeError("TenderNotice required")
    source = notice.source
    external_id = notice.external_id
    if (type(source) is not str or not _SOURCE_KEY.fullmatch(source)
            or type(external_id) is not str or not external_id
            or external_id != external_id.strip()
            or len(external_id) > 500 or "\x00" in external_id):
        raise ValueError("Invalid conservative notice identity")
    original = notice.tender_number
    if original is None:
        original = external_id
    if type(original) is not str:
        raise ValueError("Non-string upstream number")
    number = original.strip()
    # Distinct source external_id can be a publisher-local surrogate,
    # but trusted EIS original is always an explicit tender_number.
    if source in _EIS_44_ORIGINAL and _EIS_44.fullmatch(number):
        return ("eis_44", number)
    if source in _EIS_223_ORIGINAL and _EIS_223.fullmatch(number):
        return ("eis_223", number)
    return (source, external_id)


def distinct_original_count(notices) -> dict[str, int]:
    """Audit counts, not active-source health: no network or persistence."""
    seen = set()
    source_keys = set()
    total = 0
    for notice in notices:
        key = original_notice_key(notice)
        total += 1
        source_keys.add(notice.source)
        seen.add(key)
    return {
        "record_count": total,
        "adapter_key_count": len(source_keys),
        "original_notice_count": len(seen),
        "cross_source_duplicate_count": total - len(seen),
    }
