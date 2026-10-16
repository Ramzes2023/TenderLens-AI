"""Real Roseltorg listing -> independently checked detail -> worker -> isolated DB.

Exits nonzero unless *all* recorded records are searchable by external ID.
Never writes to a persistent or production database.
"""
import asyncio
import json
import tempfile
from pathlib import Path

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import HandlerRegistry, JobRepository, JobSettings
from app.jobs.models import JobScope
from app.jobs.worker import Worker
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import (ConnectorSyncHandler, ConnectorSyncService,
                                   JOB_TYPE, connector_version)
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog

SOURCE = "roseltorg_public"


def acceptance():
    catalog = build_source_catalog(MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=3,
        max_notifications_per_cycle=5, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        roseltorg_public_enabled=True,
    ))
    if SOURCE not in catalog.enabled_keys:
        raise AssertionError("Roseltorg source not enabled in isolated catalog")
    with tempfile.TemporaryDirectory(prefix="valyqon-ru-roseltorg-") as d:
        db = Database(DatabaseSettings("ru-roseltorg-live", Path(d) / "proof.sqlite"))
        try:
            jobs = JobRepository(db, JobSettings(lease_seconds=240, heartbeat_seconds=10))
            jobs.initialize()
            store = OpportunityRepository(db)
            store.initialize()
            handler = ConnectorSyncHandler(catalog, store, max_records=3)
            queued = ConnectorSyncService(jobs, catalog).enqueue(SOURCE)
            handlers = HandlerRegistry()
            handlers.register(JOB_TYPE, handler)
            if not Worker(jobs, handlers, job_types=(JOB_TYPE,)).run_once():
                raise AssertionError("Roseltorg job was not claimed by durable worker")
            completed = jobs.get(queued.id, scope=JobScope())
            if completed is None or completed.state != "succeeded":
                raise AssertionError("Roseltorg durable worker did not succeed: "
                                     + str(completed.failure_code if completed else "missing"))
            stats = completed.result
            if not 1 <= stats["fetched_count"] <= 3:
                raise AssertionError("Roseltorg did not return real verified notices")
            if (stats["accepted_count"] != stats["fetched_count"]
                    or stats["inserted_count"] != stats["fetched_count"]
                    or stats["skipped_count"]):
                raise AssertionError("Roseltorg ingestion incomplete")
            stored = store.read(SOURCE, limit=3)
            if len(stored) != stats["fetched_count"]:
                raise AssertionError("SQL records missing")
            snapshot = snapshot_catalog(catalog, store)
            for notice in stored:
                if notice.url not in (
                    f"https://www.roseltorg.ru/procedure/{notice.external_id}/1",
                    f"https://www.roseltorg.ru/procedure/{notice.external_id}/1/",
                ):
                    raise AssertionError("Unexpected Roseltorg detail URL")
                report = asyncio.run(snapshot.fetch(
                    source_keys=(SOURCE,), search_terms=(notice.external_id,),
                    limit_per_source=10,
                ))
                if report.failures or not any(
                    row.identity == notice.identity and row.url == notice.url
                    for row in report.notices
                ):
                    raise AssertionError("Real Roseltorg notice not searchable")
                if store.upsert(notice, connector_version(SOURCE)):
                    raise AssertionError("Roseltorg identity was not idempotent")
            return {
                "real_official_details": len(stored),
                "worker_inserted": stats["inserted_count"],
                "sqlite_search_verified": len(stored),
                "idempotent": True,
                "production_changed": False,
            }
        finally:
            db.close()


if __name__ == "__main__":
    try:
        result = acceptance()
    except Exception as err:
        print("RU_ROSELTORG_REAL_WORKER=BLOCKED")
        print("FAILURE_CLASS=" + type(err).__name__)
        print("PRODUCTION_CHANGED=NO")
        raise SystemExit(1)
    print("RU_ROSELTORG_EVIDENCE=" + json.dumps(result, sort_keys=True))
    print("RU_ROSELTORG_REAL_WORKER=PASS")
    print("PRODUCTION_CHANGED=NO")
