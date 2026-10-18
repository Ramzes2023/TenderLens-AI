"""Operator-approved CIS refresh cycle: no network and no production effects."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import JobRepository, JobService
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.cis_cycle import APPROVED_CIS_SOURCES, approved_cis_keys, enqueue_approved_cis
from app.sources.ingestion import ConnectorSyncService, SYSTEM_SCOPE, validate_payload


def catalog(**flags):
    base = MonitoringSettings(False, 600, 20, 5, 12, (), None)
    return build_source_catalog(replace(base, **flags))


def queue(tmp_path, cat):
    db = Database(DatabaseSettings("", tmp_path / "approved-cis.sqlite"))
    repo = JobRepository(db)
    repo.initialize()
    return db, repo, ConnectorSyncService(JobService(repo), cat)


def test_no_approved_flags_means_no_jobs_and_no_queue_side_effects(tmp_path):
    cat = catalog()
    assert APPROVED_CIS_SOURCES == ("md_elicitatie", "az_azeristilik", "az_adif_small")
    with pytest.raises(ValueError, match="No operator-approved"):
        approved_cis_keys(cat)
    db, jobs, service = queue(tmp_path, cat)
    try:
        with pytest.raises(ValueError, match="No operator-approved"):
            enqueue_approved_cis(service, cat)
        with db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM durable_jobs").fetchone()[0] == 0
    finally:
        db.close()


@pytest.mark.parametrize("flag,source", [
    ("cis_md_elicitatie_enabled", "md_elicitatie"),
    ("cis_az_azeristilik_enabled", "az_azeristilik"),
    ("cis_az_adif_small_enabled", "az_adif_small"),
])
def test_each_source_independently_approved_and_validated(tmp_path, flag, source):
    cat = catalog(**{flag: True})
    db, jobs, service = queue(tmp_path, cat)
    try:
        when = datetime(2026, 10, 18, 13, 35, tzinfo=timezone.utc)
        assert approved_cis_keys(cat) == (source,)
        result = enqueue_approved_cis(service, cat, now=when)
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


def test_three_source_hourly_dedupe_and_next_hour_enqueue(tmp_path):
    cat = catalog(cis_md_elicitatie_enabled=True, cis_az_azeristilik_enabled=True,
                  cis_az_adif_small_enabled=True)
    db, repo, service = queue(tmp_path, cat)
    try:
        t = datetime(2026, 10, 18, 13, 12, tzinfo=timezone.utc)
        first = enqueue_approved_cis(service, cat, now=t)
        again = enqueue_approved_cis(service, cat, now=t + timedelta(minutes=42))
        next_hour = enqueue_approved_cis(service, cat, now=t + timedelta(hours=1))
        assert tuple(first) == APPROVED_CIS_SOURCES
        assert {s: j["job_id"] for s, j in first.items()} == {s: j["job_id"] for s, j in again.items()}
        assert all(next_hour[s]["job_id"] != first[s]["job_id"] for s in APPROVED_CIS_SOURCES)
        with db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM durable_jobs").fetchone()[0] == 6
            assert conn.execute(
                "SELECT COUNT(DISTINCT json_extract(payload_json,'$.source_id')) FROM durable_jobs"
            ).fetchone()[0] == 3
    finally:
        db.close()


def test_operator_cycle_cannot_enqueue_other_enabled_cis_or_russian_sources(tmp_path):
    cat = catalog(cis_md_elicitatie_enabled=True, south_ural_public_enabled=True)
    db, jobs, service = queue(tmp_path, cat)
    try:
        result = enqueue_approved_cis(
            service, cat, now=datetime(2026, 10, 18, 14, tzinfo=timezone.utc))
        assert tuple(result) == ("md_elicitatie",)
        with db.connect() as conn:
            rows = conn.execute("SELECT payload_json FROM durable_jobs").fetchall()
        assert len(rows) == 1
        assert json.loads(rows[0][0])["source_id"] == "md_elicitatie"
    finally:
        db.close()
