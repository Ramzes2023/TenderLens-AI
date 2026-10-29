"""Offline security and aggregation tests for the six-source *read-only* VPS audit."""
from datetime import datetime, timedelta, timezone
import json
import sqlite3

import pytest

from app.sources.isolated_runtime_audit import (
    SOURCE_FLAGS, _job_age_minutes, audit_connection, isolated_environment_valid,
)


def environment():
    return {
        "DATABASE_URL": "sqlite:////app/data/isolated-public-sources.sqlite3",
        "VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED": "true",
        "MONITORING_ENABLED": "false",
        "TELEGRAM_BOT_TOKEN": "",
        "VALYQON_EMAIL_MODE": "disabled",
        "VALYQON_RESTRICT_PAID_SOURCE_DETAILS": "true",
        **{flag: "true" for _, flag in SOURCE_FLAGS},
    }


def fixture_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE source_opportunities "
                 "(source_id TEXT, notice_json TEXT, last_seen TEXT)")
    conn.execute("CREATE TABLE durable_jobs "
                 "(job_type TEXT, payload_json TEXT, state TEXT, "
                 "finished_at BIGINT, result_json TEXT, created_at TEXT, "
                 "failure_code TEXT)")
    return conn


def test_six_sources_actual_sql_and_worker_status_without_exposing_notices():
    now = datetime(2026, 10, 28, 18, 0, tzinfo=timezone.utc)
    conn = fixture_conn()
    notice = {
        "source": "mikroton_tender", "title": "PRIVATE TEST BUYER CONTRACT",
        "deadline": (now + timedelta(days=2)).isoformat(),
        "external_id": "sensitive-private-native-id",
        "url": "https://example.invalid/private-original",
    }
    conn.execute("INSERT INTO source_opportunities VALUES(?,?,?)",
                 ("mikroton_tender", json.dumps(notice), now.isoformat()))
    conn.execute("INSERT INTO source_opportunities VALUES(?,?,?)",
                 ("stan_commercial_public", json.dumps(
                     {"source": "stan_commercial_public", "title": "expired",
                      "deadline": (now - timedelta(days=1)).isoformat()}),
                  now.isoformat()))
    conn.execute("INSERT INTO durable_jobs "
                 "(job_type,payload_json,state,finished_at,result_json,created_at) "
                 "VALUES(?,?,?,?,?,?)",
                 ("connector.sync.v1", json.dumps({"source_id": "mikroton_tender"}),
                  "succeeded", int(now.timestamp() * 1_000_000), json.dumps({"accepted_count": 1}),
                  now.isoformat()))
    data = audit_connection(conn, environment=environment(), now=now)
    assert len(data["sources"]) == 6
    assert data["enabled_count"] == 6
    assert data["stored_open_preview_count"] == 1
    assert data["sources"]["mikroton_tender"]["last_worker_job"] == "succeeded"
    assert data["sources"]["mikroton_tender"]["last_worker_accepted_count"] == 1
    assert data["sources"]["mikroton_tender"]["last_worker_age_minutes"] == 0.0
    assert data["sources"]["stan_commercial_public"]["recent_future_deadline_previews"] == 0
    encoded = json.dumps(data)
    assert "PRIVATE TEST BUYER CONTRACT" not in encoded
    assert "sensitive-private-native-id" not in encoded
    assert "example.invalid" not in encoded
    assert data["publisher_live_acceptance_proved_by_this_audit"] is False
    assert data["public_https_caddy_routing_proved_by_this_audit"] is False
    conn.close()


def test_invalid_isolation_or_notifications_fail_before_db_read():
    conn = fixture_conn()
    for change in (
        {"DATABASE_URL": "sqlite:////app/data/tenderlens.db"},
        {"VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED": "false"},
        {"MONITORING_ENABLED": "true"},
        {"TELEGRAM_BOT_TOKEN": "secret"},
        {"VALYQON_EMAIL_MODE": "resend"},
        {"VALYQON_RESTRICT_PAID_SOURCE_DETAILS": "false"},
    ):
        e = {**environment(), **change}
        assert not isolated_environment_valid(e)
        with pytest.raises(ValueError):
            audit_connection(conn, environment=e)
    conn.close()


