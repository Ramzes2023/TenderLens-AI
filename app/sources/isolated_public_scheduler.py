"""Opt-in single-source queue scheduler; no upstream HTTP or notifications.

A healthy Docker Worker fetches the publicly published original; this process
only enqueues at most once per UTC hour. It is disabled unless an operator
explicitly starts the verified-scheduler Compose profile.
"""
from __future__ import annotations

import os
import signal
import threading
from datetime import datetime, timedelta, timezone

from app.api.isolated_public_sources import ISOLATED_SQLITE_URL


def next_utc_hour(now: datetime) -> datetime:
    if now.tzinfo is None:
        raise ValueError("UTC-aware timestamp required")
    now = now.astimezone(timezone.utc)
    return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def approved_cycle():
    if (os.environ.get("VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED") != "true" or
            os.environ.get("DATABASE_URL") != ISOLATED_SQLITE_URL or
            os.environ.get("MIKROTON_TENDER_ENABLED") != "true"):
        raise ValueError("Isolated source scheduler not explicitly approved")
    from app.database.backend import Database
    from app.database.config import load_database_settings
    from app.jobs import JobRepository, JobService, load_job_settings
    from app.monitoring.config import load_monitoring_settings
    from app.sources.catalog import build_source_catalog
    from app.sources.ingestion import ConnectorSyncService

    catalog = build_source_catalog(load_monitoring_settings())
    if set(catalog.enabled_keys) != {"mikroton_tender"}:
        raise ValueError("Unexpected enabled source in scheduler")

    database = Database(load_database_settings())
    try:
        repo = JobRepository(database, load_job_settings())
        repo.initialize()
        service = ConnectorSyncService(JobService(repo), catalog)
        service.enqueue("mikroton_tender")
    finally:
        database.close()


def main() -> int:
    stop = threading.Event()

    def request_stop(_signum, _frame):
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    while not stop.is_set():
        try:
            approved_cycle()
        except Exception:
            # Never conceal a bad config behind green source readiness.
            print("ISOLATED_SOURCE_SCHEDULE_CYCLE=FAILED", flush=True)
            return 2
        print("ISOLATED_SOURCE_SCHEDULE_CYCLE=ENQUEUED", flush=True)
        delay = max(1.0, (next_utc_hour(datetime.now(timezone.utc))
                           - datetime.now(timezone.utc)).total_seconds())
        stop.wait(delay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
