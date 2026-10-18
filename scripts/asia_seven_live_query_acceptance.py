"""Fail-closed hosted acceptance for seven real Asian feeds -> durable job -> query.

No AWS, production DB, secrets, tenant records, fabricated notices or test fakes.
A nonzero exit is intentional when any official live feed is empty or unavailable.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import HandlerRegistry, JobRepository, JobService
from app.jobs.worker import Worker
from app.sources.asia_seven import SOURCES, search_stored, validate_sources
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import JOB_TYPE, SYSTEM_SCOPE, ConnectorSyncHandler, ConnectorSyncService
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog
from scripts.asia_six_live_acceptance import settings


def run_bounded_jetro_claim(worker, jobs, job_id, *, clock=None, sleeper=None):
    """Only honor genuine leased JETRO retries at the DB's scheduled time.

    There are no forced job-state changes, mocked upstream notices, or fake
    successes. A non-terminal queued job can never pass real acceptance.
    """
    now = clock if clock is not None else time.time
    pause = sleeper if sleeper is not None else time.sleep
    state = None
    for attempt in range(3):
        worked = worker.run_once()
        state = jobs.get(job_id, scope=SYSTEM_SCOPE)
        if not worked:
            return state, "NO_LEASE_CLAIM"
        if state is None:
            return None, "NO_JOB_RESULT"
        if state.state != "queued":
            return state, "TERMINAL"
        if state.attempt_count >= min(state.max_attempts, 3) or attempt == 2:
            return state, "RETRIES_EXHAUSTED"
        wait_seconds = (state.available_at - int(now() * 1_000_000)) / 1_000_000
        if wait_seconds > 5.0:
            return state, "RETRY_WINDOW_TOO_LONG"
        pause(max(0.0, wait_seconds) + 0.08)
    return state, "RETRIES_EXHAUSTED"


def main() -> int:
    if (os.environ.get("VALYQON_ASIA_SOURCES_ENABLED") != "1"
            or os.environ.get("VALYQON_ASIA_JETRO_BID_ENABLED") != "1"):
        print("ASIA_SEVEN_REAL_QUERY_GATE=DISABLED")
        return 3

    result = {}
    successes = 0
    try:
        with tempfile.TemporaryDirectory(prefix="valyqon-asia-seven-") as folder:
            db = Database(DatabaseSettings("asia-seven-disposable", Path(folder) / "test.sqlite"))
            try:
                jobs = JobRepository(db)
                jobs.initialize()
                opportunities = OpportunityRepository(db)
                opportunities.initialize()
                cat = build_source_catalog(settings())
                validate_sources(cat)
                service = ConnectorSyncService(JobService(jobs), cat)
                handlers = HandlerRegistry()
                handlers.register(JOB_TYPE, ConnectorSyncHandler(cat, opportunities, max_records=5))
                worker = Worker(jobs, handlers, job_types=(JOB_TYPE,))
                snapshot = snapshot_catalog(cat, opportunities)
                for key in SOURCES:
                    report = {"job": "NOT_STARTED", "stored": 0, "searched": 0,
                              "queue_deduped": False, "operator_query": False}
                    result[key] = report
                    try:
                        job = service.enqueue(key)
                        if key == "jp_jetro_bid":
                            completed, queue_check = run_bounded_jetro_claim(
                                worker, jobs, job.id)
                            report["queue_check"] = queue_check
                            report["attempts"] = completed.attempt_count if completed else 0
                            report["failure_code"] = completed.failure_code if completed else None
                        else:
                            if not worker.run_once():
                                report["job"] = "NO_WORK"
                                continue
                            completed = jobs.get(job.id, scope=SYSTEM_SCOPE)
                        report["job"] = completed.state if completed else "MISSING"
                        if completed is None or completed.state != "succeeded":
                            continue
                        stored = opportunities.read(key, limit=10)
                        report["stored"] = len(stored)
                        for record in stored:
                            words = (record.title or "").split()
                            # Search one actual verified stored word, never
                            # invent a keyword that the upstream did not emit.
                            keyword = next((w for w in words if len(w) >= 3), "")
                            if not keyword:
                                continue
                            found = search_stored(opportunities, keyword, limit=30, source=key)
                            if any(row["source"] == key and row["external_id"] == record.external_id
                                   and row["url"] == record.url for row in found):
                                report["searched"] += 1
                        repeat = service.enqueue(key)
                        report["queue_deduped"] = repeat.id == job.id
                        report["operator_query"] = report["stored"] == report["searched"] > 0
                        if report["operator_query"] and report["queue_deduped"]:
                            successes += 1
                    except Exception as error:
                        report["job"] = "BLOCKED"
                        report["error_type"] = type(error).__name__
            finally:
                db.close()
    except Exception as error:
        print("ASIA_SEVEN_GATE_ERROR=" + type(error).__name__)
    print("ASIA_SEVEN_REAL_QUERY_DETAILS=" + json.dumps(result, sort_keys=True))
    print(f"ASIA_SEVEN_REAL_QUERY_VERIFIED={successes}/7")
    print("PRODUCTION_CHANGED=NO")
    return 0 if successes == len(SOURCES) else 3


if __name__ == "__main__":
    raise SystemExit(main())
