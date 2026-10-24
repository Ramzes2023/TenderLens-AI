"""Live accredited Ingushetia 44-FZ mirror -> leased Worker -> temporary SQL.

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

SOURCE = "ru_ingushetia_fabrikant44"


def acceptance():
    catalog = build_source_catalog(MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=3,
        max_notifications_per_cycle=5, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        ru_ingushetia_fabrikant44_enabled=True,
    ))
    if SOURCE not in catalog.enabled_keys:
        raise AssertionError("Ingushetia Fabrikant test source not explicitly enabled")
    with tempfile.TemporaryDirectory(prefix="valyqon-ru-ingushetia-") as tmp:
        db = Database(DatabaseSettings("ru-ingushetia-live", Path(tmp) / "proof.sqlite"))
        try:
            jobs = JobRepository(db, JobSettings(lease_seconds=240, heartbeat_seconds=10))
            jobs.initialize()
            store = OpportunityRepository(db)
            store.initialize()
            claim = ConnectorSyncService(jobs, catalog).enqueue(SOURCE)
            handlers = HandlerRegistry()
            handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, store, max_records=3))
            # Follow the real durable repository retry schedule for transient
            # official publisher outages. Never seed notices or force a failed
            # job to succeed: the same actual Worker must claim each attempt.
            worker = Worker(jobs, handlers, job_types=(JOB_TYPE,))
            completed = None
            for attempt in range(3):
                if not worker.run_once():
                    raise AssertionError("Real Ingushetia Fabrikant Worker was not claimed")
                completed = jobs.get(claim.id, scope=JobScope())
                if completed is not None and completed.state == "succeeded":
                    break
                if completed is None or completed.state != "queued":
                    break
                if attempt < 2:
                    import time
                    time.sleep((1.25, 2.25)[attempt])
            if completed is None or completed.state != "succeeded":
                raise AssertionError("Ingushetia Fabrikant real leased worker did not succeed: "
                                     + str(completed.failure_code if completed else "missing"))
            stats = completed.result
            if not 2 <= stats["fetched_count"] <= 3:
                raise AssertionError("No independently verified official Ingushetia Fabrikant records")
            if (stats["fetched_count"] != stats["accepted_count"]
                    or stats["fetched_count"] != stats["inserted_count"]
                    or stats["skipped_count"] != 0):
                raise AssertionError("Ingushetia Fabrikant accepted/inserted count mismatch")
            rows = store.read(SOURCE, limit=3)
            if len(rows) != stats["fetched_count"]:
                raise AssertionError("Public Ingushetia Fabrikant SQL row count mismatch")
            snapshots = snapshot_catalog(catalog, store)
            for notice in rows:
                # This is a Fabrikant mirror of an EIS 44-FZ original.
                # Require native 19-digit identity, first-party original card
                # link and shared EIS dedup key, never an invented procedure.
                from app.sources.ru_notice_identity import original_notice_key
                from app.sources.ru_ingushetia_fabrikant44 import canonical_detail, REGION
                if (not re.fullmatch(r"[0-9]{19}", notice.external_id)
                        or notice.tender_number != notice.external_id
                        or canonical_detail(notice.url) != (notice.external_id, notice.url)
                        or notice.region != REGION
                        or original_notice_key(notice) != ("eis_44", notice.external_id)):
                    raise AssertionError("Original Ingushetia first-party identity invalid")
                result = asyncio.run(snapshots.fetch(
                    source_keys=(SOURCE,),
                    search_terms=(notice.external_id,),
                    limit_per_source=3,
                ))
                if result.failures or not any(
                    item.identity == notice.identity and item.url == notice.url
                    for item in result.notices
                ):
                    raise AssertionError("Ingushetia Fabrikant real stored record not searchable")
                if store.upsert(notice, connector_version(SOURCE)):
                    raise AssertionError("Ingushetia Fabrikant idempotent replay duplicated record")
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
        print("RU_INGUSHETIA_FABRIKANT_REAL_WORKER=BLOCKED")
        print("FAILURE_CLASS=" + type(e).__name__)
        if type(e) is AssertionError and str(e).startswith(
                "Ingushetia Fabrikant real leased worker did not succeed: "):
            code = str(e).rsplit(": ", 1)[-1]
            if code in {"handler_error", "permanent_failure", "lease_expired", "invalid_result", "missing"}:
                print("FAILURE_STAGE=LEASE_" + code.upper())
        print("PRODUCTION_CHANGED=NO")
        return 1
    print("RU_INGUSHETIA_FABRIKANT_EVIDENCE=" + json.dumps(evidence, sort_keys=True))
    print("RU_INGUSHETIA_FABRIKANT_REAL_WORKER=PASS")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
