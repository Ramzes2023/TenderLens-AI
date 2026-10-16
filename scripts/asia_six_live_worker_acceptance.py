"""Real six-source connector.sync.v1 worker acceptance in disposable SQLite.

This is an explicit, anonymous, non-production test: six official RSS endpoints
are fetched through the real worker's bounded transport, validated, persisted,
and queried through the production snapshot catalogue. No scheduler or AWS.
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
from app.sources.asia_public import ASIA_RSS_FEEDS
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import (
    JOB_TYPE, SYSTEM_SCOPE, ConnectorSyncHandler, ConnectorSyncService,
)
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog
from scripts.asia_six_live_acceptance import settings


def main() -> int:
    if os.environ.get("VALYQON_ASIA_SOURCES_ENABLED") != "1":
        print("ASIA_WORKER_SIX_ENABLED=NO")
        return 3
    summary = {}
    with tempfile.TemporaryDirectory(prefix="valyqon-asia-worker-") as temp:
        database = Database(DatabaseSettings("asia-six-worker-ephemeral", Path(temp) / "worker.sqlite"))
        try:
            jobs = JobRepository(database)
            jobs.initialize()
            store = OpportunityRepository(database)
            store.initialize()
            catalog = build_source_catalog(settings())
            service = ConnectorSyncService(JobService(jobs), catalog)
            handlers = HandlerRegistry()
            handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, store, max_records=5))
            worker = Worker(jobs, handlers, job_types=(JOB_TYPE,))
            snapshot = snapshot_catalog(catalog, store)
            for key in ASIA_RSS_FEEDS:
                item = {"state": "NOT_STARTED", "accepted": 0, "stored": 0, "queried": 0}
                summary[key] = item
                try:
                    job = service.enqueue(key)
                    if not worker.run_once():
                        item["state"] = "NO_WORK"
                        continue
                    result = jobs.get(job.id, scope=SYSTEM_SCOPE)
                    item["state"] = result.state if result else "NO_RESULT"
                    if result is None or result.state != "succeeded":
                        item["failure_code"] = result.failure_code if result else "unknown"
                        continue
                    outcome = result.result or {}
                    item["accepted"] = outcome.get("accepted_count", 0)
                    records = store.read(key, limit=10)
                    item["stored"] = len(records)
                    for notice in records:
                        report = asyncio.run(snapshot.fetch(
                            source_keys=(key,), search_terms=(notice.external_id,),
                            limit_per_source=10,
                        ))
                        if (not report.failures and len(report.notices) == 1
                                and report.notices[0].identity == notice.identity
                                and report.notices[0].url == notice.url):
                            item["queried"] += 1
                    if not (item["accepted"] == item["stored"] == item["queried"]
                            and item["accepted"] > 0):
                        item["state"] = "INCOMPLETE"
                except Exception as exc:
                    # Only code-owned exception type; never emit public raw
                    # response text, credentials, exception arguments or URLs.
                    item["state"] = "BLOCKED"
                    item["error_type"] = type(exc).__name__
        finally:
            database.close()
    passed = sum(x["state"] == "succeeded" and x["accepted"] > 0
                 and x["accepted"] == x["stored"] == x["queried"]
                 for x in summary.values())
    print("ASIA_SIX_REAL_WORKER_SQLITE_RESULTS=" + json.dumps(summary, sort_keys=True))
    print(f"ASIA_SIX_REAL_WORKER_SQLITE_QUERY_VERIFIED={passed}/6")
    print("PRODUCTION_CHANGED=NO")
    return 0 if passed == 6 else 3


if __name__ == "__main__":
    raise SystemExit(main())
