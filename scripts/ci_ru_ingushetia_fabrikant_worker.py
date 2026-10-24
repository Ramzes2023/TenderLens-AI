"""STRICT live ETP Ingushetia original -> leased Worker -> SQL -> user query -> isolated alert.

Do not equate this accredited EIS mirror to a distinct publisher. This script
will FAIL if the current public first-party q=INN search is blocked, empty,
irrelevant, or fails individual same-host original detail checks. No fixtures,
archived ID lists, real Telegram sends, or production mutation are permitted.
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
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import JOB_TYPE, ConnectorSyncHandler, ConnectorSyncService, connector_version
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog
from app.sources.ru_ingushetia_fabrikant44 import SOURCE_ID
from app.sources.ru_notice_identity import original_notice_key
from scripts.ci_ru_ingushetia_live_worker import _check_isolated_dispatch


def proof():
    cfg = MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=3,
        max_notifications_per_cycle=3, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        ru_background_catalog_enabled=True,
        ru_ingushetia_fabrikant44_enabled=True,
    )
    catalog = build_source_catalog(cfg)
    assert SOURCE_ID in catalog.enabled_keys

    # This fetch is really issued to the CURRENT first-party searchable list.
    # Every returned row must have a checked independent first-party detail.
    originals = asyncio.run(catalog.registry.get(SOURCE_ID).source.fetch(limit=3))
    if len(originals) < 2:
        raise AssertionError("Not enough current independently verified Ingushetia originals")
    verified_ids = {n.tender_number for n in originals}
    if len(verified_ids) != len(originals) or any(
        original_notice_key(n) != ("eis_44", n.tender_number) for n in originals
    ):
        raise AssertionError("Noncanonical duplicated 44-FZ publisher identities")

    with tempfile.TemporaryDirectory(prefix="valyqon-ru-ing-fabrikant-") as d:
        db = Database(DatabaseSettings("ingush-verified-vendor", Path(d) / "worker.sqlite"))
        try:
            jobs = JobRepository(db, JobSettings(lease_seconds=240, heartbeat_seconds=10))
            jobs.initialize()
            store = OpportunityRepository(db)
            store.initialize()
            job = ConnectorSyncService(jobs, catalog).enqueue(SOURCE_ID)
            handlers = HandlerRegistry()
            handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, store, max_records=3))
            if not Worker(jobs, handlers, job_types=(JOB_TYPE,)).run_once():
                raise AssertionError("Official first-party mirrored notices Worker not claimed")
            completed = jobs.get(job.id, scope=JobScope())
            if completed is None or completed.state != "succeeded":
                raise AssertionError("Real original-card leased Worker failed")
            rows = store.read(SOURCE_ID, limit=3)
            if len(rows) < 2 or not verified_ids <= {n.tender_number for n in rows}:
                raise AssertionError("Verified current original IDs lost during Worker and SQLite")
            search = snapshot_catalog(catalog, store)
            for n in rows:
                for keyword in (n.tender_number, n.title):
                    report = asyncio.run(search.fetch(
                        source_keys=(SOURCE_ID,), search_terms=(keyword,),
                        limit_per_source=3,
                    ))
                    if report.failures or not any(
                        m.identity == n.identity and m.url == n.url for m in report.notices
                    ):
                        raise AssertionError("Official first-party Ingushetia tender not found in tenant search")
                if store.upsert(n, connector_version(SOURCE_ID)):
                    raise AssertionError("Original-number replay created duplicate")
            acknowledged = asyncio.run(_check_isolated_dispatch(
                catalog, cfg, rows, Path(d) / "monitor.sqlite", source_id=SOURCE_ID,
            ))
            if acknowledged != min(len(rows), cfg.max_notifications_per_cycle):
                raise AssertionError("Isolated monitor failed to acknowledge verified rows")
            return {
                "official_first_party_current_originals": len(verified_ids),
                "worker_state": completed.state,
                "sql_and_title_number_search": len(rows),
                "isolated_notification_ack": acknowledged,
                "original_ids_not_double_counted_as_eis": True,
                "production_changed": False,
                "real_telegram_delivery_proven": False,
            }
        finally:
            db.close()


def main():
    try:
        result = proof()
    except Exception as exc:
        print("INGUSHETIA_FABRIKANT_LIVE_WORKER=BLOCKED")
        print("FAILURE_CLASS=" + type(exc).__name__)
        if type(exc) is AssertionError:
            print("FAILURE_CONTRACT=" + str(exc)[:200].replace("\n", " "))
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("INGUSHETIA_FABRIKANT_EVIDENCE=" + json.dumps(result, sort_keys=True))
    print("INGUSHETIA_FABRIKANT_LIVE_WORKER=PASS")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
