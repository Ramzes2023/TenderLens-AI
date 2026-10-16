"""Explicit seven-source Asia batch enqueue and local persisted tender search.

This is an operator entrypoint, NOT an always-on daemon or customer endpoint.
Enqueue uses the existing lease-fenced connector.sync.v1 worker; no synchronous
remote network fetch is performed by this CLI. Search reads only stored public
notices. Worker and schedule must be enabled separately by the deployer.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone

from .asia_public import ASIA_RSS_FEEDS
from .jp_jetro_bid_rss import SOURCE_ID as JETRO_BID
from .ingestion import connector_version, sync_window, validate_payload

SOURCES = (*ASIA_RSS_FEEDS, JETRO_BID)
MAX_RETURNED = 30
_QUERY = re.compile(r"^[^\x00-\x1f\x7f]{2,120}$")


def validate_sources(catalog, *, now=None) -> tuple[str, ...]:
    """Validate all routes, flags and approved source IDs before any DB write."""
    if os.environ.get("VALYQON_ASIA_SOURCES_ENABLED", "").strip() != "1":
        raise ValueError("Hong Kong Asian procurement sources disabled.")
    if os.environ.get("VALYQON_ASIA_JETRO_BID_ENABLED", "").strip() != "1":
        raise ValueError("Japan JETRO bid RSS source disabled.")
    window = sync_window(now)
    for source_id in SOURCES:
        validate_payload({
            "schema": 1, "source_id": source_id,
            "sync_window": window,
            "connector_version": connector_version(source_id),
        }, catalog.registry)
    return SOURCES


def search_stored(opportunities, query: str, *, limit: int = 20, source: str | None = None) -> list[dict]:
    """Bounded local keyword search; never send the user's words upstream."""
    if not isinstance(query, str) or not _QUERY.fullmatch(query.strip()):
        raise ValueError("Search query must be 2-120 printable characters.")
    if type(limit) is not int or not 1 <= limit <= MAX_RETURNED:
        raise ValueError("Invalid search limit.")
    if source is not None and source not in SOURCES:
        raise ValueError("Unknown Asian source selector.")
    word = query.strip()
    rows = []
    for source_id in ((source,) if source else SOURCES):
        # Read at most limit rows from each fixed public source ID. The
        # existing repository enforces an additional 1000-row candidate bound.
        for notice in opportunities.read(source_id, limit=limit, search_terms=(word,)):
            rows.append({
                "source": notice.source, "external_id": notice.external_id,
                "title": notice.title, "url": notice.url,
                "customer": notice.customer, "published_at": notice.published_at,
                "deadline": notice.deadline, "region": notice.region,
                "initial_price": notice.initial_price, "currency": notice.currency,
            })
    # Deterministic cross-source ordering; no false claim of exact deadlines.
    rows.sort(key=lambda n: (n["published_at"] or "", n["source"], n["external_id"]), reverse=True)
    return rows[:limit]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group()
    commands.add_argument("--enqueue", action="store_true",
                          help="Queue 7 approved source refreshes for current UTC hour.")
    commands.add_argument("--search", metavar="KEYWORD",
                          help="Search only already-persisted public Asian tenders.")
    parser.add_argument("--source", choices=SOURCES,
                        help="Optional source ID for already-persisted search results.")
    parser.add_argument("--limit", type=int, default=20,
                        help="Max returned stored tenders (1..30).")
    args = parser.parse_args(argv)

    # Dry run is completely safe: no configuration, database or network access.
    if not args.enqueue and args.search is None:
        print(json.dumps({
            "mode": "dry_run", "sources": list(SOURCES),
            "total_sources": len(SOURCES), "enqueued": 0,
            "production_changed": False,
        }, ensure_ascii=False, separators=(",", ":")))
        return 0

    database = None
    try:
        if os.environ.get("VALYQON_ASIA_OPERATIONS_ENABLED") != "1":
            raise ValueError("Explicit operator enablement required.")
        if args.source and args.search is None:
            raise ValueError("Source filter requires search mode.")
        if args.search is not None:
            if not _QUERY.fullmatch(args.search.strip()) or not 1 <= args.limit <= MAX_RETURNED:
                raise ValueError("Invalid search input.")
        from app.database.backend import Database
        from app.database.config import load_database_settings
        from .opportunities import OpportunityRepository

        if args.enqueue:
            from app.jobs import JobRepository, JobService, load_job_settings
            from app.monitoring.config import load_monitoring_settings
            from .catalog import build_source_catalog
            from .ingestion import ConnectorSyncService

            catalog = build_source_catalog(load_monitoring_settings())
            now = datetime.now(timezone.utc)
            validated = validate_sources(catalog, now=now)
            database = Database(load_database_settings())
            jobs = JobRepository(database, load_job_settings())
            jobs.initialize()
            service = ConnectorSyncService(JobService(jobs), catalog)
            output = []
            for source in validated:
                job = service.enqueue(source, now=now)
                output.append({"source": source, "job_id": job.id, "state": job.state})
            print(json.dumps({
                "mode": "queued", "source_count": len(output), "jobs": output,
                "requires_running_connector_worker": True,
            }, ensure_ascii=False, separators=(",", ":")))
            return 0

        database = Database(load_database_settings())
        opportunities = OpportunityRepository(database)
        rows = search_stored(opportunities, args.search, limit=args.limit, source=args.source)
        print(json.dumps({
            "mode": "stored_search", "query": args.search.strip(),
            "results": rows, "count": len(rows),
            "only_previously_ingested": True,
            "network_fetch": False,
        }, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception:
        # Do not expose operator DB credentials, private URLs or stack traces.
        print("Asian procurement operation failed; verify flags, stored data and worker configuration.")
        return 2
    finally:
        if database is not None:
            database.close()


if __name__ == "__main__":
    raise SystemExit(main())
