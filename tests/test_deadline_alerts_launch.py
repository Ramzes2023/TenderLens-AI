from datetime import datetime, timezone, timedelta
import pytest
from app.launch.deadline_alerts import aware_deadline, due_lead_hours, safe_official_url

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)

def test_only_precise_aware_future_deadlines_trigger():
    assert due_lead_hours("2026-10-19T12:00:00+00:00", now=NOW) == 48
    assert due_lead_hours("2026-10-20T12:00:00+00:00", now=NOW) is None
    assert due_lead_hours("2026-10-17T12:00:00+00:00", now=NOW) is None
    assert due_lead_hours("2026-10-18", now=NOW) is None
    assert due_lead_hours("2026-10-18T12:00:00", now=NOW) is None
    assert due_lead_hours("2026-10-18T12:00:00+03:00", now=NOW) == 48

def test_moscow_time_is_supported_only_when_explicit():
    assert aware_deadline("19.10.2026 14:00 МСК") == datetime(
        2026, 10, 19, 11, 0, tzinfo=timezone.utc
    )
    assert aware_deadline("19.10.2026 14:00 (MSK)") == datetime(
        2026, 10, 19, 11, 0, tzinfo=timezone.utc
    )
    assert due_lead_hours("19.10.2026 14:00 МСК", now=NOW) == 48
    for ambiguous in (
        "19.10.2026 14:00", "19.10.2026", "32.10.2026 14:00 МСК",
        "19.10.2026 25:00 МСК", "19.10.2026 14:00 МСК 2026-10-19",
        "19.10.2026 14:00 UTC", "19.10.2026 14:00 +03:00",
    ):
        assert aware_deadline(ambiguous) is None


def test_no_unsafe_original_url_in_notification():
    assert safe_official_url("javascript:alert(1)") == ""
    assert safe_official_url("https://example.com:8443/bid") == ""
    assert safe_official_url("https://example.com/bid") == "https://example.com/bid"
