"""Public EIS result identity gate; no upstream HTTP and no tenant data.

A stored record is not proof of live delivery, but its canonical official
identity must be checked before the isolated anonymous preview can show it.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

_EIS_44 = re.compile(r"/epz/order/notice/[a-z0-9-]{2,24}/view/common-info\.html")
_EIS_223 = re.compile(r"/223/purchase/public/purchase/[a-z0-9/-]{1,130}\.html")
_NUM_44 = re.compile(r"[0-9]{18,20}")
_NUM_223 = re.compile(r"[0-9]{11,20}")


def accepted_eis_original(notice: object) -> bool:
    """Fail closed for spoofed host, law, regNumber and unsupported URLs."""
    if not isinstance(notice, dict):
        return False
    source = notice.get("source")
    if source not in {"eis", "eis_223", "eis_44_html"}:
        return False
    number = notice.get("tender_number")
    raw = notice.get("url")
    if type(number) is not str or type(raw) is not str or len(raw) > 2000:
        return False
    expected_number = _NUM_223 if source == "eis_223" else _NUM_44
    if not expected_number.fullmatch(number):
        return False
    try:
        parts = urlsplit(raw)
        query = parse_qs(parts.query, keep_blank_values=True)
        if (parts.scheme != "https" or parts.netloc != "zakupki.gov.ru"
                or parts.fragment or "\\" in raw
                or set(query) != {"regNumber"} or query["regNumber"] != [number]):
            return False
        if source == "eis_223":
            if not _EIS_223.fullmatch(parts.path):
                return False
        elif not _EIS_44.fullmatch(parts.path):
            return False
        if source == "eis_44_html" and notice.get("external_id") != number:
            return False
    except (ValueError, TypeError, KeyError):
        return False
    return True
