"""MAIN-FORWARD live Ingushetia acceptance; no fixtures and no actual Telegram.

Accepts a real source only after publisher-owned current discovery -> leased
Worker -> disposable SQL -> tenant title/number search -> isolated monitor
acknowledgement. EIS checks actual original HTML cards; accredited Fabrikant
already checks every independent original inside its adapter.
"""
from __future__ import annotations

import asyncio
import json
import time
import ssl
import tempfile
from pathlib import Path
from types import SimpleNamespace

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import HandlerRegistry, JobRepository, JobSettings
from app.jobs.models import JobScope
from app.jobs.worker import Worker
from app.monitoring.config import MonitoringSettings
from app.monitoring.repository import MonitoringRepository
from app.monitoring.service import TenderMonitorService
from app.bot.monitoring import monitor_loop
from app.sources.catalog import build_source_catalog
from app.sources.eis_pinned_ca import select_verified_eis_ca
from app.sources.http import FetchPolicy, bounded_fetch, source_client
from app.sources.ingestion import JOB_TYPE, ConnectorSyncHandler, ConnectorSyncService, connector_version
from app.sources.opportunities import OpportunityRepository
from app.sources.ru_notice_identity import original_notice_key
from app.sources.snapshots import snapshot_catalog

EIS = "ru_ingushetia_eis44"
ETP = "ru_ingushetia_fabrikant44"

def _settings(source):
    ca = select_verified_eis_ca()
    return MonitoringSettings(
        enabled=True, interval_seconds=600, max_items=3,
        max_notifications_per_cycle=2, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=ca,
        profile_feeds_enabled=False, ru_background_catalog_enabled=True,
        ru_ingushetia_eis44_enabled=(source == EIS),
        ru_ingushetia_fabrikant44_enabled=(source == ETP),
    )

async def _independent_eis_details(notices, ca):
    # Never infer original card validity solely from a published RSS URL.
    context = ssl.create_default_context(cafile=str(ca))
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    with bounded_fetch(FetchPolicy(frozenset({"zakupki.gov.ru"}), len(notices), max_bytes=1_800_000)):
        async with source_client(timeout=20, verify=context, trust_env=False,
                                 follow_redirects=False,
                                 headers={"Accept":"text/html","User-Agent":"TenderLensAI/0.9 (+RSS monitor)"}) as client:
            for n in notices:
                response = await client.get(n.url)
                response.raise_for_status()
                if "html" not in response.headers.get("content-type", "").lower():
                    raise AssertionError("EIS original card was not HTML")
                if n.tender_number not in response.text:
                    raise AssertionError("EIS original card did not show publisher number")

async def _isolated_alerts(cat, settings, repo, db_file, notices):
    out = MonitoringRepository(db_file)
    out.initialize()
    owner, chat = 857001, 857002
    out.set_subscription(owner, chat, True)
    srv = TenderMonitorService(settings, None, out, None)
    snapshot = snapshot_catalog(cat, repo)
    found, report = await srv.fetch_matches_from_catalog(
        snapshot, owner, source_keys=tuple(n.source for n in notices[:1]),
    )
    if report.failures or len(found) < 2:
        raise AssertionError("SQL snapshot did not reach monitor")
    stop = asyncio.Event()
    class Sink:
        def __init__(self):
            self.received = []
        async def send_message(self, chat_id, text, **kwargs):
            if chat_id != chat or "НОВАЯ ЗАКУПКА" not in text:
                raise AssertionError("Bad isolated dispatch")
            self.received.append(text)
            stop.set()
            return SimpleNamespace(message_id=len(self.received))
    sink = Sink()
    await asyncio.wait_for(monitor_loop(sink, srv, stop, source_catalog=snapshot), timeout=30)
    if len(sink.received) != 2:
        raise AssertionError("Two independent simulated acknowledgements required")
    matched = [n for n in notices if any(n.tender_number in msg for msg in sink.received)]
    if len(matched) != 2 or any(not out.seen(owner, "eis_44", n.tender_number) for n in matched):
        raise AssertionError("Durable upstream-original acknowledgement missing")
    return len(sink.received)

