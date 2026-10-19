"""LIVE Ingushetia EIS acceptance; never substitute fixtures or cached cards.

Requires 2 true EIS 44-FZ notices with region corroborated by publisher,
reachable original cards, leased Worker, durable disposable SQLite,
query by number/title, and replay idempotence. Does not send Telegram
to real users and must not be represented as production delivery proof.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import HandlerRegistry, JobRepository, JobSettings
from app.jobs.models import JobScope
from app.jobs.worker import Worker
from app.monitoring.config import MonitoringSettings
from app.monitoring.repository import MonitoringRepository
from app.monitoring.service import TenderMonitorService, prefilter_notice
from app.scoring.models import CompanyProfile
from app.bot.monitoring import monitor_loop
from app.sources.catalog import build_source_catalog
from app.sources.http import source_client
from app.sources.ingestion import JOB_TYPE, ConnectorSyncHandler, ConnectorSyncService, connector_version
from app.sources.http import FetchPolicy, bounded_fetch
from scripts.ru_eis_pinned_tls_probe import verify_root
from app.sources.opportunities import OpportunityRepository
from app.sources.ru_ingushetia_eis44 import SOURCE_ID, RSS_URL, normalize_ingushetia_notice
from app.sources.snapshots import snapshot_catalog


ROOT = Path(__file__).resolve().parents[1] / 'russian_trusted_root_ca_pem.crt'


def _catalog_settings():
    # The bundled Ministry certificate is accepted only when its canonical DER
    # matches the independently documented official root fingerprint.
    verify_root(ROOT.read_bytes())
    cfg = MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=2,
        max_notifications_per_cycle=2, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=ROOT,
        profile_feeds_enabled=False,
        ru_ingushetia_eis44_enabled=True,
        ru_background_catalog_enabled=True,
        ru_ingushetia_eis44_rss_url=os.environ.get('RU_INGUSHETIA_EIS44_RSS_URL', '').strip() or None,
    )
    return cfg


def _catalog():
    return build_source_catalog(_catalog_settings())


async def _check_original_links(notices):
    observed = {}
    async def record(response):
        observed['status'] = response.status_code
    with bounded_fetch(FetchPolicy(frozenset({'zakupki.gov.ru'}), len(notices), max_bytes=1_800_000)):
      async with source_client(
        timeout=20, follow_redirects=False, trust_env=False, verify=str(ROOT),
        headers={"Accept": "text/html"},
        event_hooks={"response": [record]},
      ) as client:
          for notice in notices:
              observed.clear()
              try:
                  original = await client.get(notice.url)
              except Exception:
                  if observed.get('status') is not None:
                      raise AssertionError('Official EIS original card HTTP ' + str(observed['status'])) from None
                  raise
              original.raise_for_status()
              if "html" not in original.headers.get("content-type", "").lower():
                  raise AssertionError("Official EIS original card is not HTML")
              body = original.text
              from app.sources.ru_ingushetia_fabrikant44 import _Visible, _text
              visible = _Visible()
              visible.feed(body)
              text = _text(visible.content).casefold()
              if any(value.casefold() not in text for value in
                     (notice.tender_number, notice.title, notice.customer or "")):
                  raise AssertionError("Official EIS card does not corroborate number, title and customer")


async def _check_isolated_dispatch(catalog, cfg, notices, db_path, *, source_id=SOURCE_ID,
                                   persisted_catalog=None):
    """Real stored notices -> real monitor dedup -> Telegram-format fake sink.

    Intentionally uses no bot credentials, chat API, network send, or user data.
    This is a staging pipeline proof, NOT a Telegram delivery receipt.
    """
    monitor_repo = MonitoringRepository(db_path)
    monitor_repo.initialize()
    fake_owner, fake_chat = 101, 202
    monitor_repo.set_subscription(fake_owner, fake_chat, True)

    class PersistedNoticeMonitor(TenderMonitorService):
        async def fetch_matches_from_catalog(self, selected_catalog, owner_user_id=None,
                                             *, source_keys=None):
            assert selected_catalog is catalog
            assert source_id in source_keys
            matches = [prefilter_notice(n, None) for n in notices]
            return [m for m in matches if m is not None], SimpleNamespace(
                attempted_sources=(source_id,), total_failure=False,
            )

    # Live acceptance reads the actual Worker database through SnapshotSource.
    # The supplied-notice subclass is used only by the offline helper contract.
    service = (TenderMonitorService(cfg, None, monitor_repo, None)
               if persisted_catalog is not None else
               PersistedNoticeMonitor(cfg, None, monitor_repo, None))
    stop = asyncio.Event()

    class IsolatedAckSink:
        def __init__(self):
            self.messages = []

        async def send_message(self, chat_id, text, **kwargs):
            assert chat_id == fake_chat and kwargs.get("disable_web_page_preview") is True
            self.messages.append(text)
            stop.set()
            return SimpleNamespace(message_id=len(self.messages))

    sink = IsolatedAckSink()
    await monitor_loop(sink, service, stop, source_catalog=persisted_catalog or catalog)
    expected = min(len(notices), cfg.max_notifications_per_cycle)
    if len(sink.messages) != expected:
        raise AssertionError("Staging monitor did not dispatch every allowed first batch notice")
    delivered = []
    for text in sink.messages:
        matching = [row for row in notices if row.tender_number in text]
        if len(matching) != 1 or matching[0].title not in text or "НОВАЯ ЗАКУПКА" not in text:
            raise AssertionError("Staging dispatch lost original procurement identity")
        row = matching[0]
        delivered.append(row)
        if not monitor_repo.seen(fake_owner, "eis_44", row.tender_number):
            raise AssertionError("Simulated Telegram acknowledgement was not persisted")
    if len({row.tender_number for row in delivered}) != expected:
        raise AssertionError("Staging monitor dispatched a duplicate original")
    if await service.unseen_matches(fake_owner, [
        prefilter_notice(row, None) for row in delivered
    ]):
        raise AssertionError("Simulated delivered Ingushetia original would alert again")
    if await service.unseen_matches(fake_owner, [
        prefilter_notice(replace(row, source="eis", external_id="generic-" + row.tender_number), None)
        for row in delivered
    ]):
        raise AssertionError("The same original from generic EIS would alert again")
    # A per-cycle cap cannot mark unnotified later rows as delivered.
    remaining = await service.unseen_matches(fake_owner, [
        prefilter_notice(row, None) for row in notices if row not in delivered
    ])
    if len(remaining) != len(notices) - expected:
        raise AssertionError("Undelivered notices must remain eligible for the next cycle")
    return len(sink.messages)


async def _check_user_queries_and_profiles(catalog, cfg, notices, db_path, *, source_id):
    """Exercise actual SQL catalog queries and production profile filtering."""
    repo = MonitoringRepository(db_path)
    repo.initialize()
    service = TenderMonitorService(cfg, None, repo, None)
    evidence = []
    for notice in notices:
        words = re.findall(r"[^\W_]+", notice.title, flags=re.UNICODE)
        term = next((word for word in words[1:] if len(word) >= 4), words[0])
        profile = CompanyProfile(profile_version="live-acceptance-v1",
                                 company_name="Isolated Ingushetia acceptance",
                                 search_keywords=[term], allowed_regions=[notice.region])
        matches, report = await service.fetch_matches_from_catalog_for_profile(
            catalog, profile, source_keys=(source_id,))
        if report.failures or not any(m.notice.identity == notice.identity for m in matches):
            raise AssertionError("Live SQL notice not found for user keyword and matching profile")
        for rejecting in (profile.model_copy(update={"excluded_keywords": [term]}),
                          profile.model_copy(update={"allowed_regions": ["Чужой регион"]})):
            rejected, report = await service.fetch_matches_from_catalog_for_profile(
                catalog, rejecting, source_keys=(source_id,))
            if report.failures or any(m.notice.identity == notice.identity for m in rejected):
                raise AssertionError("Excluded keyword or wrong-region profile accepted the notice")
        evidence.append({"number": notice.tender_number, "user_query": term,
                         "profile_match": True, "excluded_keyword_rejected": True,
                         "other_region_rejected": True})
    return evidence


def proof():
    catalog = _catalog()
    assert SOURCE_ID in catalog.enabled_keys
    # LIVE network to real official RSS first, never fixtures.
    source = catalog.registry.get(SOURCE_ID).source
    first = asyncio.run(source.fetch(limit=2))
    if len(first) < 2:
        raise AssertionError(
            f"Only {len(first)} independently region-confirmed real EIS notices; minimum 2"
        )
    assert all(normalize_ingushetia_notice(item) is not None for item in first)
    asyncio.run(_check_original_links(first[:2]))
    with tempfile.TemporaryDirectory(prefix="valyqon-ru-ingushetia-") as tmp:
        db = Database(DatabaseSettings("ru-ingushetia-live", Path(tmp) / "proof.sqlite"))
        try:
            jobs = JobRepository(db, JobSettings(lease_seconds=240, heartbeat_seconds=10))
            jobs.initialize()
            store = OpportunityRepository(db)
            store.initialize()
            job = ConnectorSyncService(jobs, catalog).enqueue(SOURCE_ID)
            handlers = HandlerRegistry()
            handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, store, max_records=2))
            assert Worker(jobs, handlers, job_types=(JOB_TYPE,)).run_once()
            completed = jobs.get(job.id, scope=JobScope())
            if completed is None or completed.state != "succeeded":
                raise AssertionError("Real fenced worker did not succeed")
            rows = store.read(SOURCE_ID, limit=2)
            if len(rows) < 2:
                raise AssertionError("Insufficient real Ingushetia notices persisted")
            # Never accept two verified upstream details AND unrelated SQL rows
            # as a complete ingestion chain; the same originals must survive.
            original_verified_ids = {n.tender_number for n in first[:2]}
            persisted_ids = {n.tender_number for n in rows}
            if not original_verified_ids <= persisted_ids:
                raise AssertionError("Original EIS detail IDs did not survive real leased Worker SQL")
            snap = snapshot_catalog(catalog, store)
            for n in rows:
                assert normalize_ingushetia_notice(n) is not None
                report = asyncio.run(snap.fetch(
                    source_keys=(SOURCE_ID,), search_terms=(n.tender_number,),
                    limit_per_source=10,
                ))
                if report.failures or not any(
                    m.external_id == n.external_id and m.url == n.url for m in report.notices
                ):
                    raise AssertionError("Real Ingushetia EIS notice not searchable by number")
                title_report = asyncio.run(snap.fetch(
                    source_keys=(SOURCE_ID,), search_terms=(n.title,),
                    limit_per_source=10,
                ))
                if title_report.failures or not any(
                    m.identity == n.identity for m in title_report.notices
                ):
                    raise AssertionError('Real Ingushetia notice not searchable by title')
                if store.upsert(n, connector_version(SOURCE_ID)):
                    raise AssertionError("Replay inserted duplicate regional notice")
            profiles = asyncio.run(_check_user_queries_and_profiles(
                snap, _catalog_settings(), rows, Path(tmp) / "profiles.sqlite", source_id=SOURCE_ID))
            staged = asyncio.run(_check_isolated_dispatch(
                catalog, _catalog_settings(), rows, Path(tmp) / "notifications.sqlite",
                persisted_catalog=snap))
            return {
                "official_rss_origin": "zakupki.gov.ru",
                "isolated_staging_sink_dispatches": staged,
                "original_cards_corresponding_to_list": 2,
                "leased_worker_state": completed.state,
                "stored_and_searchable": len(rows),
                "notice_ids": sorted(persisted_ids),
                "notices": [{"number": n.tender_number, "title": n.title,
                             "customer": n.customer, "url": n.url} for n in rows],
                "user_queries_and_profiles": profiles,
                "replay_duplicates": 0,
                "production_changed": False,
                "real_user_notifications_sent": False,
            }
        finally:
            db.close()


def main():
    """Accept ONLY genuinely live full-chain originals from EIS or accredited ETP.

    This is not a fake fallback to archived notice IDs. Both choices must
    acquire *current real upstream list rows* on this run, independently GET
    originals, and pass real leased Worker, SQL, tenant search and alert sink.
    """
    from scripts.ci_ru_ingushetia_fabrikant_worker import proof as vendor_proof

    failures = []
    for upstream, acceptance in (("official_eis_rss", proof),
                                 ("accredited_44fz_etp_mirror", vendor_proof)):
        try:
            result = acceptance()
        except Exception as exc:
            failure = type(exc).__name__
            cause_names = []
            cause = getattr(exc, "__cause__", None)
            while cause is not None and len(cause_names) < 3:
                cause_names.append(type(cause).__name__)
                cause = getattr(cause, "__cause__", None)
            failures.append({
                "route": upstream,
                "failure_class": failure,
                "cause_types": cause_names,
                "retryable": bool(getattr(exc, "retryable", False)),
                "contract": str(exc)[:200] if type(exc) is AssertionError else None,
            })
            continue
        print("RU_INGUSHETIA_LIVE_UPSTREAM=" + upstream)
        print("EARLIER_ROUTE_FAILURES=" + json.dumps(failures, sort_keys=True))
        print("RU_INGUSHETIA_PROOF=" + json.dumps(result, ensure_ascii=False, sort_keys=True))
        print("RU_INGUSHETIA_LIVE_ACCEPTANCE=PASS")
        print("REAL_USER_TELEGRAM_RECEIPT=NOT_TESTED")
        print("PRODUCTION_CHANGED=NO")
        return 0

    print("RU_INGUSHETIA_LIVE_ACCEPTANCE=BLOCKED")
    print("FAILURE_ROUTE_SUMMARY=" + json.dumps(failures, sort_keys=True))
    print("REAL_USER_TELEGRAM_RECEIPT=NOT_TESTED")
    print("PRODUCTION_CHANGED=NO")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
