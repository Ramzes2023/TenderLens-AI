"""Live acceptance: 20 genuine Samara page 0+1 notices -> fenced Worker -> SQL.

All rows come from first-party HTTPS in current run, NOT synthetic fixtures.
Read-only upstream, ephemeral local database, no subscriber messaging or prod
activation. Per-notice original detail pages still NOT independently proven.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import HandlerRegistry, JobRepository, JobSettings
from app.jobs.models import JobScope
from app.jobs.worker import Worker
from app.sources.ingestion import (
    JOB_TYPE, ConnectorSyncHandler, ConnectorSyncService, connector_version,
)
from app.sources.opportunities import OpportunityRepository
from app.sources.ru_samara_public_list import SOURCE_ID, GRID
from app.sources.snapshots import snapshot_catalog
from scripts.ci_ru_samara_public_list_sql import make_research_catalog


def acceptance():
    catalog = make_research_catalog()
    with tempfile.TemporaryDirectory(prefix="valyqon-samara-20-real-") as tmp:
        db = Database(DatabaseSettings("ru-samara-20", Path(tmp) / "real.sqlite"))
        try:
            queue = JobRepository(db, JobSettings(
                lease_seconds=240, heartbeat_seconds=10,
            ))
            queue.initialize()
            store = OpportunityRepository(db)
            store.initialize()
            submitted = ConnectorSyncService(queue, catalog).enqueue(SOURCE_ID)
            handlers = HandlerRegistry()
            handlers.register(JOB_TYPE, ConnectorSyncHandler(
                catalog, store, max_records=20,
            ))
            if not Worker(queue, handlers, job_types=(JOB_TYPE,)).run_once():
                raise AssertionError("Samara page 0+1 leased job not claimed")
            completed = queue.get(submitted.id, scope=JobScope())
            if completed is None or completed.state != "succeeded":
                raise AssertionError("Samara page 0+1 real Worker failed")
            counts = completed.result
            if any(counts[k] != 20 for k in (
                    "fetched_count", "accepted_count", "inserted_count")):
                raise AssertionError("Twenty genuine native rows were not persisted")
            rows = store.read(SOURCE_ID, limit=20)
            if (len(rows) != 20
                    or len({r.external_id for r in rows}) != 20
                    or len({r.tender_number for r in rows}) != 20
                    or any(r.url != GRID or r.deadline is not None
                           or r.initial_price is not None for r in rows)):
                raise AssertionError("Unsafe or repeated Samara SQL notice provenance")
            source = snapshot_catalog(catalog, store)
            checked = 0
            for notice in (rows[0], rows[9], rows[10], rows[19]):
                match = asyncio.run(source.fetch(
                    source_keys=(SOURCE_ID,),
                    search_terms=(notice.external_id,),
                    limit_per_source=20,
                ))
                if match.failures or not any(
                    x.external_id == notice.external_id for x in match.notices
                ):
                    raise AssertionError("A genuine Samara page-1 SQL ID is missing")
                if store.upsert(notice, connector_version(SOURCE_ID)):
                    raise AssertionError("Replay inserted duplicate Samara native ID")
                checked += 1
            miss = asyncio.run(source.fetch(
                source_keys=(SOURCE_ID,),
                search_terms=("valyqon_samara_nonexistent_908721312",),
                limit_per_source=20,
            ))
            if miss.failures or miss.notices:
                raise AssertionError("Unmatched tenant query leaked Samara records")
            return {
                "real_original_list_notices": len(rows),
                "distinct_native_ids": len({r.external_id for r in rows}),
                "two_original_pages": True,
                "fenced_worker_inserted": counts["inserted_count"],
                "sqlite_query_verified": checked,
                "unmatched_query_clean": True,
                "independent_original_details": False,
                "actual_telegram_delivered": False,
                "production_changed": False,
            }
        finally:
            db.close()


def main():
    try:
        evidence = acceptance()
    except Exception as error:
        print("RU_SAMARA_TWO_PAGE_WORKER_SQL=BLOCKED_" + type(error).__name__)
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_SAMARA_TWO_PAGE_EVIDENCE=" + json.dumps(
        evidence, sort_keys=True, ensure_ascii=False,
    ))
    print("RU_SAMARA_TWO_PAGE_WORKER_SQL=PASS_REAL_LIST_ONLY")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
