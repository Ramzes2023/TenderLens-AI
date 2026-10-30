"""Conservative current dates for verified first-party Kavkaz.RF and Lenobl.

The Kavkaz.RF original provides only a civil DATE. Lenobl provides an
exact native DATE+TIME but no independently documented timezone. Never
invent a UTC instant. An original local-clock deadline is safely open only
if it is later than current time even in the maximum legal UTC+14 offset.
All other adapters continue requiring timezone-aware ISO timestamps.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re

DATE_ONLY_ALLOWED = frozenset({"kavkaz_rf_firstparty"})
NAIVE_CLOCK_ALLOWED = frozenset({"lenobl_small_public"})
SAMARA_LIST_ONLY_SOURCE = "ru_samara_public_list"
EIS_RSS_SOURCES = frozenset({"eis", "eis_223"})
_SAMARA_DATE = re.compile(r"(?:0[1-9]|[12][0-9]|3[01])\.(?:0[1-9]|1[0-2])\.20[0-9]{2}")
_SAMARA_CLOCK = re.compile(
    r"(?:0[1-9]|[12][0-9]|3[01])\.(?:0[1-9]|1[0-2])\.20[0-9]{2} "
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9])?"
)
_SAMARA_ISO_SECONDS = re.compile(
    r"20[0-9]{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]"
)



def eligible_published_deadline(source: str, raw: object, *, now: datetime) -> bool:
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Timezone-aware verification time required")
    now = now.astimezone(timezone.utc)
    if not isinstance(raw, str) or len(raw) > 48:
        return False
    if source in EIS_RSS_SOURCES:
        # Official EIS result-level civil clock has NO independently attested
        # offset. Require a deadline later than even a UTC+14 wall clock,
        # rather than silently treating it as Moscow or UTC.
        match = re.fullmatch(
            r"(?:0[1-9]|[12][0-9]|3[01])\.(?:0[1-9]|1[0-2])\.20[0-9]{2} "
            r"(?:[01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9])?", raw)
        if match:
            try:
                fmt = "%d.%m.%Y %H:%M:%S" if raw.count(":") == 2 else "%d.%m.%Y %H:%M"
                closing = datetime.strptime(raw, fmt)
            except ValueError:
                return False
            return closing > (now + timedelta(hours=14)).replace(tzinfo=None)
    if source == SAMARA_LIST_ONLY_SOURCE:
        # Authentic first-party native JSON LIST fields, not a deep detail
        # page. Source uses Russian day.month.year, optionally a local clock
        # without publisher-attested time zone. Preserve that original
        # precision; never manufacture midnight, UTC or Moscow offset.
        max_local_now = now + timedelta(hours=14)
        try:
            if _SAMARA_DATE.fullmatch(raw):
                return datetime.strptime(raw, "%d.%m.%Y").date() > max_local_now.date()
            if _SAMARA_CLOCK.fullmatch(raw):
                fmt = "%d.%m.%Y %H:%M:%S" if raw.count(":") == 2 else "%d.%m.%Y %H:%M"
                closing = datetime.strptime(raw, fmt)
                return closing > max_local_now.replace(tzinfo=None)
            if _SAMARA_ISO_SECONDS.fullmatch(raw):
                closing = datetime.fromisoformat(raw)
                return closing > max_local_now.replace(tzinfo=None)
        except ValueError:
            return False
        return False
    if (source in DATE_ONLY_ALLOWED and
            re.fullmatch(r"20\d{2}-\d{2}-\d{2}", raw)):
        try:
            due = date.fromisoformat(raw)
        except ValueError:
            return False
        # A date tomorrow in UTC+14 is NOT safe: it could already be today
        # at the official publisher. Require strictly later.
        return due > (now + timedelta(hours=14)).date()
    if (source in NAIVE_CLOCK_ALLOWED and re.fullmatch(
            r"20\d{2}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d"
            r"(?::[0-5]\d)?", raw)):
        try:
            local_clock = datetime.fromisoformat(raw)
        except ValueError:
            return False
        # Without documented timezone, no possible UTC+14 locality
        # may have passed the official displayed closing clock already.
        latest_possible_local_clock = (
            now + timedelta(hours=14)
        ).replace(tzinfo=None)
        return local_clock > latest_possible_local_clock
    if source in NAIVE_CLOCK_ALLOWED:
        # This portal never supplied a timezone, nor a bare date-only
        # deadline: refuse any unsupported date/clock representation.
        return False
    try:
        timestamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    return timestamp.tzinfo is not None and timestamp.astimezone(timezone.utc) > now
