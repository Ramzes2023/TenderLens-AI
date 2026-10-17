"""Strict TEK-Torg public listing + every detail -> actual worker -> SQLite.

Never invent notice dates/prices. No external credentials, persistent DB or LLM.
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

SOURCE = "tektorg"


def proof():
    settings = MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=5,
        max_notifications_per_cycle=5, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        tektorg_public_enabled=True,
    )
    catalog = build_source_catalog(settings)
    if SOURCE not in catalog.enabled_keys:
        raise AssertionError("TEK-Torg not explicitly enabled")
    with tempfile.TemporaryDirectory(prefix="valyqon-tektorg-real-") as tmp:
        db = Database(DatabaseSettings("ru-tektorg-proof", Path(tmp)/"real.sqlite"))
        try:
            store = OpportunityRepository(db)
            store.initialize()
            worker = ConnectorSyncHandler(catalog, store, max_records=5)
            ctx = SimpleNamespace(job=SimpleNamespace(scope=JobScope()), should_stop=False)
            params = {"schema":1, "source_id":SOURCE,
                      "sync_window":sync_window(), "connector_version":connector_version(SOURCE)}
            stats = worker(ctx, params)
            if not 1 <= stats["fetched_count"] <= 5:
                raise AssertionError("No independently verified live TEK-Torg notices")
            if (stats["fetched_count"] != stats["accepted_count"]
                    or stats["fetched_count"] != stats["inserted_count"]
                    or stats["skipped_count"] != 0):
                raise AssertionError("TEK-Torg durable ingestion incomplete")
            stored = store.read(SOURCE,limit=5)
            if len(stored) != stats["fetched_count"]:
                raise AssertionError("Missing TEK-Torg SQL rows")
            snapshot = snapshot_catalog(catalog,store)
            for n in stored:
                if n.url != f"https://www.tektorg.ru/223-fz/procedures/{n.external_id}":
                    raise AssertionError("Noncanonical TEK-Torg detail URL")
                report = asyncio.run(snapshot.fetch(
                    source_keys=(SOURCE,), search_terms=(n.external_id,),
                    limit_per_source=5,
                ))
                if report.failures or not any(
                    item.identity == n.identity and item.url == n.url
                    for item in report.notices
                ):
                    raise AssertionError("Stored TEK-Torg record not found")
                if store.upsert(n,connector_version(SOURCE)):
                    raise AssertionError("Duplicate TEK-Torg identity inserted")
            return {"real_detail_verified":len(stored), "worker_inserted":stats["inserted_count"],
                    "sqlite_search_verified":len(stored),
                    "idempotent_replay":True, "production_changed":False}
        finally:
            db.close()


def main():
    try:
        result = proof()
    except Exception as e:
        print("RU_TEKTORG_REAL_WORKER=BLOCKED")
        print("FAILURE_CLASS="+type(e).__name__)
        print("PRODUCTION_CHANGED=NO")
        return 1
    print("RU_TEKTORG_REAL_WORKER_EVIDENCE="+json.dumps(result,sort_keys=True))
    print("RU_TEKTORG_REAL_WORKER=PASS")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
