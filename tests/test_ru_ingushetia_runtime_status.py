"""Offline contracts for observational Ingushetia runtime freshness.

No real network, Telegram send, queue, production write, or source opt-in.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from pathlib import Path

import pytest

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.sources.ingestion import connector_version
from app.sources.models import TenderNotice
from app.sources.opportunities import OpportunityRepository
from scripts.ru_ingushetia_runtime_status import snapshot_health, main

EIS = "ru_ingushetia_eis44"
FAB = "ru_ingushetia_fabrikant44"
N = "0114500000826002472"


def settings(*, eis=True, fab=False, monitor=True, catalog=True, sql=True):
    return SimpleNamespace(
        ru_ingushetia_eis44_enabled=eis,
        ru_ingushetia_fabrikant44_enabled=fab,
        enabled=monitor,
        ru_background_catalog_enabled=catalog,
        ru_ingushetia_worker_sql_alerts_enabled=sql,
    )


def notice(source=EIS, number=N):
    return TenderNotice(
        source=source, external_id=number, tender_number=number,
        title="Поставка лекарственных средств",
        customer="Комитет госзаказа Республики Ингушетия",
        region="Республика Ингушетия",
        url=("https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber="
             if source == EIS else "https://44.fabrikant.ru/44/procedure/ea21/") + number,
    )


def test_no_optin_or_missing_monitor_flags_are_not_ready():
    class NoRead:
        def latest_seen_utc(self, source):
            raise AssertionError("No source should be queried if it is disabled")

    report = snapshot_health(settings(eis=False), NoRead())
    assert report["source_states"] == {}
    assert report["source_enabled_count"] == 0
    assert report["status"] == "NOT_OPERATIONALLY_READY"
    assert report["production_changed"] is False

    for mode in ("monitor", "catalog", "sql"):
        class Fake:
            def latest_seen_utc(self, source):
                return datetime.now(timezone.utc)
            def read(self, *args, **kwargs):
                return [notice()]
        opts = {"monitor": True, "catalog": True, "sql": True}
        opts[mode] = False
        result = snapshot_health(settings(**opts), Fake())
        assert result["status"] == "NOT_OPERATIONALLY_READY"
        assert result["source_states"] == {EIS: "RECENT_SQL_OBSERVED"}
        assert result["telegram_bot_api_receipt_proven"] is False
        assert result["current_upstream_reachability_proven"] is False


def test_real_disposable_sqlite_records_are_fresh_but_not_live_telegram(tmp_path):
    db = Database(DatabaseSettings("ing-runtime", tmp_path / "worker.sqlite"))
    repo = OpportunityRepository(db)
    repo.initialize()
    try:
        before = datetime.now(timezone.utc)
        repo.upsert(notice(EIS), connector_version(EIS))
        result = snapshot_health(settings(eis=True, fab=True), repo)
        assert result["source_states"][EIS] == "RECENT_SQL_OBSERVED"
        assert result["source_states"][FAB] == "SQL_ABSENT"
        assert result["status"] == "NOT_OPERATIONALLY_READY"

        repo.upsert(notice(FAB), connector_version(FAB))
        healthy = snapshot_health(settings(eis=True, fab=True), repo)
        assert healthy["status"] == "SQL_SNAPSHOT_OBSERVED_ONLY"
        assert healthy["source_states"] == {
            EIS: "RECENT_SQL_OBSERVED", FAB: "RECENT_SQL_OBSERVED",
        }
        assert healthy["telegram_bot_api_receipt_proven"] is False
        assert healthy["current_upstream_reachability_proven"] is False
        # The snapshot observer is read-only: no queue or monitoring tables.
        with db.connect() as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM source_opportunities"
            ).fetchone()[0] == 2
    finally:
        db.close()


@pytest.mark.parametrize("age_seconds,expected", [
    (-3600 * 4, "SQL_STALE"),
    (3600, "SQL_CLOCK_SKEW"),
])
def test_old_and_future_worker_observations_fail_closed(age_seconds, expected):
    now = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
    class Repo:
        def latest_seen_utc(self, source):
            assert source == EIS
            return now + timedelta(seconds=age_seconds)
        def read(self, *args, **kwargs):
            raise AssertionError("An old/future record must not be read")
    report = snapshot_health(settings(), Repo(), now=now)
    assert report["status"] == "NOT_OPERATIONALLY_READY"
    assert report["source_states"][EIS] == expected


def test_unknown_database_exception_is_redacted_and_never_proves_ready():
    class Broken:
        def latest_seen_utc(self, source):
            raise RuntimeError("password=NEVER_PRINT")
    result = snapshot_health(settings(), Broken())
    assert result["source_states"][EIS] == "SQL_UNAVAILABLE"
    assert "NEVER_PRINT" not in str(result)


def test_read_only_cli_requires_explicit_flag_and_must_not_open_database(monkeypatch, capsys):
    import sys
    import app.database.backend as backend

    def fatal(*args, **kwargs):
        raise AssertionError("No database construction or network access allowed")

    monkeypatch.setattr(backend, "Database", fatal)
    assert main([]) == 2
    assert "EXPLICIT_READ_ONLY_FLAG_REQUIRED" in capsys.readouterr().out


def test_non_utc_clock_rejected_without_querying_repository():
    with pytest.raises(ValueError, match="UTC-aware"):
        snapshot_health(settings(), object(), now=datetime(2026, 10, 22, 12))
    with pytest.raises(ValueError, match="UTC-aware"):
        snapshot_health(settings(), object(),
                        now=datetime(2026, 10, 22, 14,
                                     tzinfo=timezone(timedelta(hours=2))))
