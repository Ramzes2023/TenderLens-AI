"""Genuine Samara 3-page list -> leased/fenced Worker -> SQLite -> user lookup.

Read-only upstream; synthetic database and no real subscriber messages.
This does not independently prove detail-page price, deadline or documents.
"""
from __future__ import annotations

import asyncio
import json
import re
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
    with tempfile.TemporaryDirectory(prefix="valyqon-samara-30-real-") as tmp:
        db = Database(DatabaseSettings("ru-samara-30", Path(tmp) / "real.sqlite"))
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
                catalog, store, max_records=30,
            ))
            if not Worker(queue, handlers, job_types=(JOB_TYPE,)).run_once():
                raise AssertionError("Samara page 2 leased job not claimed")
            completed = queue.get(submitted.id, scope=JobScope())
            if completed is None or completed.state != "succeeded":
                raise AssertionError("Samara page 2 original-list Worker failed")
            counts = completed.result
            if any(counts[k] != 30 for k in (
                    "fetched_count", "accepted_count", "inserted_count")):
                raise AssertionError("Thirty original native rows were not persisted")
            rows = store.read(SOURCE_ID, limit=30)
            if (len(rows) != 30
                    or len({r.external_id for r in rows}) != 30
                    or len({r.tender_number for r in rows}) != 30
                    or any(r.url != GRID or (r.initial_price is not None and r.currency != "RUB")
                           or (r.deadline is not None and not isinstance(r.deadline, str)) for r in rows)):
                raise AssertionError("Unsafe/duplicated Samara SQL records")

            # The independent real grid probe confirmed price + publication
            # + collecting-end metadata are present in the original 30 rows.
            # Persisted notices must actually contain safely normalized values
            # too: HTTP 200 + 30 IDs alone is no longer enough for acceptance.
            metadata_counts = {
                "price": sum(r.initial_price is not None and r.currency == "RUB" for r in rows),
                "publication": sum(r.published_at is not None for r in rows),
                "deadline": sum(r.deadline is not None for r in rows),
            }
            if any(count == 0 for count in metadata_counts.values()):
                raise AssertionError("Original native Samara list fields were not persisted")
            if not any(r.initial_price is not None and r.deadline is not None
                       and r.published_at is not None for r in rows[20:]):
                raise AssertionError("No complete third-page list metadata persisted")

            snapshot = snapshot_catalog(catalog, store)
            probes = [rows[i] for i in (0, 9, 10, 19, 20, 29)]
            for notice in probes:
                matched = asyncio.run(snapshot.fetch(
                    source_keys=(SOURCE_ID,),
                    search_terms=(notice.external_id,),
                    limit_per_source=30,
                ))
                if matched.failures or not any(
                    x.external_id == notice.external_id for x in matched.notices
                ):
                    raise AssertionError("Original page-2 SQL ID not searchable")
                if store.upsert(notice, connector_version(SOURCE_ID)):
                    raise AssertionError("Repeated Samara record inserted duplicate")
            title_words = re.findall(r"[А-Яа-яЁёA-Za-z]{6,}", rows[29].title)
            if not title_words:
                raise AssertionError("Third-page title lacks a natural-language word")
            title_lookup = asyncio.run(snapshot.fetch(
                source_keys=(SOURCE_ID,),
                search_terms=(title_words[0],),
                limit_per_source=30,
            ))
            if title_lookup.failures or not any(
                x.external_id == rows[29].external_id for x in title_lookup.notices
            ):
                raise AssertionError("Third-page native title search failed")
            absent = asyncio.run(snapshot.fetch(
                source_keys=(SOURCE_ID,),
                search_terms=("valyqon_samara_unmatched_98236591",),
                limit_per_source=30,
            ))
            if absent.failures or absent.notices:
                raise AssertionError("Nonmatching user received unrelated tenders")
            return {
                "real_original_list_notices": len(rows),
                "unique_native_numbers": len({r.tender_number for r in rows}),
                "native_pages": 3,
                "lease_fenced_worker_inserted": counts["inserted_count"],
                "sqlite_original_id_queries": len(probes),
                "third_page_title_query": True,
                "negative_keyword_returns_none": True,
                "idempotent": True,
                "list_price_present": metadata_counts["price"],
                "list_deadline_present": metadata_counts["deadline"],
                "list_publication_present": metadata_counts["publication"],
                "independent_details_verified": False,
                "real_external_message_sent": False,
                "production_changed": False,
            }
        finally:
            db.close()


def main():
    try:
        result = acceptance()
    except Exception as error:
        print("RU_SAMARA_THREE_PAGE_WORKER_SQL=BLOCKED_" + type(error).__name__)
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_SAMARA_THREE_PAGE_EVIDENCE=" + json.dumps(
        result, sort_keys=True, ensure_ascii=False,
    ))
    print("RU_SAMARA_THREE_PAGE_WORKER_SQL=PASS_REAL_LIST_ONLY")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
