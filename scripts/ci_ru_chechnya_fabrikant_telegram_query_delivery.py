"""Real Chechnya Fabrikant public list -> per-user keyword -> Telegram rendering + dedup.

READ-ONLY CI. Bounded first-party list and independently verified public detail GETs are real upstream evidence.
Telegram transport is a local in-memory fake: this NEVER sends to subscribers
or external chat accounts, nor proves live Telegram credentials/delivery.
"""
from __future__ import annotations

import asyncio
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace

from app.bot.monitoring import format_match, monitor_loop, enabled_ru_catalog_keys
from app.monitoring.config import MonitoringSettings
from app.monitoring.repository import MonitoringRepository
from app.monitoring.service import MonitorMatch, TenderMonitorService, prefilter_notice
from app.scoring.models import CompanyProfile
from app.sources.catalog import build_source_catalog

SOURCE = "ru_chechnya_fabrikant44"


class LocalCaptureBot:
    def __init__(self, stop: asyncio.Event, *, fail_delivery=False):
        self.stop = stop
        self.delivered = []
        self.fail_delivery = fail_delivery
        self.attempted = []

    async def send_message(self, chat_id, text, **kwargs):
        if chat_id != 99001 or kwargs.get("disable_web_page_preview") is not True:
            raise AssertionError("Unexpected recipient or outbound formatting")
        if not text.startswith("🆕 НОВАЯ ЗАКУПКА") or "Источник: " + SOURCE not in text:
            raise AssertionError("Message does not identify genuine Chechnya Fabrikant source")
        # Official Chechnya Fabrikant cards carry native original numbers only; never invent a price.
        # A deadline is displayed only when independently verified, not guessed.
        self.attempted.append(text)
        self.stop.set()
        if self.fail_delivery:
            raise ConnectionError("Deliberate local transport failure; no Telegram I/O")
        self.delivered.append(text)
        # A local-only, shape-compatible synthetic Bot API receipt.
        # The production monitor checks recipient and positive message ID
        # before marking an actual procured ID delivered. This is NOT
        # confirmation from Telegram servers or a user.
        return SimpleNamespace(
            message_id=len(self.delivered),
            chat=SimpleNamespace(id=chat_id),
        )


def settings():
    return MonitoringSettings(
        enabled=True, interval_seconds=60, max_items=2,
        max_notifications_per_cycle=2, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=None,
        profile_feeds_enabled=False,
        ru_chechnya_fabrikant44_enabled=True,
        ru_background_catalog_enabled=True,
    )


async def acceptance():
    cfg = settings()
    catalog = build_source_catalog(cfg)
    if enabled_ru_catalog_keys(catalog) != (SOURCE,):
        raise AssertionError("Unexpected enabled Russian source selection")
    # Proof uses LIVE original first-party rows; no synthetic notice generation.
    source = catalog.registry.get(SOURCE).source
    rows = await source.fetch(limit=2)
    if len(rows) != 2 or len({n.external_id for n in rows}) != 2:
        raise AssertionError("No two independently numbered public Chechnya Fabrikant items")

    words = re.findall(r"[А-Яа-яЁёA-Za-z]{6,}", rows[0].title)
    if not words:
        raise AssertionError("No real long search term in public title")
    term = words[0]
    profile = CompanyProfile(
        profile_version="v1", company_name="Test-only Chechnya Fabrikant requester",
        product_keywords=[term], search_keywords=[term],
        accepted_currencies=[],
    )
    if prefilter_notice(rows[0], profile) is None:
        raise AssertionError("Real title does not match its own keyword")
    negative = profile.model_copy(update={
        "search_keywords": ["valyqon_synthetic_unmatched_term_987654321"]
    })
    if any(prefilter_notice(n, negative) is not None for n in rows):
        raise AssertionError("Nonmatching requester leaked a real tender")

    with tempfile.TemporaryDirectory(prefix="valyqon-chechnya-telegram-") as dir:
        repo = MonitoringRepository(Path(dir) / "notifications.sqlite")
        repo.initialize()
        repo.set_subscription(99000, 99001, True)
        service = TenderMonitorService(cfg, None, repo, profile)
        # Exercise the real delivery loop's error path. A failed local send
        # must not claim a genuine notice as seen before a retry succeeds.
        failed_stop = asyncio.Event()
        failed_bot = LocalCaptureBot(failed_stop, fail_delivery=True)
        await asyncio.wait_for(
            monitor_loop(failed_bot, service, failed_stop, source_catalog=catalog),
            timeout=55,
        )
        if not failed_bot.attempted or failed_bot.delivered:
            raise AssertionError("Local failed-send boundary was not exercised")
        failed_matches = [MonitorMatch(n, (term,)) for n in rows
                          if ("Номер: " + n.tender_number) in failed_bot.attempted[0]]
        if not failed_matches or await service.unseen_matches(99000, failed_matches) != failed_matches:
            raise AssertionError("Failed local delivery suppressed a real retry")
        stop = asyncio.Event()
        bot = LocalCaptureBot(stop)
        # Actual API source is queried again through production
        # monitor_loop; fake send_message is the only substituted boundary.
        await asyncio.wait_for(
            monitor_loop(bot, service, stop, source_catalog=catalog),
            timeout=55,
        )
        if not bot.delivered:
            raise AssertionError("Real Chechnya Fabrikant query emitted no local message")
        if not any(("Номер: " + m.notice.tender_number) in message
                   for m in failed_matches for message in bot.delivered):
            raise AssertionError("Failed genuine notice was not retried successfully")
        # Native IDs in the message must originate from the genuine public
        # fetch, not invented fixtures or source-count metadata.
        if not any(
            ("Номер: " + n.tender_number) in message
            for message in bot.delivered for n in rows
        ):
            raise AssertionError("No real Chechnya Fabrikant native ID in delivery")
        matched = [MonitorMatch(n, (term,)) for n in rows
                   if ("Номер: " + n.tender_number) in "\n".join(bot.delivered)]
        if await service.unseen_matches(99000, matched):
            raise AssertionError("Successfully simulated delivery is not deduplicated")
        if not await service.unseen_matches(99002, matched):
            raise AssertionError("Another customer's unseen records were suppressed")

        return {
            "real_independently_verified_detail_rows": len(rows),
            "eis_independent_feed": False,
            "query_matched_local_messages": len(bot.delivered),
            "dedup_after_confirmed_local_send": True,
            "cross_customer_isolation": True,
            "negative_query_returns_no_matches": True,
            "failed_delivery_remains_retryable": True,
            "retry_confirmed_by_local_capture": True,
            "actual_telegram_message_delivered": False,
            "production_changed": False,
        }


def main():
    import json
    try:
        result = asyncio.run(acceptance())
    except Exception as error:
        print("RU_CHECHNYA_FABRIKANT_LOCAL_TELEGRAM_QUERY=BLOCKED_" + type(error).__name__)
        print("ACTUAL_TELEGRAM_MESSAGE_DELIVERED=NO")
        print("PRODUCTION_CHANGED=NO")
        return 2
    print("RU_CHECHNYA_FABRIKANT_LOCAL_TELEGRAM_EVIDENCE=" + json.dumps(
        result, ensure_ascii=False, sort_keys=True))
    print("RU_CHECHNYA_FABRIKANT_LOCAL_TELEGRAM_QUERY=PASS_LOCAL_CAPTURE_ONLY")
    print("ACTUAL_TELEGRAM_MESSAGE_DELIVERED=NO")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
