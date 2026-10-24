"""RU operator queue: rigorous offline durable-job, auth scope and no false sources."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import JobRepository, JobService
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.ru_cycle import (
    RU_APPROVED_SOURCES, approved_ru_keys, enqueue_approved_ru,
)
from app.sources.ingestion import ConnectorSyncService, SYSTEM_SCOPE, validate_payload


def catalog(**flags):
    base = MonitoringSettings(False, 600, 20, 5, 12, (), None)
    return build_source_catalog(replace(base, **flags))


def queue(tmp_path, cat):
    db = Database(DatabaseSettings("", tmp_path / "approved-ru.sqlite"))
    repo = JobRepository(db)
    repo.initialize()
    return db, repo, ConnectorSyncService(JobService(repo), cat)


def test_only_ten_explicitly_verified_operator_sources_and_no_side_effects(tmp_path):
    assert RU_APPROVED_SOURCES == (
        "b2b_center", "lenobl_small_public", "nmck_native_public",
        "mikroton_tender", "south_ural_public", "stan_commercial_public",
        "kavkaz_rf_firstparty", "ru_samara_public_list",
        "ru_dagestan_public_list", "ru_ingushetia_fabrikant44",
    )
    cat = catalog()
    with pytest.raises(ValueError, match="No operator-approved"):
        approved_ru_keys(cat)
    db, jobs, service = queue(tmp_path, cat)
    try:
        with pytest.raises(ValueError, match="No operator-approved"):
            enqueue_approved_ru(service, cat)
        with db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM durable_jobs").fetchone()[0] == 0
    finally:
        db.close()


@pytest.mark.parametrize("flag,source", [
    ("b2b_center_enabled", "b2b_center"),
    ("lenobl_small_public_enabled", "lenobl_small_public"),
    ("nmck_native_public_enabled", "nmck_native_public"),
    ("mikroton_tender_enabled", "mikroton_tender"),
    ("south_ural_public_enabled", "south_ural_public"),
    ("stan_commercial_public_enabled", "stan_commercial_public"),
    ("kavkaz_rf_firstparty_enabled", "kavkaz_rf_firstparty"),
    ("ru_samara_public_list_enabled", "ru_samara_public_list"),
    ("ru_dagestan_public_list_enabled", "ru_dagestan_public_list"),
    ("ru_ingushetia_fabrikant44_enabled", "ru_ingushetia_fabrikant44"),
])
def test_each_russian_source_requires_individual_operator_enable(tmp_path, flag, source):
    cat = catalog(**{flag: True})
    db, jobs, service = queue(tmp_path, cat)
    try:
        when = datetime(2026, 10, 18, 13, 35, tzinfo=timezone.utc)
        assert approved_ru_keys(cat) == (source,)
        result = enqueue_approved_ru(service, cat, now=when)
        assert tuple(result) == (source,)
        current = jobs.get(result[source]["job_id"], scope=SYSTEM_SCOPE)
        assert current.state == "queued"
        assert current.payload["source_id"] == source
        assert current.payload["sync_window"] == "2026-10-18T13Z"
        validate_payload(current.payload, cat.registry)
        with db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM durable_jobs").fetchone()[0] == 1
    finally:
        db.close()


def test_ru_cycle_hourly_repeat_is_idempotent_then_next_hour_unique(tmp_path):
    cat = catalog(b2b_center_enabled=True, lenobl_small_public_enabled=True,
                  nmck_native_public_enabled=True, mikroton_tender_enabled=True,
                  south_ural_public_enabled=True, stan_commercial_public_enabled=True,
                  kavkaz_rf_firstparty_enabled=True,
                  ru_samara_public_list_enabled=True,
                  ru_dagestan_public_list_enabled=True,
                  ru_ingushetia_fabrikant44_enabled=True)
    db, jobs, service = queue(tmp_path, cat)
    try:
        start = datetime(2026, 10, 18, 13, 12, tzinfo=timezone.utc)
        first = enqueue_approved_ru(service, cat, now=start)
        same_hour = enqueue_approved_ru(service, cat, now=start + timedelta(minutes=42))
        next_hour = enqueue_approved_ru(service, cat, now=start + timedelta(hours=1))
        assert tuple(first) == RU_APPROVED_SOURCES
        assert {s: j["job_id"] for s, j in first.items()} == {
            s: j["job_id"] for s, j in same_hour.items()
        }
        assert all(first[key]["job_id"] != next_hour[key]["job_id"]
                   for key in RU_APPROVED_SOURCES)
        with db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM durable_jobs").fetchone()[0] == 20
            ids = {json.loads(row[0])["source_id"] for row in conn.execute(
                "SELECT payload_json FROM durable_jobs"
            )}
        assert ids == set(RU_APPROVED_SOURCES)
    finally:
        db.close()


def test_enabled_but_unverified_and_nonrussian_sources_never_queued(tmp_path):
    cat = catalog(
        kavkaz_rf_firstparty_enabled=True, south_ural_public_enabled=True,
        tektorg_public_enabled=True, gpb_etp_public_enabled=True,
        cis_md_elicitatie_enabled=True,
    )
    db, jobs, service = queue(tmp_path, cat)
    try:
        result = enqueue_approved_ru(service, cat)
        assert tuple(result) == ("south_ural_public", "kavkaz_rf_firstparty")
        with db.connect() as conn:
            rows = conn.execute("SELECT payload_json FROM durable_jobs").fetchall()
        assert {json.loads(row[0])["source_id"] for row in rows} == set(result)
        assert all(j["state"] == "queued" for j in result.values())
    finally:
        db.close()