def test_false_source_switch_and_invalid_datetime_are_rejected():
    conn = fixture_conn()
    now = datetime(2026, 10, 28, 18, tzinfo=timezone.utc)
    e = environment()
    e["RU_SAMARA_PUBLIC_LIST_ENABLED"] = "false"
    data = audit_connection(conn, environment=e, now=now)
    assert data["enabled_count"] == 5
    e["RU_SAMARA_PUBLIC_LIST_ENABLED"] = "YES"
    with pytest.raises(ValueError):
        audit_connection(conn, environment=e, now=now)
    with pytest.raises(ValueError):
        audit_connection(conn, environment=environment(),
                         now=datetime(2026, 10, 28, 18))
    conn.close()


def test_worker_age_is_real_microseconds_not_an_iso_text_clock():
    now = datetime(2026, 10, 29, 14, 0, tzinfo=timezone.utc)
    stamp = int(now.timestamp() * 1_000_000)
    assert _job_age_minutes(stamp - 300_000_000, now) == 5.0
    assert _job_age_minutes(stamp - 7_200_000_000, now) == 120.0
    for invalid in (None, True, 0, -5, 2**63, now.isoformat(),
                    str(stamp), stamp + 1_000_000):
        assert _job_age_minutes(invalid, now) is None


def test_real_sql_worker_clock_uses_integer_without_data_leakage():
    now = datetime(2026, 10, 29, 14, 0, tzinfo=timezone.utc)
    conn = fixture_conn()
    finished = int(now.timestamp() * 1_000_000) - 180_000_000
    conn.execute("INSERT INTO durable_jobs "
                 "(job_type,payload_json,state,finished_at,result_json,created_at) "
                 "VALUES(?,?,?,?,?,?)", (
        "connector.sync.v1", json.dumps({"source_id": "lenobl_small_public"}),
        "failed", finished, None, now.isoformat(),
    ))
    data = audit_connection(conn, environment=environment(), now=now)
    record = data["sources"]["lenobl_small_public"]
    assert record["last_worker_job"] == "failed"
    assert record["last_worker_age_minutes"] == 3.0
    assert record["last_worker_accepted_count"] is None
    assert data["publisher_live_acceptance_proved_by_this_audit"] is False
    assert data["production_changed"] is False
    conn.close()


def test_failure_code_from_real_lease_is_safe_class_only():
    now = datetime(2026, 10, 29, 14, 0, tzinfo=timezone.utc)
    conn = fixture_conn()
    for source, state, code in (
        ("lenobl_small_public", "failed", "handler_error"),
        ("ru_samara_public_list", "failed", "secret_failure_payload"),
        ("stan_commercial_public", "succeeded", None),
    ):
        conn.execute(
            "INSERT INTO durable_jobs "
            "(job_type,payload_json,state,finished_at,result_json,created_at,"
            "failure_code) VALUES(?,?,?,?,?,?,?)",
            ("connector.sync.v1", json.dumps({"source_id": source}),
             state, int(now.timestamp() * 1_000_000), None,
             int(now.timestamp() * 1_000_000), code),
        )
    result = audit_connection(conn, environment=environment(), now=now)
    assert result["sources"]["lenobl_small_public"]["last_worker_failure_code"] == "handler_error"
    assert result["sources"]["ru_samara_public_list"]["last_worker_failure_code"] == "unclassified"
    assert result["sources"]["stan_commercial_public"]["last_worker_failure_code"] is None
    assert "secret_failure_payload" not in json.dumps(result)
    assert result["production_changed"] is False
    conn.close()
