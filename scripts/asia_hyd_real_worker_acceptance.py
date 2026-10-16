"""Official HyD live HTTPS → genuine connector Worker → temporary SQLite → search.

Mandatory no-fake PR gate. Nonzero when actual linked tenders cannot be found.
"""
from __future__ import annotations
import asyncio
import json
import os
import tempfile
from pathlib import Path

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import HandlerRegistry, JobRepository, JobService
from app.jobs.worker import Worker
from app.sources.catalog import build_source_catalog
from app.sources.hk_hyd_tenders import SOURCE_ID
from app.sources.ingestion import JOB_TYPE, SYSTEM_SCOPE, ConnectorSyncHandler, ConnectorSyncService
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog
from scripts.asia_six_live_acceptance import settings


def main():
    if os.environ.get("VALYQON_ASIA_HYD_ENABLED") != "1":
        print("ASIA_HYD_GATE=NOT_ENABLED")
        return 3
    out = {"job": "NOT_STARTED", "stored": 0, "searched": 0, "deduped": False}
    try:
        with tempfile.TemporaryDirectory(prefix="valyqon-hyd-live-") as directory:
            db = Database(DatabaseSettings("hyd-ephemeral", Path(directory) / "tenders.db"))
            try:
                jobs = JobRepository(db)
                jobs.initialize()
                stored = OpportunityRepository(db)
                stored.initialize()
                catalog = build_source_catalog(settings())
                service = ConnectorSyncService(JobService(jobs), catalog)
                handlers = HandlerRegistry()
                handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, stored, max_records=10))
                worker = Worker(jobs, handlers, job_types=(JOB_TYPE,))
                job = service.enqueue(SOURCE_ID)
                if worker.run_once():
                    finished = jobs.get(job.id, scope=SYSTEM_SCOPE)
                    out["job"] = finished.state if finished else "NO_RESULT"
                    if out["job"] == "succeeded":
                        notices = stored.read(SOURCE_ID, limit=20)
                        out["stored"] = len(notices)
                        snapshot = snapshot_catalog(catalog, stored)
                        for notice in notices:
                            result = asyncio.run(snapshot.fetch(
                                source_keys=(SOURCE_ID,), search_terms=(notice.external_id,),
                                limit_per_source=20,
                            ))
                            if (not result.failures and len(result.notices) == 1
                                    and result.notices[0].identity == notice.identity):
                                out["searched"] += 1
                        out["deduped"] = service.enqueue(SOURCE_ID).id == job.id
            finally:
                db.close()
    except Exception as exc:
        out["job"] = "BLOCKED"
        out["error_type"] = type(exc).__name__
    valid = (out["job"] == "succeeded" and out["stored"] > 0
             and out["searched"] == out["stored"] and out["deduped"])
    print("ASIA_HYD_REAL_WORKER_EVIDENCE=" + json.dumps(out, sort_keys=True))
    print("ASIA_HYD_REAL_WORKER_SEARCH=" + ("PASS" if valid else "FAIL"))
    print("PRODUCTION_CHANGED=NO")
    return 0 if valid else 3


if __name__ == "__main__":
    raise SystemExit(main())
