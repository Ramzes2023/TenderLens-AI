"""Offline V6 Telegram bridge audit contracts: zero sending and zero writes."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.monitoring.v6_bridge_readiness import (
    SOURCES, _keywords, audit_connections, audit_paths, main,
)

NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


def seed(source_path, customer_path, *, profile=None, samara_deadline="31.12.2026",
         finished=None, include_samara=True, missing_worker=None, active=True):
    source = sqlite3.connect(source_path)
    customer = sqlite3.connect(customer_path)
    source.executescript(
        "CREATE TABLE source_opportunities (source_id TEXT, notice_json TEXT, last_seen TEXT);"
        "CREATE TABLE durable_jobs (job_type TEXT, payload_json TEXT, state TEXT, "
        "result_json TEXT, finished_at TEXT, created_at TEXT);"
    )
    customer.executescript(
        "CREATE TABLE monitor_subscriptions (owner_user_id INTEGER, enabled INTEGER);"
        "CREATE TABLE monitor_seen (owner_user_id INTEGER, source TEXT, external_id TEXT);"
        "CREATE TABLE company_active (owner_user_id INTEGER, company_id INTEGER);"
        "CREATE TABLE company_workspaces "
        "(id INTEGER, owner_user_id INTEGER, profile_json TEXT);"
    )
    seen = NOW.isoformat()
    for n, name in enumerate(SOURCES):
        if name == missing_worker:
            continue
        source.execute("INSERT INTO durable_jobs VALUES (?,?,?,?,?,?)", (
            "connector.sync.v1", json.dumps({"source_id": name}), "succeeded",
            json.dumps({"accepted_count": 2}),
            (finished or NOW - timedelta(minutes=5)).isoformat(),
            (NOW - timedelta(minutes=10 + n)).isoformat(),
        ))
    if include_samara:
        source.execute("INSERT INTO source_opportunities VALUES (?,?,?)", (
            "ru_samara_public_list",
            json.dumps({
                "source": "ru_samara_public_list", "external_id": "12345678",
                "title": "Реальный формат тестовой закупки",
                "url": "https://webtorgi.samregion.ru/smallpurchases/GzwSP/NoticesGrid",
                "deadline": samara_deadline,
            }, ensure_ascii=False), seen,
        ))
    customer.execute("INSERT INTO monitor_subscriptions VALUES (?,1)", (10001,))
    if active:
        customer.execute("INSERT INTO company_active VALUES (?,?)", (10001, 5))
    if profile is None:
        profile = {"search_keywords": ["оборудование"], "product_keywords": []}
    customer.execute(
        "INSERT INTO company_workspaces VALUES (?,?,?)",
        (5, 10001, json.dumps(profile, ensure_ascii=False)),
    )
    source.commit()
    customer.commit()
    source.close()
    customer.close()


def test_readonly_candidate_and_no_database_change(tmp_path):
    a, b = tmp_path / "sources.sqlite", tmp_path / "customer.sqlite"
    seed(a, b)
    before = a.read_bytes(), b.read_bytes()
    result = audit_paths(a, b, now=NOW)
    assert result["read_only_candidate"] is True
    assert result["recent_successful_workers"] == 6
    assert result["safely_current_samara_list_rows"] == 1
    assert result["subscriptions_with_explicit_active_company_keywords"] == 1
    assert result["telegram_live_send_authorized"] is False
    assert (a.read_bytes(), b.read_bytes()) == before
    assert not any("chat" in key or "token" in key for key in result)


@pytest.mark.parametrize("profile", [
    {"search_keywords": [], "product_keywords": []},
    {"search_keywords": ["  "], "product_keywords": []},
    {"search_keywords": "unsafe string", "product_keywords": []},
    {"search_keywords": [42], "product_keywords": []},
    {"search_keywords": ["test"], "product_keywords": ["" ]},
])
def test_no_broadcast_without_strict_explicit_keywords(tmp_path, profile):
    a, b = tmp_path / "sources.sqlite", tmp_path / "customer.sqlite"
    seed(a, b, profile=profile)
    assert not audit_paths(a, b, now=NOW)["read_only_candidate"]


def test_missing_active_company_is_blocked(tmp_path):
    a, b = tmp_path / "sources.sqlite", tmp_path / "customer.sqlite"
    seed(a, b, active=False)
    result = audit_paths(a, b, now=NOW)
    assert result["active_subscriptions"] == 1
    assert result["subscriptions_with_explicit_active_company_keywords"] == 0
    assert not result["read_only_candidate"]


def test_samara_expired_deadline_is_blocked(tmp_path):
    a, b = tmp_path / "sources.sqlite", tmp_path / "customer.sqlite"
    seed(a, b, samara_deadline="01.01.2026")
    result = audit_paths(a, b, now=NOW)
    assert result["safely_current_samara_list_rows"] == 0
    assert not result["read_only_candidate"]


def test_missing_recent_worker_is_blocked(tmp_path):
    a, b = tmp_path / "sources.sqlite", tmp_path / "customer.sqlite"
    seed(a, b, missing_worker="lenobl_small_public")
    result = audit_paths(a, b, now=NOW)
    assert result["recent_successful_workers"] == 5
    assert not result["read_only_candidate"]


def test_stale_worker_is_blocked(tmp_path):
    a, b = tmp_path / "sources.sqlite", tmp_path / "customer.sqlite"
    seed(a, b, finished=NOW - timedelta(hours=3))
    assert not audit_paths(a, b, now=NOW)["read_only_candidate"]


def test_rejects_same_database_and_missing_inputs(tmp_path):
    a = tmp_path / "source.sqlite"
    a.write_bytes(b"not a database")
    with pytest.raises(ValueError):
        audit_paths(a, a, now=NOW)
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        audit_paths(a, tmp_path / "missing.sqlite", now=NOW)


def test_missing_schema_fails_closed(tmp_path):
    a, b = tmp_path / "sources.sqlite", tmp_path / "customer.sqlite"
    sqlite3.connect(a).close()
    sqlite3.connect(b).close()
    with pytest.raises(ValueError):
        audit_paths(a, b, now=NOW)


def test_cli_does_not_expose_user_profile_or_authorize_sending(tmp_path, capsys):
    a, b = tmp_path / "sources.sqlite", tmp_path / "customer.sqlite"
    seed(a, b, profile={"search_keywords": ["private-keyword-should-not-print"],
                        "product_keywords": []})
    assert main(["--sources-db", str(a), "--customer-db", str(b)]) in (0, 2)
    output = capsys.readouterr().out
    assert "private-keyword-should-not-print" not in output
    assert "10001" not in output
    assert "TELEGRAM_LIVE_SEND_AUTHORIZED=NO" in output
    assert "PRODUCTION_MODIFICATIONS=NONE" in output


def test_no_write_is_ever_allowed_even_from_in_memory_connection():
    source = sqlite3.connect(":memory:")
    customer = sqlite3.connect(":memory:")
    with pytest.raises(ValueError):
        audit_connections(source, customer, now=NOW)
    source.close()
    customer.close()
