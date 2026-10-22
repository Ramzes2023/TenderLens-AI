"""Strict real Chechnya EIS RSS -> fenced Worker -> SQLite -> query -> local alert.

NO fixture tender can make this pass. No production writes.  LocalCaptureBot is
NOT the external Telegram API and is never described as actual delivery.
Run only after placing a region-filtered official EIS 44-FZ RSS URL in
RU_CHECHNYA_EIS_RSS_URLS and opting in via RU_CHECHNYA_EIS_ENABLED=true.
"""
from __future__ import annotations

import asyncio
import json
import re
import tempfile
from pathlib import Path

from app.bot.monitoring import enabled_ru_catalog_keys, monitor_loop
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import HandlerRegistry, JobRepository, JobSettings
from app.jobs.models import JobScope
from app.jobs.worker import Worker
from app.monitoring.config import MonitoringSettings, load_monitoring_settings
from app.monitoring.repository import MonitoringRepository
from app.monitoring.service import TenderMonitorService, prefilter_notice
from app.scoring.models import CompanyProfile
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import (
    JOB_TYPE, ConnectorSyncHandler, ConnectorSyncService, connector_version,
)
from app.sources.opportunities import OpportunityRepository
from app.sources.ru_chechnya_eis_rss import SOURCE_KEY, is_chechnya_notice
from app.sources.snapshots import snapshot_catalog


class LocalCaptureBot:
    def __init__(self, stop):
        self.stop = stop
        self.messages = []

    async def send_message(self, chat_id, text, **kwargs):
        if chat_id != 99102 or "Источник: " + SOURCE_KEY not in text:
            raise AssertionError("Unexpected local alert payload or recipient")
        if not kwargs.get("disable_web_page_preview"):
            raise AssertionError("Expected original-link preview to be disabled")
        self.messages.append(text)
        self.stop.set()
        # Shape-compatible local-only synthetic receipt. The shared
        # production acknowledgement validation is separately gated;
        # this MUST NOT be reported as external Telegram API delivery.
        from types import SimpleNamespace
        return SimpleNamespace(
            message_id=len(self.messages),
            chat=SimpleNamespace(id=chat_id),
        )


def isolated_settings():
    # Read operator's actual endpoint and official TLS trust setting, while
    # making other sources and production delivery impossible in this proof.
    cfg = load_monitoring_settings()
    if not cfg.ru_chechnya_eis_enabled or not cfg.ru_chechnya_eis_rss_urls:
        raise AssertionError("Operator opt-in and official Chechnya EIS RSS URL required")
    return MonitoringSettings(
        enabled=True, interval_seconds=60, max_items=5,
        max_notifications_per_cycle=5, request_timeout=min(cfg.request_timeout, 30),
        eis_rss_urls=(), ca_bundle_file=cfg.ca_bundle_file,
        profile_feeds_enabled=False, ru_chechnya_eis_enabled=True,
        ru_chechnya_eis_rss_urls=cfg.ru_chechnya_eis_rss_urls,
        eis_direct_enabled=cfg.eis_direct_enabled,
        eis_system_trust_enabled=cfg.eis_system_trust_enabled,
        ru_background_catalog_enabled=True,
    )


