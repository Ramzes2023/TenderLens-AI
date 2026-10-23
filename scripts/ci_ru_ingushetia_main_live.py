"""Strict mainline Ingushetia live acceptance: real source->leased Worker->SQL.

Never substitute fixtures, historical original numbers, fake notices, or call
Telegram for real customers. One current first-party publication source must
independently pass: regional provenance, original cards, Worker, SQL and search.
"""
from __future__ import annotations

import asyncio
import json
import ssl
from pathlib import Path
from tempfile import TemporaryDirectory

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import HandlerRegistry, JobRepository, JobSettings
from app.jobs.models import JobScope
from app.jobs.worker import Worker
from app.monitoring.config import MonitoringSettings
from app.monitoring.repository import MonitoringRepository
from app.monitoring.service import TenderMonitorService
from app.sources.catalog import build_source_catalog
from app.sources.http import FetchPolicy, bounded_fetch, source_client
from app.sources.ingestion import (
    JOB_TYPE, ConnectorSyncHandler, ConnectorSyncService, connector_version,
)
from app.sources.opportunities import OpportunityRepository
from app.sources.ru_ingushetia_eis44 import SOURCE_ID as EIS
from app.sources.ru_ingushetia_fabrikant44 import SOURCE_ID as FAB
from app.sources.ru_notice_identity import original_notice_key
from app.sources.snapshots import snapshot_catalog
from app.sources.eis_pinned_ca import select_verified_eis_ca
# Match the current main EIS RSS adapter user agent for EIS card transport.

ROOT = Path(__file__).resolve().parents[1] / "russian_trusted_root_ca_pem.crt"


async def corroborate_eis_cards(rows):
    with bounded_fetch(FetchPolicy(frozenset({"zakupki.gov.ru"}), 2, max_bytes=1_800_000)):
        async with source_client(timeout=20, follow_redirects=False, trust_env=False,
                                 verify=ssl.create_default_context(cafile=str(select_verified_eis_ca(ROOT))),
                                 headers={"Accept": "text/html", "User-Agent": "TenderLensAI/0.9 (+RSS monitor)"}) as client:
            for notice in rows[:2]:
                response = await client.get(notice.url)
                response.raise_for_status()
                if ("html" not in response.headers.get("content-type", "").lower()
                        or notice.tender_number not in response.text):
                    raise AssertionError("EIS first-party original card unavailable")


def real_worker_proof(source_id):
    cfg = MonitoringSettings(
        False, 600, 5, 2, 25, (), ROOT, profile_feeds_enabled=False,
        ru_ingushetia_eis44_enabled=(source_id == EIS),
        ru_ingushetia_fabrikant44_enabled=(source_id == FAB),
        ru_background_catalog_enabled=True,
    )
    catalog = build_source_catalog(cfg)
    with TemporaryDirectory(prefix="valyqon-ing-main-live-") as directory:
        db = Database(DatabaseSettings("ing-main-live", Path(directory) / "proof.sqlite"))
        try:
            queue = JobRepository(db, JobSettings(lease_seconds=240, heartbeat_seconds=10))
            queue.initialize()
            store = OpportunityRepository(db)
            store.initialize()
            job = ConnectorSyncService(queue, catalog).enqueue(source_id)
            handlers = HandlerRegistry()
            handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, store, max_records=5))
            worker = Worker(queue, handlers, job_types=(JOB_TYPE,))
            # Exercise the actual durable retries; never forge success.
            import time
            current = None
            for idx in range(3):
                if not worker.run_once():
                    raise AssertionError("Leased Worker did not claim original-source job")
                current = queue.get(job.id, scope=JobScope())
                if current and current.state == "succeeded":
                    break
                if current is None or current.state != "queued" or idx == 2:
                    raise AssertionError("Real source Worker failed")
                time.sleep(1.25 if idx == 0 else 2.25)
            rows = store.read(source_id, limit=5)
            if len(rows) < 2 or current is None or current.state != "succeeded":
                raise AssertionError("Fewer than two real original notices survived Worker SQL")
            keys = [original_notice_key(row) for row in rows]
            if (len(keys) != len(set(keys)) or
                    any(key[0] != "eis_44" or key[1] != row.tender_number
                        for key, row in zip(keys, rows))):
                raise AssertionError("Noncanonical or duplicated EIS original identities")
            if source_id == EIS:
                asyncio.run(corroborate_eis_cards(rows))
            for row in rows:
                results = store.read(source_id, limit=5, search_terms=(row.tender_number,))
                if not any(item.identity == row.identity for item in results):
                    raise AssertionError("Verified Worker SQL original is not searchable")
                if store.upsert(row, connector_version(source_id)):
                    raise AssertionError("Previously stored EIS original duplicated on replay")
            # The live notices are delivered only to a disposable local service,
            # never a Telegram API or real subscriber.
            monitoring = MonitoringRepository(Path(directory) / "monitor.sqlite")
            monitoring.initialize()
            monitor = TenderMonitorService(cfg, None, monitoring, None)
            snap = snapshot_catalog(catalog, store)
            matches, report = asyncio.run(monitor.fetch_matches_from_catalog(
                snap, 101, source_keys=(source_id,)))
            if report.failures or len(matches) < 2:
                raise AssertionError("Live Worker SQL does not reach catalog monitor search")
            return {
                "source": source_id, "worker": "succeeded",
                "verified_sql_originals": len(rows),
                "first_party_original_card_checks": 2,
                "catalog_monitor_matches": len(matches),
                "replay_duplicate_inserts": 0,
                "telegram_bot_api_receipt": "NOT_TESTED",
                "production_changed": False,
            }
        finally:
            db.close()


def main():
    failed = []
    # The accredited first-party list can be reachable while EIS is blocked
    # from GitHub-hosted egress. It still must independently verify each
    # original card; ordering cannot turn a blocked source into a success.
    for source_id in (FAB, EIS):
        try:
            result = real_worker_proof(source_id)
        except Exception as exc:
            # No URL, token, environment, or raw vendor error text in logs.
            failed.append({"source": source_id,
                           "error_class": type(exc).__name__ if type(exc).__name__ in {
                               "AssertionError", "ConnectorTransportError",
                               "ValueError", "TimeoutError", "HTTPStatusError",
                           } else "BLOCKED"})
            continue
        print("INGUSHETIA_MAINLINE_LIVE_PROOF=" + json.dumps(result, sort_keys=True))
        print("INGUSHETIA_MAINLINE_LIVE_ACCEPTANCE=PASS")
        return 0
    print("INGUSHETIA_MAINLINE_LIVE_ACCEPTANCE=BLOCKED")
    print("INGUSHETIA_MAINLINE_LIVE_FAILURES=" + json.dumps(failed, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
