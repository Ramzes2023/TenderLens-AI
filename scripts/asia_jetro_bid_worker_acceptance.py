"""Fail-closed JETRO bid RSS: real HTTPS -> queue -> Worker -> SQLite -> search.

Explicit PR-only disposable acceptance, no production activation or secrets.
A 200 response, fixture-only success or merely constructing an adapter is
NOT sufficient. A GitHub runner must retrieve a linked official tender.
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
from app.sources.jp_jetro_bid_rss import SOURCE_ID
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog
from scripts.asia_six_live_acceptance import settings


def main() -> int:
    if os.environ.get("VALYQON_ASIA_JETRO_BID_ENABLED") != "1":
        print("JP_JETRO_BID_LIVE_GATE=NOT_ENABLED")
        return 3

    result = {"job": "NOT_STARTED", "stored": 0, "searched": 0, "replay_deduped": False}
    try:
        with tempfile.TemporaryDirectory(prefix="valyqon-jp-jetro-bid-") as directory:
            db = Database(DatabaseSettings(
                "jp-jetro-temporary", Path(directory) / "notices.sqlite"
            ))
            try:
                jobs = JobRepository(db)
                jobs.initialize()
                opportunities = OpportunityRepository(db)
                opportunities.initialize()
                catalog = build_source_catalog(settings())
                service = ConnectorSyncService(JobService(jobs), catalog)
                handlers = HandlerRegistry()
                handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, opportunities, max_records=5))
                worker = Worker(jobs, handlers, job_types=(JOB_TYPE,))
                job = service.enqueue(SOURCE_ID)
                if worker.run_once():
                    state = jobs.get(job.id, scope=SYSTEM_SCOPE)
                    result["job"] = state.state if state else "NO_JOB_RESULT"
                    if state is not None and state.state == "succeeded":
                        stored = opportunities.read(SOURCE_ID, limit=10)
                        result["stored"] = len(stored)
                        snapshots = snapshot_catalog(catalog, opportunities)
                        for notice in stored:
                            report = asyncio.run(snapshots.fetch(
                                source_keys=(SOURCE_ID,),
                                search_terms=(notice.external_id,),
                                limit_per_source=10,
                            ))
                            if (not report.failures and len(report.notices) == 1
                                    and report.notices[0].identity == notice.identity
                                    and report.notices[0].url == notice.url):
                                result["searched"] += 1
                        duplicate = service.enqueue(SOURCE_ID)
                        result["replay_deduped"] = duplicate.id == job.id
            finally:
                db.close()
    except Exception as exc:
        result["job"] = "BLOCKED"
        # No remote notice content, HTTP response, URL or credentials in logs.
        result["error_type"] = type(exc).__name__

    passed = (
        result["job"] == "succeeded" and result["stored"] > 0
        and result["stored"] == result["searched"] and result["replay_deduped"]
    )
    print("JP_JETRO_BID_REAL_WORKER_EVIDENCE=" + json.dumps(result, sort_keys=True))
    print("JP_JETRO_BID_REAL_WORKER_SEARCH=" + ("PASS" if passed else "FAIL"))
    print("PRODUCTION_CHANGED=NO")
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
