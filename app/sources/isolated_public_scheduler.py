"""Opt-in fixed Russian-source queue scheduler; no upstream HTTP or notifications.

A healthy Docker Worker fetches the publicly published original; this process
only enqueues at most once per UTC hour per source. It is disabled unless an operator
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
            os.environ.get("MIKROTON_TENDER_ENABLED") != "true" or
            os.environ.get("STAN_COMMERCIAL_PUBLIC_ENABLED") != "true"):
        raise ValueError("Isolated source scheduler not explicitly approved")
    from app.database.backend import Database
    from app.database.config import load_database_settings
    from app.jobs import JobRepository, JobService, load_job_settings
    from app.monitoring.config import load_monitoring_settings
    from app.sources.catalog import build_source_catalog
    from app.sources.ingestion import ConnectorSyncService
    from app.sources.ru_cycle import approved_ru_keys

    extension = os.environ.get("SOUTH_URAL_PUBLIC_ENABLED", "false").strip().lower()
    north_caucasus = os.environ.get("KAVKAZ_RF_FIRSTPARTY_ENABLED", "false").strip().lower()
    if extension not in {"true", "false"} or north_caucasus not in {"true", "false"}:
        raise ValueError("Invalid regional public-source opt-in.")
    approved = ("mikroton_tender", "stan_commercial_public")
    if extension == "true":
        approved += ("south_ural_public",)
    if north_caucasus == "true":
        if extension != "true":
            # Prevent accidentally reverting the live third source when
            # layering a fourth-source release atop the installed stack.
            raise ValueError("Kavkaz.RF requires the approved South Ural overlay.")
        approved += ("kavkaz_rf_firstparty",)
    northwest = os.environ.get("LENOBL_SMALL_PUBLIC_ENABLED", "false").strip().lower()
    if northwest not in {"true", "false"}:
        raise ValueError("Invalid Lenobl source opt-in.")
    if northwest == "true":
        if extension != "true" or north_caucasus != "true":
            raise ValueError("Lenobl requires the existing four-source overlays.")
        approved += ("lenobl_small_public",)
    catalog = build_source_catalog(load_monitoring_settings())
    if set(approved_ru_keys(catalog)) != set(approved):
        raise ValueError("Unexpected enabled RU source in scheduler")

    database = Database(load_database_settings())
    try:
        repo = JobRepository(database, load_job_settings())
        repo.initialize()
        service = ConnectorSyncService(JobService(repo), catalog)
        for source_id in approved:
            service.enqueue(source_id)
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
