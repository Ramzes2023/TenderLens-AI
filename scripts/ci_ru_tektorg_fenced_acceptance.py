"""Strict TEK-Torg real public listing -> details -> leased worker -> SQLite.

No fixtures for live source, no production credentials or persistent DB,
no TLS bypass, no cross-host request or custom proxy.
"""
from __future__ import annotations

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
from app.sources.ingestion import (
    JOB_TYPE, ConnectorSyncHandler, ConnectorSyncService, connector_version,
)
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog

SOURCE = "tektorg"


def acceptance():
    catalog = build_source_catalog(MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=5,
        max_notifications_per_cycle=5, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        tektorg_public_enabled=True,
    ))
    if SOURCE not in catalog.enabled_keys:
        raise AssertionError("TEK-Torg not enabled in test catalog")
    with tempfile.TemporaryDirectory(prefix="valyqon-tektorg-fenced-real-") as tmp:
        db = Database(DatabaseSettings("ru-tektorg-fenced-proof", Path(tmp) / "real.sqlite"))
        try:
            jobs = JobRepository(db, JobSettings(lease_seconds=240, heartbeat_seconds=10))
            jobs.initialize()
            store = OpportunityRepository(db)
            store.initialize()
            claim = ConnectorSyncService(jobs, catalog).enqueue(SOURCE)
            handlers = HandlerRegistry()
            handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, store, max_records=5))
            if not Worker(jobs, handlers, job_types=(JOB_TYPE,)).run_once():
                raise AssertionError("TEK-Torg job not claimed by production worker")
            completed = jobs.get(claim.id, scope=JobScope())
            if completed is None or completed.state != "succeeded":
                raise AssertionError("TEK-Torg real leased worker did not succeed: "
                                     + str(completed.failure_code if completed else "missing"))
            stats = completed.result
            if not 1 <= stats["fetched_count"] <= 5:
                raise AssertionError("No independently checked real TEK-Torg notices")
            if (stats["fetched_count"] != stats["accepted_count"]
                    or stats["fetched_count"] != stats["inserted_count"]
                    or stats["skipped_count"] != 0):
                raise AssertionError("TEK-Torg fenced worker record counts mismatch")
            stored = store.read(SOURCE, limit=5)
            if len(stored) != stats["fetched_count"]:
                raise AssertionError("TEK-Torg inserted SQL count mismatch")
            snapshot = snapshot_catalog(catalog, store)
            for notice in stored:
                if notice.url != f"https://www.tektorg.ru/223-fz/procedures/{notice.external_id}":
                    raise AssertionError("TEK-Torg record URL not canonical")
                query = asyncio.run(snapshot.fetch(
                    source_keys=(SOURCE,),
                    search_terms=(notice.external_id,),
                    limit_per_source=5,
                ))
                if query.failures or not any(
                    item.identity == notice.identity and item.url == notice.url
                    for item in query.notices
                ):
                    raise AssertionError("Real TEK-Torg record cannot be searched")
                if store.upsert(notice, connector_version(SOURCE)):
                    raise AssertionError("TEK-Torg idempotent replay duplicated record")
            return {
                "official_details": len(stored),
                "fenced_worker_inserted": stats["inserted_count"],
                "sqlite_search": len(stored),
                "idempotent": True,
                "production_changed": False,
            }
        finally:
            db.close()


def main():
    try:
        evidence = acceptance()
    except Exception as e:
        print("RU_TEKTORG_FENCED_REAL=BLOCKED")
        print("FAILURE_CLASS=" + type(e).__name__)
        if type(e) is AssertionError and str(e).startswith(
                "TEK-Torg real leased worker did not succeed: "):
            code = str(e).rsplit(": ", 1)[-1]
            if code in {"handler_error", "permanent_failure", "lease_expired", "invalid_result", "missing"}:
                print("FAILURE_STAGE=" + code.upper())
        print("PRODUCTION_CHANGED=NO")
        return 1
    print("RU_TEKTORG_FENCED_EVIDENCE=" + json.dumps(evidence, sort_keys=True))
    print("RU_TEKTORG_FENCED_REAL=PASS")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
