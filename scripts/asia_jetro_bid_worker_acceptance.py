"""Fail-closed JETRO bid RSS: real HTTPS -> queue -> Worker -> SQLite -> search.

Explicit PR-only disposable acceptance, no production activation or secrets.
A 200 response, fixture-only success or merely constructing an adapter is
NOT sufficient. A GitHub runner must retrieve a linked official tender.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
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



def run_real_queued_job(worker, jobs, job_id, *, clock=None, sleeper=None):
    """Honor the durable queue retry schedule without mocking source results.

    Retryable upstream failure legitimately leaves the real claimed job queued.
    Accept only a genuinely succeeded terminal result after up to 3 attempts.
    """
    now = clock if clock is not None else time.time
    wait = sleeper if sleeper is not None else time.sleep
    state = None
    for _ in range(3):
        worked = worker.run_once()
        state = jobs.get(job_id, scope=SYSTEM_SCOPE)
        if not worked:
            return state, "NO_RUNNABLE_JOB"
        if state is None:
            return None, "NO_JOB_RESULT"
        if state.state != "queued":
            return state, "FINISHED"
        if state.attempt_count >= min(state.max_attempts, 3):
            return state, "RETRIES_EXHAUSTED"
        delay = (state.available_at - int(now() * 1_000_000)) / 1_000_000
        if delay > 5:
            return state, "RETRY_DELAY_OUT_OF_BOUNDS"
        wait(max(0.0, delay) + 0.06)
    return state, "RETRY_LIMIT"

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
                state, queue_check = run_real_queued_job(worker, jobs, job.id)
                result["job"] = state.state if state else "NO_JOB_RESULT"
                result["queue_check"] = queue_check
                if state is not None:
                    result["attempts"] = state.attempt_count
                    result["failure_code"] = state.failure_code
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
