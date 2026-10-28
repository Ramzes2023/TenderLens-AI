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


def eligible_published_deadline(source: str, raw: object, *, now: datetime) -> bool:
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Timezone-aware verification time required")
    now = now.astimezone(timezone.utc)
    if not isinstance(raw, str) or len(raw) > 48:
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
            r"20\\d{2}-\\d{2}-\\d{2}T(?:[01]\\d|2[0-3]):[0-5]\\d"
            r"(?::[0-5]\\d)?", raw)):
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
    try:
        timestamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    return timestamp.tzinfo is not None and timestamp.astimezone(timezone.utc) > now
