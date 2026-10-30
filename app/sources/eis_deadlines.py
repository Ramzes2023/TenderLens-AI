"""Conservative EIS RSS result deadline extraction, without invented timezones.

Only a literal result-specific closing date is accepted. Search form labels,
publication dates, and competing values must never become bid deadlines.
"""
from __future__ import annotations

import re
from datetime import datetime

_DATE_CLOCK = r"(?P<date>(?:0[1-9]|[12][0-9]|3[01])\.(?:0[1-9]|1[0-2])\.20[0-9]{2} (?:[01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9])?)"
_CLOSING = re.compile(
    r"(?:Дата\s+и\s+время\s+окончания\s+подачи\s+заявок"
    r"|Окончание\s+подачи\s+заявок"
    r"|Срок\s+окончания\s+подачи\s+заявок)\s*:\s*"
    + _DATE_CLOCK,
    re.IGNORECASE,
)


def result_deadline(description: object) -> str | None:
    if type(description) is not str or not description or len(description) > 100_000:
        return None
    # A search-form's terms are not notice evidence. EIS descriptions can
    # prefix the actual result with this explicit separator.
    marker = "Найденный результат:"
    text = description.split(marker, 1)[1] if marker in description else description
    found = [m.group("date") for m in _CLOSING.finditer(text)]
    if not found or len(set(found)) != 1:
        return None
    value = found[0]
    try:
        fmt = "%d.%m.%Y %H:%M:%S" if value.count(":") == 2 else "%d.%m.%Y %H:%M"
        datetime.strptime(value, fmt)
    except ValueError:
        return None
    # Keep the source's unzoned civil time as supplied, no claim of UTC/MSK.
    return value
