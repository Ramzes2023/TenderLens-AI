"""Operator-only batch enqueue of six approved Asian public connectors.

Dry-run by default. Never schedules background work by importing this module.
The existing job queue deduplicates each (source, UTC-hour, adapter-version)
across workers. Do not enable on AWS until all six live acceptance checks pass.
"""
from __future__ import annotations

import argparse
import json
import os

from .asia_public import ASIA_RSS_FEEDS, JETRO_LISTS
from .ingestion import connector_version, sync_window, validate_payload

SOURCES = (*ASIA_RSS_FEEDS, *JETRO_LISTS)


def validate_batch(catalog) -> tuple[str, ...]:
    """Validate all six source IDs before opening the job queue for writes."""
    if os.environ.get("VALYQON_ASIA_SOURCES_ENABLED", "").strip() != "1":
        raise ValueError("Asian procurement sources are not explicitly enabled.")
    window = sync_window()
    for source_id in SOURCES:
        validate_payload(
            {"schema": 1, "source_id": source_id, "sync_window": window,
             "connector_version": connector_version(source_id)},
            catalog.registry,
        )
    return SOURCES


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--enqueue", action="store_true",
        help="Explicitly enqueue the six existing verified connectors for this UTC hour.",
    )
    args = parser.parse_args(argv)

    # Local introspection is safe and does not read .env, DB or secrets.
    if not args.enqueue:
        print(json.dumps({
            "mode": "dry_run", "source_ids": SOURCES,
            "enqueued": 0, "production_changed": False,
        }, separators=(",", ":")))
        return 0

    database = None
    try:
        from app.database.backend import Database
        from app.database.config import load_database_settings
        from app.jobs import JobRepository, JobService, load_job_settings
        from app.monitoring.config import load_monitoring_settings
        from .catalog import build_source_catalog
        from .ingestion import ConnectorSyncService

        # Fail closed BEFORE opening the DB if source activation/registry
        # does not match the exact operator-approved six-source contract.
        catalog = build_source_catalog(load_monitoring_settings())
        validated = validate_batch(catalog)
        database = Database(load_database_settings())
        jobs = JobRepository(database, load_job_settings())
        jobs.initialize()
        service = ConnectorSyncService(JobService(jobs), catalog)
        queued = []
        for source_id in validated:
            job = service.enqueue(source_id)
            queued.append({"source_id": source_id, "job_id": job.id})
        print(json.dumps({
            "mode": "enqueue", "source_count": len(queued),
            "jobs": queued,
        }, separators=(",", ":")))
        return 0
    except Exception:
        # Do not leak DB details, internal URLs or credentialed payloads.
        print("Asian connector batch enqueue was blocked or failed.")
        return 2
    finally:
        if database is not None:
            database.close()


if __name__ == "__main__":
    raise SystemExit(main())
