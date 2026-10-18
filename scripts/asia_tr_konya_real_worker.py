"""Strict REAL Konya official listing -> leased Worker -> SQLite -> keyword search.

No fixtures, synthetic records, AWS, production activation, credentials,
third-party tenders, queue-state spoofing or TLS/proxy bypass. Must fail RED
if public government pages are temporarily unavailable or no live tenders.
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
from app.sources.ingestion import JOB_TYPE, SYSTEM_SCOPE, ConnectorSyncHandler, ConnectorSyncService
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog
from app.sources.tr_konya_municipality import SOURCE_ID
from scripts.asia_six_live_acceptance import settings


def main() -> int:
    if os.environ.get("VALYQON_ASIA_TURKEY_KONYA_ENABLED") != "1":
        print("TR_KONYA_LIVE_GATE=DISABLED")
        return 3
    proof = {"job": "NOT_STARTED", "stored": 0, "searched": 0, "idempotent": False}
    try:
        with tempfile.TemporaryDirectory(prefix="valyqon-konya-real-") as temp:
            db = Database(DatabaseSettings("tr-konya-ephemeral", Path(temp) / "tenders.db"))
            try:
                jobs = JobRepository(db)
                jobs.initialize()
                store = OpportunityRepository(db)
                store.initialize()
                cat = build_source_catalog(settings())
                service = ConnectorSyncService(JobService(jobs), cat)
                handlers = HandlerRegistry()
                handlers.register(JOB_TYPE, ConnectorSyncHandler(cat, store, max_records=4))
                worker = Worker(jobs, handlers, job_types=(JOB_TYPE,))
                job = service.enqueue(SOURCE_ID)
                if worker.run_once():
                    state = jobs.get(job.id, scope=SYSTEM_SCOPE)
                    proof["job"] = state.state if state else "MISSING"
                    if state and state.state == "succeeded":
                        rows = store.read(SOURCE_ID, limit=10)
                        proof["stored"] = len(rows)
                        if any(row.deadline is None or row.tender_number is None for row in rows):
                            proof["job"] = "INVALID_ORIGINAL"
                        else:
                            snap = snapshot_catalog(cat, store)
                            for notice in rows:
                                result = asyncio.run(snap.fetch(
                                    source_keys=(SOURCE_ID,),
                                    search_terms=(notice.tender_number,),
                                    limit_per_source=20,
                                ))
                                if (not result.failures
                                        and len(result.notices) == 1
                                        and result.notices[0].identity == notice.identity
                                        and result.notices[0].url == notice.url):
                                    proof["searched"] += 1
                            proof["idempotent"] = service.enqueue(SOURCE_ID).id == job.id
            finally:
                db.close()
    except Exception as error:
        proof["job"] = "BLOCKED"
        proof["error_type"] = type(error).__name__
    good = (proof["job"] == "succeeded" and proof["stored"] >= 2
            and proof["searched"] == proof["stored"] and proof["idempotent"])
    print("TR_KONYA_OFFICIAL_REAL_ACCEPTANCE=" + json.dumps(proof, sort_keys=True))
    print("TR_KONYA_LIVE_WORKER_SQLITE_SEARCH=" + ("PASS" if good else "FAIL"))
    print("PRODUCTION_CHANGED=NO")
    return 0 if good else 3


if __name__ == "__main__":
    raise SystemExit(main())