def accept():
    cfg = isolated_settings()
    catalog = build_source_catalog(cfg)
    if enabled_ru_catalog_keys(catalog) != (SOURCE_KEY,):
        raise AssertionError("Isolated regional proof selected unexpected RU sources")
    with tempfile.TemporaryDirectory(prefix="valyqon-chechnya-eis-live-") as tmp:
        root = Path(tmp)
        db = Database(DatabaseSettings("ru-chechnya-live", root / "worker.sqlite"))
        try:
            jobs = JobRepository(db, JobSettings(lease_seconds=240, heartbeat_seconds=10))
            jobs.initialize()
            store = OpportunityRepository(db)
            store.initialize()
            queued = ConnectorSyncService(jobs, catalog).enqueue(SOURCE_KEY)
            handlers = HandlerRegistry()
            handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, store, max_records=5))
            if not Worker(jobs, handlers, job_types=(JOB_TYPE,)).run_once():
                raise AssertionError("No regional Worker job was claimed")
            completed = jobs.get(queued.id, scope=JobScope())
            if completed is None or completed.state != "succeeded":
                # Print only stable Job status codes; never dump the RSS URL,
                # response body, certificate contents or personal searches.
                print("RU_CHECHNYA_EIS_WORKER_STATE=" +
                      (completed.state if completed is not None else "missing"))
                print("RU_CHECHNYA_EIS_WORKER_FAILURE_CODE=" +
                      (completed.failure_code or "none" if completed is not None else "none"))
                raise AssertionError("Chechnya Worker did not succeed")
            stats = completed.result
            rows = store.read(SOURCE_KEY, limit=5)
            if not rows or not all(is_chechnya_notice(n) for n in rows):
                raise AssertionError("No original regional EIS tender persisted")
            if any(not n.tender_number or "zakupki.gov.ru" not in n.url for n in rows):
                raise AssertionError("Missing genuine official notice number/URL")
            if stats["inserted_count"] != len(rows) or stats["skipped_count"]:
                raise AssertionError("Not all genuine EIS items passed durable Worker validation")

            # Per-user query: real published title, real stored native number,
            # plus a negative query to catch unwanted all-Russia leakage.
            first = rows[0]
            terms = re.findall(r"[А-Яа-яЁёA-Za-z]{6,}", first.title)
            if not terms:
                raise AssertionError("No usable published title keyword")
            term = terms[0]
            snapshot = snapshot_catalog(catalog, store)
            for query in (first.tender_number, term):
                report = asyncio.run(snapshot.fetch(
                    source_keys=(SOURCE_KEY,), search_terms=(query,), limit_per_source=5,
                ))
                if report.failures or not any(n.identity == first.identity for n in report.notices):
                    raise AssertionError("Genuine EIS title or ID query failed")
            negative = asyncio.run(snapshot.fetch(
                source_keys=(SOURCE_KEY,),
                search_terms=("valyqon_chechnya_absent_987654321",), limit_per_source=5,
            ))
            if negative.failures or negative.notices:
                raise AssertionError("Negative regional query leaked unrelated tenders")

            profile = CompanyProfile(
                profile_version="v1", company_name="Synthetic Chechnya requester",
                product_keywords=[term], search_keywords=[term],
                accepted_currencies=["RUB"],
            )
            if prefilter_notice(first, profile) is None:
                raise AssertionError("User profile failed matching real tender")
            if store.upsert(first, connector_version(SOURCE_KEY)):
                raise AssertionError("Same tender inserted twice")

            async def local_notification():
                repo = MonitoringRepository(root / "alerts.sqlite")
                repo.initialize()
                repo.set_subscription(99101, 99102, True)
                service = TenderMonitorService(cfg, None, repo, profile)
                stop = asyncio.Event()
                bot = LocalCaptureBot(stop)
                await asyncio.wait_for(
                    # The real original was already obtained and fenced-written
                    # by the Worker. User notifications must read that exact
                    # persisted SQL snapshot rather than making an unrelated
                    # second upstream RSS request, which could fail or change.
                    monitor_loop(bot, service, stop, source_catalog=snapshot),
                    timeout=75,
                )
                if not bot.messages or not any(
                    ("Номер: " + str(n.tender_number)) in text
                    for text in bot.messages for n in rows
                ):
                    raise AssertionError("No original Chechnya notice reached local Telegram boundary")
                # Check delivery dedup through the actual persisted monitoring
                # repository, not only the Worker opportunity upsert. Every
                # captured real EIS number must be marked seen for this user.
                delivered = {
                    n.tender_number for n in rows
                    if any(("Номер: " + str(n.tender_number)) in text
                           for text in bot.messages)
                }
                if not delivered:
                    raise AssertionError("No original regional notice was captured")
                replay, replay_report = await service.fetch_matches_from_catalog(
                    snapshot, 99101, source_keys=(SOURCE_KEY,),
                )
                if replay_report.failures or not replay_report.attempted_sources:
                    raise AssertionError("Replay failed to read stored regional notices")
                replay_numbers = {match.notice.tender_number for match in replay}
                if not delivered.issubset(replay_numbers):
                    raise AssertionError("Captured notice not discoverable on replay")
                unclaimed = await service.unseen_matches(99101, replay)
                if delivered.intersection(
                    match.notice.tender_number for match in unclaimed
                ):
                    raise AssertionError("Local alert delivery dedup failed on replay")
                return len(bot.messages)

            local_alerts = asyncio.run(local_notification())
            return {
                "official_live_eis_region_notices": len(rows),
                "fenced_worker_inserted": stats["inserted_count"],
                "sqlite_original_number_query": True,
                "sqlite_real_title_keyword_query": True,
                "unmatched_keyword_returns_none": True,
                "dedup_on_replay": True,
                "local_alert_captured": local_alerts,
                "local_alert_replay_dedup_verified": True,
                "real_telegram_api_delivery_verified": False,
                "production_enabled": False,
            }
        finally:
            db.close()


def main():
    try:
        result = accept()
    except Exception as error:
        print("RU_CHECHNYA_EIS_STRICT_LIVE=BLOCKED_" + type(error).__name__)
        print("REAL_TELEGRAM_DELIVERY=NOT_VERIFIED")
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_CHECHNYA_EIS_REAL_EVIDENCE=" +
          json.dumps(result, ensure_ascii=False, sort_keys=True))
    print("RU_CHECHNYA_EIS_STRICT_LIVE=PASS_LOCAL_CAPTURE")
    print("REAL_TELEGRAM_DELIVERY=NOT_VERIFIED")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
