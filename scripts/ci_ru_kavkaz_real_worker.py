"""Genuine Kavkaz.RF original details -> leased/fenced worker -> disposable SQL.

Mandatory hosted network gate: fixture is NEVER substituted for live HTML.
No production DB, auth cookies, secrets, proxy, TLS bypass or redirects.
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
from app.sources.catalog import SourceCatalog
from app.sources.ingestion import JOB_TYPE, ConnectorSyncHandler, ConnectorSyncService, connector_version
from app.sources.kavkaz_rf_firstparty import KavkazRfFirstpartySource, SOURCE_ID, HOST, _canonical
from app.sources.multi import MultiSourceFetcher
from app.sources.opportunities import OpportunityRepository
from app.sources.registry import SourceRegistration, SourceRegistry, SourceTransport, SourceCapabilities
from app.sources.snapshots import snapshot_catalog


def isolated_catalog():
    registry = SourceRegistry((
        SourceRegistration(
            key=SOURCE_ID, display_name="Kavkaz.RF genuine corporate procurements",
            source=KavkazRfFirstpartySource(), transport=SourceTransport.HTML,
            jurisdictions=("RU",), languages=("ru",),
            homepage_url="https://" + HOST + "/purchases_sales/zakupki/tekushchie-/",
            official=False, enabled=True, capabilities=SourceCapabilities(),
        ),
    ))
    return SourceCatalog(registry=registry, fetcher=MultiSourceFetcher(registry, concurrency=1))


def proof():
    catalog = isolated_catalog()
    assert SOURCE_ID in catalog.enabled_keys
    with tempfile.TemporaryDirectory(prefix="valyqon-kavkaz-rf-") as tmp:
        database = Database(DatabaseSettings("ru-kavkaz-real", Path(tmp) / "proof.sqlite"))
        try:
            jobs = JobRepository(database, JobSettings(lease_seconds=240, heartbeat_seconds=10))
            jobs.initialize()
            store = OpportunityRepository(database)
            store.initialize()
            claim = ConnectorSyncService(jobs, catalog).enqueue(SOURCE_ID)
            handlers = HandlerRegistry()
            handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, store, max_records=2))
            if not Worker(jobs, handlers, job_types=(JOB_TYPE,)).run_once():
                raise AssertionError("Kavkaz.RF real leased worker did not claim")
            completed = jobs.get(claim.id, scope=JobScope())
            if completed is None or completed.state != "succeeded":
                raise AssertionError(
                    "Kavkaz.RF real worker did not succeed: "
                    + str(completed.failure_code if completed else "missing")
                )
            stats = completed.result
            if (stats["fetched_count"] != 2 or stats["accepted_count"] != 2
                    or stats["inserted_count"] != 2 or stats["skipped_count"] != 0):
                raise AssertionError("Kavkaz.RF two independent genuine originals not durably inserted")
            rows = store.read(SOURCE_ID, limit=2)
            if len(rows) != 2 or len({n.external_id for n in rows}) != 2:
                raise AssertionError("Kavkaz.RF native IDs missing or duplicate")
            snapshot = snapshot_catalog(catalog, store)
            for notice in rows:
                if (notice.tender_number != notice.external_id
                        or _canonical(notice.url) != notice.url
                        or notice.initial_price is None
                        or not notice.published_at
                        or notice.customer != "АО «КАВКАЗ.РФ»"):
                    raise AssertionError("Stored original notice metadata not corroborated")
                result = asyncio.run(snapshot.fetch(
                    source_keys=(SOURCE_ID,), search_terms=(notice.external_id,),
                    limit_per_source=2,
                ))
                if result.failures or not any(
                    item.identity == notice.identity and item.url == notice.url
                    for item in result.notices
                ):
                    raise AssertionError("Genuine Kavkaz.RF notice not keyword/ID searchable")
                if store.upsert(notice, connector_version(SOURCE_ID)):
                    raise AssertionError("Idempotent worker replay inserted duplicate")
            return {
                "native_details_verified": len(rows),
                "fenced_worker_inserted": stats["inserted_count"],
                "sql_id_queries_found": len(rows),
                "idempotent": True,
                "production_changed": False,
                "site_independent_from_eis_not_proved": True,
            }
        finally:
            database.close()


def main():
    try:
        evidence = proof()
    except Exception as exc:
        print("RU_KAVKAZ_REAL_WORKER=BLOCKED")
        print("FAILURE_CLASS=" + type(exc).__name__)
        print("FAILURE_REASON=" + str(exc).replace("\n", " ")[:200])
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_KAVKAZ_PROOF=" + json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    print("RU_KAVKAZ_REAL_WORKER=PASS")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
