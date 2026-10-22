"""Explicit, operator-approved UTC-hourly queueing for Ingushetia originals.

Queueing ONLY: no network fetch, no Worker process, no Telegram delivery,
no source flags toggled, and no production activation on import. The caller
must separately run an approved connector Worker against the SAME database
and enable the monitor/bot with their own explicit authorization.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import signal
import threading

from app.sources.ingestion import sync_window
from app.sources.registry import SourceRegistryError

SOURCES = ("ru_ingushetia_eis44", "ru_ingushetia_fabrikant44")
APPROVAL = "YES_INGUSHETIA_QUEUE_ONLY"


def enabled_ingushetia_keys(catalog):
    """Never queue unrelated RU sources or source registrations not enabled."""
    result = []
    for key in SOURCES:
        try:
            registration = catalog.registry.get(key)
        except SourceRegistryError:
            continue
        if "RU" not in registration.jurisdictions:
            raise ValueError("Unexpected region on Ingushetia source")
        if registration.enabled:
            result.append(key)
    if not result:
        raise ValueError("No explicitly enabled Ingushetia source")
    return tuple(result)


def queue_if_new_hour(service, catalog, *, now, previous_window=None):
    """Each UTC hour may enqueue its own source jobs once.

    The durable service's existing source + version + UTC-hour idempotency
    remains authoritative even after a process restart. This in-memory
    check only avoids unnecessary database calls within the same hour.
    """
    if now.tzinfo is None:
        raise ValueError("UTC-aware scheduling clock required")
    active = enabled_ingushetia_keys(catalog)
    window = sync_window(now)
    if window == previous_window:
        return window, {}
    queued = {}
    for source in active:
        job = service.enqueue(source, now=now)
        queued[source] = {"job_id": job.id, "state": job.state}
    return window, queued


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="Queue one approved UTC hour")
    mode.add_argument("--hourly", action="store_true", help="Run an explicit hourly queue loop")
    parser.add_argument("--authorize-queue-only", action="store_true")
    args = parser.parse_args(argv)
    if (not args.authorize_queue_only
            or os.environ.get("VALYQON_INGUSHETIA_QUEUE_APPROVED") != APPROVAL):
        print("INGUSHETIA_HOURLY_ENQUEUE=BLOCKED; EXPLICIT_APPROVAL_REQUIRED=YES")
        return 2

    db = None
    try:
        from app.database.backend import Database
        from app.database.config import load_database_settings
        from app.jobs import JobRepository, JobService, load_job_settings
        from app.monitoring.config import load_monitoring_settings
        from app.sources.catalog import build_source_catalog
        from app.sources.ingestion import ConnectorSyncService

        catalog = build_source_catalog(load_monitoring_settings())
        enabled_ingushetia_keys(catalog)  # fail before opening any database
        db = Database(load_database_settings())
        jobs = JobRepository(db, load_job_settings())
        jobs.initialize()
        service = ConnectorSyncService(JobService(jobs), catalog)
        stop = threading.Event()
        if args.hourly:
            def stopping(signum, frame):
                stop.set()
            signal.signal(signal.SIGINT, stopping)
            signal.signal(signal.SIGTERM, stopping)
        previous_window = None
        while not stop.is_set():
            now = datetime.now(timezone.utc)
            previous_window, queued = queue_if_new_hour(
                service, catalog, now=now, previous_window=previous_window,
            )
            if queued:
                print("INGUSHETIA_HOURLY_ENQUEUE=" + json.dumps({
                    "utc_window": previous_window, "queued": queued,
                    "ingestion_performed": False,
                    "telegram_sent": False,
                    "durable_queue_changed": True,
                    "source_flags_changed": False,
                }, sort_keys=True), flush=True)
            if args.once:
                break
            stop.wait(30.0)
        return 0
    except Exception:
        # Never serialize job payloads, DB credentials, or upstream exception
        # text. Operators can inspect approved durable job statuses separately.
        print("INGUSHETIA_HOURLY_ENQUEUE=BLOCKED; CHECK_DATABASE_AND_ENABLED_SOURCES=YES")
        return 2
    finally:
        if db is not None:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