def proof(source):
    settings = _settings(source)
    cat = build_source_catalog(settings)
    assert source in cat.enabled_keys
    with tempfile.TemporaryDirectory(prefix="valyqon-main-first-ing-") as td:
        d = Path(td)
        db = Database(DatabaseSettings("main-forward-ing", d / "notices.sqlite"))
        try:
            queue = JobRepository(db, JobSettings(lease_seconds=240, heartbeat_seconds=10))
            queue.initialize()
            records = OpportunityRepository(db)
            records.initialize()
            job = ConnectorSyncService(queue, cat).enqueue(source)
            handlers = HandlerRegistry()
            handlers.register(JOB_TYPE, ConnectorSyncHandler(cat, records, max_records=3))
            worker = Worker(queue, handlers, job_types=(JOB_TYPE,))
            done = None
            for attempt in range(3):
                if not worker.run_once():
                    raise AssertionError("WORKER_NOT_CLAIMED")
                done = queue.get(job.id, scope=JobScope())
                if done is not None and done.state == "succeeded":
                    break
                if done is None:
                    raise AssertionError("WORKER_RESULT_MISSING")
                if done.state != "queued":
                    raise AssertionError("WORKER_FINAL_FAILURE")
                if attempt == 2:
                    raise AssertionError("WORKER_RETRIES_EXHAUSTED")
                # Real durable queue retry, not a simulated successful job:
                # preserve the job identity, lease/fencing and SQL checks.
                time.sleep((1.25, 2.25)[attempt])
            if done is None or done.state != "succeeded":
                raise AssertionError("WORKER_NOT_SUCCEEDED")
            saved = records.read(source, limit=3)
            if len(saved) < 2 or len({original_notice_key(n) for n in saved}) != len(saved):
                raise AssertionError("At least two genuine distinct SQL original IDs required")
            if source == EIS:
                asyncio.run(_independent_eis_details(saved[:2], settings.ca_bundle_file))
            snapshot = snapshot_catalog(cat, records)
            for n in saved:
                for query in (n.tender_number, n.title):
                    report = asyncio.run(snapshot.fetch(
                        source_keys=(source,), search_terms=(query,), limit_per_source=3))
                    if report.failures or not any(x.tender_number == n.tender_number for x in report.notices):
                        raise AssertionError("SQL user title/number search lost original")
                if records.upsert(n, connector_version(source)):
                    raise AssertionError("Duplicate original reinserted")
            ack = asyncio.run(_isolated_alerts(cat, settings, records, d / "monitor.sqlite", saved))
            return dict(source=source, real_originals=len(saved), worker=done.state,
                        sql_search=True, isolated_acks=ack, replay_duplicates=0,
                        telegram_bot_api_receipt="NOT_TESTED", production_changed=False)
        finally:
            db.close()

def main():
    failures=[]
    known = {
        "WORKER_NOT_CLAIMED", "WORKER_RESULT_MISSING",
        "WORKER_FINAL_FAILURE", "WORKER_RETRIES_EXHAUSTED",
        "WORKER_NOT_SUCCEEDED",
        "At least two genuine distinct SQL original IDs required",
        "SQL user title/number search lost original",
        "Duplicate original reinserted",
        "EIS original card was not HTML",
        "EIS original card did not show publisher number",
        "SQL snapshot did not reach monitor",
        "Two independent simulated acknowledgements required",
        "Durable upstream-original acknowledgement missing",
    }
    for src in (EIS, ETP):
        try:
            result=proof(src)
        except Exception as exc:
            # Expose only allowlisted source-owned stages: no exception
            # payload, HTTP URL, token, customer data or upstream HTML.
            stage = str(exc) if type(exc) is AssertionError and str(exc) in known else "NETWORK_OR_HANDLER_FAILURE"
            failures.append(dict(source=src, error_type=type(exc).__name__, stage=stage))
            continue
        print("INGUSHETIA_MAIN_FORWARD_LIVE=" + json.dumps(result, sort_keys=True))
        print("INGUSHETIA_MAIN_FORWARD_ACCEPTANCE=PASS")
        print("REAL_USER_TELEGRAM_RECEIPT=NOT_TESTED; PRODUCTION_CHANGED=NO")
        return 0
    print("INGUSHETIA_MAIN_FORWARD_ACCEPTANCE=BLOCKED")
    print("SOURCE_FAILURE_TYPES=" + json.dumps(failures, sort_keys=True))
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
