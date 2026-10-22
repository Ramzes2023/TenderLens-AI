"""Offline-only proof of explicitly authorized hourly regional queue admission.

No network, bot, production, recurring task or listener is started in tests.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import JobRepository, JobService
from app.jobs.models import JobScope
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import ConnectorSyncService
from scripts.ru_ingushetia_hourly_enqueue import (
    APPROVAL, SOURCES, enabled_ingushetia_keys, queue_if_new_hour, main,
)


def catalog(**switches):
    options = MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=20,
        max_notifications_per_cycle=5, request_timeout=20,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        **switches,
    )
    return build_source_catalog(options)


def test_default_off_and_nonregional_russian_flags_cannot_enqueue():
    assert len(SOURCES) == 2
    with pytest.raises(ValueError, match="No explicitly enabled Ingushetia"):
        enabled_ingushetia_keys(catalog())
    with pytest.raises(ValueError, match="No explicitly enabled Ingushetia"):
        enabled_ingushetia_keys(catalog(b2b_center_enabled=True))
    assert enabled_ingushetia_keys(catalog(
        ru_ingushetia_eis44_enabled=True,
    )) == ("ru_ingushetia_eis44",)
    assert enabled_ingushetia_keys(catalog(
        ru_ingushetia_fabrikant44_enabled=True,
    )) == ("ru_ingushetia_fabrikant44",)


def test_explicit_regional_hourly_enqueue_uses_existing_durable_utc_job_fencing(tmp_path):
    cat = catalog(
        b2b_center_enabled=True,  # must never be enqueued by regional scheduler
        ru_ingushetia_eis44_enabled=True,
        ru_ingushetia_fabrikant44_enabled=True,
    )
    db = Database(DatabaseSettings("regional-hourly-test", tmp_path / "hourly.sqlite"))
    jobs = JobRepository(db)
    jobs.initialize()
    service = ConnectorSyncService(JobService(jobs), cat)
    try:
        now = datetime(2026, 10, 22, 15, 3, tzinfo=timezone.utc)
        w0, first = queue_if_new_hour(service, cat, now=now)
        assert tuple(first) == SOURCES and w0 == "2026-10-22T15Z"
        assert all(j["state"] == "queued" for j in first.values())
        for k, item in first.items():
            row = jobs.get(item["job_id"], scope=JobScope())
            assert row.payload["source_id"] == k
            assert row.payload["sync_window"] == w0

        w1, noop = queue_if_new_hour(service, cat, now=now + timedelta(minutes=35),
                                     previous_window=w0)
        assert w1 == w0 and noop == {}

        # Starting a new scheduler process in the same UTC hour is still
        # idempotent against the actual database, not only in-memory state.
        _, again = queue_if_new_hour(service, cat, now=now + timedelta(minutes=45))
        assert {key: j["job_id"] for key, j in first.items()} == {
            key: j["job_id"] for key, j in again.items()
        }

        w2, later = queue_if_new_hour(service, cat, now=now + timedelta(hours=1),
                                      previous_window=w1)
        assert w2 == "2026-10-22T16Z" and tuple(later) == SOURCES
        assert all(later[k]["job_id"] != first[k]["job_id"] for k in SOURCES)
        with db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM durable_jobs").fetchone()[0] == 4
    finally:
        db.close()


def test_naive_schedule_clock_rejected_and_auth_missing_means_zero_db_access(
        monkeypatch, capsys,
):
    with pytest.raises(ValueError, match="UTC-aware"):
        queue_if_new_hour(object(), catalog(ru_ingushetia_eis44_enabled=True),
                          now=datetime(2026, 10, 22, 15, 0))

    monkeypatch.delenv("VALYQON_INGUSHETIA_QUEUE_APPROVED", raising=False)
    assert main(["--once", "--authorize-queue-only"]) == 2
    assert "EXPLICIT_APPROVAL_REQUIRED=YES" in capsys.readouterr().out
    monkeypatch.setenv("VALYQON_INGUSHETIA_QUEUE_APPROVED", APPROVAL)
    assert main(["--once"]) == 2
    assert "EXPLICIT_APPROVAL_REQUIRED=YES" in capsys.readouterr().out
