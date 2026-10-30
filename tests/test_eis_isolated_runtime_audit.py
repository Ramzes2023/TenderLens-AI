"""Synthetic read-only EIS release evidence tests; no real remote queries."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.sources.eis_isolated_runtime_audit import audit, audit_path

NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


def environment(**changes):
    result = {
        "DATABASE_URL": "sqlite:////app/data/isolated-public-sources.sqlite3",
        "VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED": "true",
        "MONITORING_ENABLED": "false",
        "TELEGRAM_BOT_TOKEN": "",
        "VALYQON_EMAIL_MODE": "disabled",
        "VALYQON_RESTRICT_PAID_SOURCE_DETAILS": "true",
        "EIS_RSS_PUBLIC_ENABLED": "true",
        "EIS_223_PUBLIC_ENABLED": "true",
        "EIS_223_ENABLED": "true",
        "EIS_DIRECT_ENABLED": "true",
        "EIS_PROFILE_FEEDS_ENABLED": "false",
        "EIS_223_PROFILE_FEEDS_ENABLED": "false",
        "EIS_RSS_URLS": "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?fz44=on",
        "EIS_223_RSS_URLS": "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?fz223=on",
    }
    result.update(changes)
    return result


def database():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE source_opportunities("
        "source_id TEXT,external_id TEXT,notice_json TEXT,last_seen TEXT)")
    conn.execute(
        "CREATE TABLE durable_jobs(job_type TEXT,payload_json TEXT,"
        "state TEXT,finished_at INTEGER,result_json TEXT,created_at INTEGER)")
    return conn


def add(conn, *, source, now=NOW, good=True, state="succeeded",
        received=1, age_minutes=4):
    number = "0316300145126000012" if source == "eis" else "32616521305"
    path = ("/epz/order/notice/ea44/view/common-info.html"
            if source == "eis" else
            "/223/purchase/public/purchase/info/common-info.html")
    obj = {
        "source": source, "external_id": number, "tender_number": number,
        "title": "Поставка медицинского оборудования",
        "url": ("https://zakupki.gov.ru" if good else "https://evil.invalid")
        + path + "?regNumber=" + number,
        "deadline": "10.12.2026 19:45",
        "customer": "Госучреждение",
    }
    conn.execute("INSERT INTO source_opportunities VALUES(?,?,?,?)", (
        source, number, json.dumps(obj, ensure_ascii=False), now.isoformat()))
    conn.execute("INSERT INTO durable_jobs VALUES(?,?,?,?,?,?)", (
        "connector.sync.v1", json.dumps({"source_id": source}),
        state,
        int((now-timedelta(minutes=age_minutes)).timestamp()*1_000_000),
        json.dumps({"accepted_count": received}), 10000,
    ))


def test_both_independent_current_original_and_worker_receipt_required():
    db = database()
    try:
        add(db, source="eis")
        add(db, source="eis_223")
        result = audit(db, environment=environment(), now=NOW)
        assert result["local_candidate_ready"] is True
        assert set(result["sources"]) == {"eis","eis_223"}
        assert all(row["recent_canonical_open_previews"] == 1
                   and row["last_worker_job"] == "succeeded"
                   and row["local_ready"] for row in result["sources"].values())
        assert result["publisher_live_origin_proved"] is False
        assert result["public_https_caddy_routing_proved"] is False
        assert result["production_modified"] is False
    finally:
        db.close()


@pytest.mark.parametrize("change", [
    {"EIS_RSS_PUBLIC_ENABLED": "false"},
    {"EIS_223_PUBLIC_ENABLED": "false"},
    {"EIS_DIRECT_ENABLED": "false"},
    {"EIS_223_ENABLED": "false"},
    {"MONITORING_ENABLED": "true"},
    {"TELEGRAM_BOT_TOKEN": "unexpected"},
    {"EIS_RSS_URLS": "https://evil.invalid/epz/order/extendedsearch/rss.html?fz44=on"},
    {"EIS_RSS_URLS": "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?fz223=on"},
    {"EIS_223_RSS_URLS": "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?fz44=on"},
    {"EIS_PROFILE_FEEDS_ENABLED": "true"},
])
def test_invalid_environment_cannot_report_success(change):
    db = database()
    try:
        with pytest.raises(ValueError):
            audit(db, environment=environment(**change), now=NOW)
    finally:
        db.close()


def test_source_specific_job_or_original_failure_fails_closed():
    for mode in ("wrong_original","failed_job","no_accepted","old_job","old_source"):
        db = database()
        try:
            add(db, source="eis")
            params = {}
            if mode == "wrong_original":
                params["good"] = False
            elif mode == "failed_job":
                params["state"] = "failed"
            elif mode == "no_accepted":
                params["received"] = 0
            elif mode == "old_job":
                params["age_minutes"] = 200
            elif mode == "old_source":
                params["now"] = NOW-timedelta(hours=3)
            add(db, source="eis_223", **params)
            result = audit(db, environment=environment(), now=NOW)
            assert result["local_candidate_ready"] is False, mode
            assert result["sources"]["eis"]["local_ready"] is True
            assert result["sources"]["eis_223"]["local_ready"] is False
        finally:
            db.close()


def test_missing_db_is_not_created_by_read_only_audit(tmp_path):
    path = tmp_path / "missing.sqlite"
    with pytest.raises(sqlite3.Error):
        audit_path(path, environment=environment(), now=NOW)
    assert not path.exists()
