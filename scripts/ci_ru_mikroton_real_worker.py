"""Strict real MikroTon -> actual durable connector handler -> ephemeral SQLite/search.

No mocked source records, account credentials, production database, redirects,
TLS bypass or LLM service. Nonempty real public data is mandatory.
"""
import asyncio
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs.models import JobScope
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import ConnectorSyncHandler, connector_version, sync_window
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog

SOURCE = "mikroton_tender"


def acceptance():
    settings = MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=10,
        max_notifications_per_cycle=5, request_timeout=15,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        mikroton_tender_enabled=True,
    )
    catalog = build_source_catalog(settings)
    if SOURCE not in catalog.enabled_keys:
        raise AssertionError("MikroTon was not explicitly enabled")
    with tempfile.TemporaryDirectory(prefix="valyqon-ru-mikroton-worker-") as directory:
        db = Database(DatabaseSettings("ru-mikroton-live-worker", Path(directory) / "notices.sqlite"))
        try:
            store = OpportunityRepository(db)
            store.initialize()
            worker = ConnectorSyncHandler(catalog, store, max_records=10)
            ctx = SimpleNamespace(job=SimpleNamespace(scope=JobScope()), should_stop=False)
            payload = {"schema": 1, "source_id": SOURCE,
                       "sync_window": sync_window(),
                       "connector_version": connector_version(SOURCE)}
            report = worker(ctx, payload)
            if (not 1 <= report["fetched_count"] <= 10
                    or report["accepted_count"] != report["fetched_count"]
                    or report["inserted_count"] != report["fetched_count"]
                    or report["skipped_count"] != 0
                    or report["updated_count"] != 0):
                raise AssertionError("No complete real worker ingestion")
            notices = store.read(SOURCE, limit=10)
            if len(notices) != report["fetched_count"]:
                raise AssertionError("Real worker database count mismatch")
            matches = 0
            snapshot = snapshot_catalog(catalog, store)
            for row in notices:
                if (row.source != SOURCE
                        or row.url != f"https://tender.mt52.ru/tenders/{row.external_id}"):
                    raise AssertionError("Bad canonical source URL")
                found = asyncio.run(snapshot.fetch(
                    source_keys=(SOURCE,),
                    search_terms=(row.external_id,), limit_per_source=10,
                ))
                # Keyword search is substring-based, not an exact-ID filter:
                # short numeric IDs can occur in dates/prices of other notices.
                # Require the exact notice identity AND URL among results.
                if (found.failures or not any(
                        hit.identity == row.identity and hit.url == row.url
                        for hit in found.notices
                )):
                    raise AssertionError("Real worker keyword-search mismatch")
                # Replaying identical normalized notices changes no identities.
                if store.upsert(row, connector_version(SOURCE)):
                    raise AssertionError("Real worker identity was duplicated")
                matches += 1
            return {"real_fetched": report["fetched_count"],
                    "real_worker_inserted": report["inserted_count"],
                    "db_search_identities": matches,
                    "duplicate_replay_inserted": 0,
                    "production_changed": False}
        finally:
            db.close()


def main():
    try:
        evidence = acceptance()
    except Exception as error:
        print("RU_MIKROTON_LIVE_WORKER=BLOCKED")
        print("FAILURE_CLASS=" + type(error).__name__)
        print("PRODUCTION_CHANGED=NO")
        return 1
    print("RU_MIKROTON_LIVE_WORKER_EVIDENCE=" + json.dumps(evidence, sort_keys=True))
    print("RU_MIKROTON_LIVE_WORKER=PASS")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
