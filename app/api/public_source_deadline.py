"""Conservative current-date-only rule for first-party Kavkaz.RF originals.

A published deadline may have a calendar date but no documented timezone.
Never invent a UTC timestamp or pretend a time of day was published. To
safely call such a tender still open, require its date to be strictly after
the latest currently existing civil date on earth (UTC+14). This can omit
legitimate near-deadline tenders, but can never admit an expired local date.
Date-only support applies only to Kavkaz.RF and verified Lenobl originals;
other
adapters, which must supply timezone-aware timestamps.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re

DATE_ONLY_ALLOWED = frozenset({"kavkaz_rf_firstparty", "lenobl_small_public"})


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
    try:
        timestamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    return timestamp.tzinfo is not None and timestamp.astimezone(timezone.utc) > now
