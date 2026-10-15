"""Offline operator-alert regression tests. Never contact Telegram or procurement sites."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import time

import pytest

from app.observability import operator_alerts as alerts


def snapshot(*, failed=0, expired=0, sources=None):
    return {"recent_failed_jobs": failed, "expired_worker_leases": expired,
            "source_last_seen_seconds": sources or {}}


def test_worker_failure_stale_and_http_growth():
    report = snapshot(failed=2, expired=1, sources={"ted": 90000, "world_bank": None, "eis": 10})
    http = {"status": "measured", "current_requests": 100, "current_5xx": 22,
            "previous_requests": 100, "previous_5xx": 2}
    keys = [key for key, _ in alerts.evaluate(report, http)]
    assert keys == ["worker_lease_expired", "jobs_recently_failed",
                    "source_stale:ted", "source_stale:world_bank", "http_5xx_growth"]


def test_empty_or_slow_source_is_only_a_freshness_warning():
    keys = alerts.evaluate(snapshot(sources={"ted": None}),
                           {"status": "not_configured"})
    assert len(keys) == 1 and keys[0][0] == "source_stale:ted"
    assert "no recent persisted opportunity evidence" in keys[0][1]
    assert not alerts.evaluate(snapshot(sources={"ted": 3600}),
                               {"status": "not_configured"})


@pytest.mark.parametrize("requests,errors,previous,old", [
    (19, 8, 50, 0), (100, 4, 100, 0), (100, 5, 100, 10),
    (100, 0, 100, 0),
])
def test_5xx_alert_needs_volume_errors_and_growth(requests, errors, previous, old):
    report = {"status": "measured", "current_requests": requests,
              "current_5xx": errors, "previous_requests": previous,
              "previous_5xx": old}
    assert not alerts.evaluate(snapshot(), report)


def test_caddy_json_log_two_windows(tmp_path):
    now = 1890000000.0
    p = tmp_path / "access.json"
    records = ([{"ts": now - 100, "status": 503} for _ in range(6)]
               + [{"ts": now - 150, "status": 200} for _ in range(25)]
               + [{"ts": now - 1200, "status": 500}]
               + [{"ts": now - 1400, "status": 200} for _ in range(30)]
               + [{"ts": now - 2200, "status": 502}])
    p.write_text("\n".join(json.dumps(x) for x in records) + "\n", encoding="utf-8")
    measured = alerts.inspect_http_log(str(p), now=now)
    assert measured == {"status": "measured", "current_requests": 31, "current_5xx": 6,
                        "previous_requests": 31, "previous_5xx": 1}
    assert alerts.evaluate(snapshot(), measured)[0][0] == "http_5xx_growth"
    assert alerts.inspect_http_log("", now=now) == {"status": "not_configured"}


def test_invalid_and_unavailable_log_does_not_claim_safety(tmp_path):
    path = tmp_path / "bad-log.json"
    path.write_text('{"ts": "2026-10-15", "status": "500"}\nnot-json\n[]', encoding="utf8")
    assert alerts.inspect_http_log(str(path))["current_requests"] == 0
    assert alerts.inspect_http_log(str(tmp_path / "missing")) == {"status": "unavailable"}
    assert alerts.inspect_http_log("https://example.test/logs") == {"status": "unavailable"}


class FakeCursor:
    def __init__(self, result):
        self.result = result

    def fetchone(self):
        return (self.result,)


class FakeConnection:
    def __init__(self):
        self.queries = []
        self.closed = False

    def execute(self, sql, params):
        self.queries.append((sql, params))
        if "state='failed'" in sql:
            return FakeCursor(3)
        if "lease_expires_at <=" in sql:
            return FakeCursor(1)
        if "source_id=?" in sql:
            return FakeCursor("2026-10-15T08:00:00+00:00" if params == ("ted",) else None)
        raise AssertionError("Unexpected SQL")

    def close(self):
        self.closed = True


def test_readonly_aggregates_and_source_validation():
    class DB:
        def __init__(self):
            self.conn = FakeConnection()

        def connect(self):
            return self.conn

    db = DB()
    now = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc).timestamp()
    result = alerts.inspect_database(db, ("ted", "empty"), now=now)
    assert result == {"recent_failed_jobs": 3, "expired_worker_leases": 1,
                      "source_last_seen_seconds": {"ted": 7200, "empty": None}}
    assert len(db.conn.queries) == 4 and db.conn.closed
    assert all(sql.strip().upper().startswith("SELECT ") for sql, _ in db.conn.queries)
    with pytest.raises(ValueError):
        alerts.inspect_database(DB(), ("ted';DROP TABLE",), now=now)


def test_telegram_send_is_explicit_and_redacts_http_failure(monkeypatch):
    requests = []
    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
    monkeypatch.setattr(alerts.request, "urlopen",
                        lambda req, timeout: (requests.append((req, timeout)) or Response()))
    alerts._telegram_send("1234567890:" + "A" * 30, "-123456789", "Safe alert")
    assert len(requests) == 1 and requests[0][0].get_method() == "POST"
    assert json.loads(requests[0][0].data)["text"] == "Safe alert"
    with pytest.raises(ValueError):
        alerts._telegram_send("invalid", "-123456789", "Hello")
    assert len(requests) == 1


def test_once_per_hour_state_tracks_only_codes(monkeypatch, tmp_path):
    output = []
    monkeypatch.setattr(alerts, "_telegram_send", lambda *args: output.append(args))
    state = tmp_path / "private.json"
    events = [("jobs_recently_failed", "Jobs failed")]
    at = 1890000000.0
    args = dict(token="synthetic", chat_id="synthetic", state_file=str(state))
    assert alerts._emit_once(events, **args, now=at) == 1
    assert alerts._emit_once(events, **args, now=at + 100) == 0
    assert alerts._emit_once(events, **args, now=at + 3601) == 1
    assert len(output) == 2
    persisted = json.loads(state.read_text("utf8"))
    assert set(persisted) == {"jobs_recently_failed"}
    assert "Jobs failed" not in state.read_text("utf8")
