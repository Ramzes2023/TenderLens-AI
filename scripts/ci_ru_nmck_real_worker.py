"""Public Leningrad Oblast -> real leased/fenced worker -> disposable searchable DB.

Only independently checked official live notices qualify; no fixture substitution,
no production credentials, deployment, proxy or TLS bypass.
"""
import asyncio
import json
import re
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

SOURCE = "nmck_native_public"


def acceptance():
    catalog = build_source_catalog(MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=3,
        max_notifications_per_cycle=5, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        nmck_native_public_enabled=True,
    ))
    if SOURCE not in catalog.enabled_keys:
        raise AssertionError("NMCK test source not explicitly enabled")
    with tempfile.TemporaryDirectory(prefix="valyqon-ru-nmck-") as tmp:
        db = Database(DatabaseSettings("ru-nmck-live", Path(tmp) / "proof.sqlite"))
        try:
            jobs = JobRepository(db, JobSettings(lease_seconds=240, heartbeat_seconds=10))
            jobs.initialize()
            store = OpportunityRepository(db)
            store.initialize()
            claim = ConnectorSyncService(jobs, catalog).enqueue(SOURCE)
            handlers = HandlerRegistry()
            handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, store, max_records=3))
            if not Worker(jobs, handlers, job_types=(JOB_TYPE,)).run_once():
                raise AssertionError("Public NMCK job was not claimed")
            completed = jobs.get(claim.id, scope=JobScope())
            if completed is None or completed.state != "succeeded":
                raise AssertionError("NMCK real leased worker did not succeed: "
                                     + str(completed.failure_code if completed else "missing"))
            stats = completed.result
            if not 1 <= stats["fetched_count"] <= 3:
                raise AssertionError("No independently verified official NMCK records")
            if (stats["fetched_count"] != stats["accepted_count"]
                    or stats["fetched_count"] != stats["inserted_count"]
                    or stats["skipped_count"] != 0):
                raise AssertionError("NMCK accepted/inserted count mismatch")
            rows = store.read(SOURCE, limit=3)
            if len(rows) != stats["fetched_count"]:
                raise AssertionError("Public NMCK SQL row count mismatch")
            snapshots = snapshot_catalog(catalog, store)
            for notice in rows:
                if (notice.tender_number != notice.external_id + "М"
                        or not re.fullmatch(
                            r"https://xn--j1adc1b\\.xn--p1ai/procedures\\?procedure="
                            r"[a-z0-9-]{6,140}-" + re.escape(notice.external_id) + r"m",
                            notice.url,
                        )):
                    raise AssertionError("Public NMCK notice URL or identity invalid")
                result = asyncio.run(snapshots.fetch(
                    source_keys=(SOURCE,),
                    search_terms=(notice.external_id,),
                    limit_per_source=3,
                ))
                if result.failures or not any(
                    item.identity == notice.identity and item.url == notice.url
                    for item in result.notices
                ):
                    raise AssertionError("NMCK real stored record not searchable")
                if store.upsert(notice, connector_version(SOURCE)):
                    raise AssertionError("NMCK idempotent replay duplicated record")
            return {
                "independently_verified_details": len(rows),
                "fenced_worker_inserted": stats["inserted_count"],
                "sql_keyword_found": len(rows),
                "idempotent": True,
                "production_changed": False,
            }
        finally:
            db.close()


def main():
    try:
        evidence = acceptance()
    except Exception as e:
        print("RU_NMCK_REAL_WORKER=BLOCKED")
        print("FAILURE_CLASS=" + type(e).__name__)
        if type(e) is AssertionError and str(e).startswith(
                "NMCK real leased worker did not succeed: "):
            code = str(e).rsplit(": ", 1)[-1]
            if code in {"handler_error", "permanent_failure", "lease_expired", "invalid_result", "missing"}:
                print("FAILURE_STAGE=LEASE_" + code.upper())
        print("PRODUCTION_CHANGED=NO")
        return 1
    print("RU_NMCK_EVIDENCE=" + json.dumps(evidence, sort_keys=True))
    print("RU_NMCK_REAL_WORKER=PASS")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
