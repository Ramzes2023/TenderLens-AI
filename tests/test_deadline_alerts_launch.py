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

def test_no_unsafe_original_url_in_notification():
    assert safe_official_url("javascript:alert(1)") == ""
    assert safe_official_url("https://example.com:8443/bid") == ""
    assert safe_official_url("https://example.com/bid") == "https://example.com/bid"
