"""Strict GPB public listing + every detail -> actual worker -> SQLite.

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

SOURCE = "gpb_etp_public"


def proof():
    settings = MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=3,
        max_notifications_per_cycle=5, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        gpb_etp_public_enabled=True,
    )
    catalog = build_source_catalog(settings)
    if SOURCE not in catalog.enabled_keys:
        raise AssertionError("GPB not explicitly enabled")
    with tempfile.TemporaryDirectory(prefix="valyqon-gpb-real-") as tmp:
        db = Database(DatabaseSettings("ru-gpb-proof", Path(tmp)/"real.sqlite"))
        try:
            store = OpportunityRepository(db)
            store.initialize()
            worker = ConnectorSyncHandler(catalog, store, max_records=3)
            ctx = SimpleNamespace(job=SimpleNamespace(scope=JobScope()), should_stop=False)
            params = {"schema":1, "source_id":SOURCE,
                      "sync_window":sync_window(), "connector_version":connector_version(SOURCE)}
            stats = worker(ctx, params)
            if not 1 <= stats["fetched_count"] <= 3:
                raise AssertionError("No independently verified live GPB notices")
            if (stats["fetched_count"] != stats["accepted_count"]
                    or stats["fetched_count"] != stats["inserted_count"]
                    or stats["skipped_count"] != 0):
                raise AssertionError("GPB durable ingestion incomplete")
            stored = store.read(SOURCE,limit=3)
            if len(stored) != stats["fetched_count"]:
                raise AssertionError("Missing GPB SQL rows")
            snapshot = snapshot_catalog(catalog,store)
            for n in stored:
                if not n.url.startswith(f"https://etpgpb.ru/procedures/etp/{n.external_id}-"):
                    raise AssertionError("Noncanonical GPB detail URL")
                report = asyncio.run(snapshot.fetch(
                    source_keys=(SOURCE,), search_terms=(n.external_id,),
                    limit_per_source=5,
                ))
                if report.failures or not any(
                    item.identity == n.identity and item.url == n.url
                    for item in report.notices
                ):
                    raise AssertionError("Stored GPB record not found")
                if store.upsert(n,connector_version(SOURCE)):
                    raise AssertionError("Duplicate GPB identity inserted")
            return {"real_detail_verified":len(stored), "worker_inserted":stats["inserted_count"],
                    "sqlite_search_verified":len(stored),
                    "idempotent_replay":True, "production_changed":False}
        finally:
            db.close()


def main():
    try:
        result = proof()
    except Exception as e:
        print("RU_GPB_REAL_WORKER=BLOCKED")
        print("FAILURE_CLASS="+type(e).__name__)
        # Only the explicit public source and isolated test DB are accessed.
        # Keep the failure category/proximal cause visible for actual fixes.
        cause = e.__cause__ or e.__context__
        print("FAILURE_REASON="+str(e).replace("\\n", " ")[:350])
        if cause is not None:
            print("FAILURE_CAUSE_CLASS="+type(cause).__name__)
            print("FAILURE_CAUSE="+str(cause).replace("\\n", " ")[:350])
        print("PRODUCTION_CHANGED=NO")
        return 1
    print("RU_GPB_REAL_WORKER_EVIDENCE="+json.dumps(result,sort_keys=True))
    print("RU_GPB_REAL_WORKER=PASS")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
