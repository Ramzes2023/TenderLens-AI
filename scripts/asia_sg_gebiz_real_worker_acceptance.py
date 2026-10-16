"""Real TWO Singapore official RSS feeds → queue → Worker → temp DB → search.

Strict hosted live gate, no fixtures or credentials, never touches production.
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
from app.sources.sg_gebiz_rss import FEEDS
from app.sources.ingestion import JOB_TYPE, SYSTEM_SCOPE, ConnectorSyncHandler, ConnectorSyncService
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog
from scripts.asia_six_live_acceptance import settings


def main():
    if os.environ.get("VALYQON_ASIA_GEBIZ_ENABLED") != "1":
        print("SG_GEBIZ_REAL_GATE=NOT_ENABLED")
        return 3
    evidence = {}
    try:
        with tempfile.TemporaryDirectory(prefix="valyqon-singapore-") as folder:
            db = Database(DatabaseSettings("sg-public-rss-disposable", Path(folder) / "notices.sqlite"))
            try:
                jobs = JobRepository(db)
                jobs.initialize()
                store = OpportunityRepository(db)
                store.initialize()
                catalog = build_source_catalog(settings())
                service = ConnectorSyncService(JobService(jobs), catalog)
                handlers = HandlerRegistry()
                handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, store, max_records=10))
                worker = Worker(jobs, handlers, job_types=(JOB_TYPE,))
                snapshot = snapshot_catalog(catalog, store)
                for source in FEEDS:
                    out = {"job": "NOT_STARTED", "stored": 0, "searched": 0, "deduped": False}
                    evidence[source] = out
                    try:
                        job = service.enqueue(source)
                        if not worker.run_once():
                            out["job"] = "NO_CLAIM"
                            continue
                        state = jobs.get(job.id, scope=SYSTEM_SCOPE)
                        out["job"] = state.state if state else "NOT_FOUND"
                        if out["job"] != "succeeded":
                            continue
                        rows = store.read(source, limit=20)
                        out["stored"] = len(rows)
                        for item in rows:
                            found = asyncio.run(snapshot.fetch(
                                source_keys=(source,), search_terms=(item.tender_number,),
                                limit_per_source=20,
                            ))
                            if (not found.failures and len(found.notices) == 1
                                    and found.notices[0].identity == item.identity
                                    and found.notices[0].url == item.url):
                                out["searched"] += 1
                        out["deduped"] = service.enqueue(source).id == job.id
                    except Exception as exc:
                        out["job"] = "BLOCKED"
                        out["error_type"] = type(exc).__name__
            finally:
                db.close()
    except Exception as exc:
        print("SG_GEBIZ_FATAL_ERROR=" + type(exc).__name__)
    passed = len(evidence) == len(FEEDS) and all(
        row["job"] == "succeeded" and row["stored"] > 0 and
        row["stored"] == row["searched"] and row["deduped"]
        for row in evidence.values()
    )
    print("SG_GEBIZ_REAL_WORKER_EVIDENCE=" + json.dumps(evidence, sort_keys=True))
    print("SG_GEBIZ_REAL_WORKER_SEARCH=" + ("PASS" if passed else "FAIL"))
    print("PRODUCTION_CHANGED=NO")
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
