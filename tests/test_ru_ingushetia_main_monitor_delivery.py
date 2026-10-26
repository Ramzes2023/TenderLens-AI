"""Offline release regression: real local SQL and monitor; synthetic Bot API sink only.

This is NOT proof of live source availability or actual Telegram delivery.
Production subscriptions, customer chats and external networks are never used.
"""
import asyncio
from dataclasses import replace
from types import SimpleNamespace

from app.bot.monitoring import monitor_loop
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.monitoring.config import MonitoringSettings
from app.monitoring.repository import MonitoringRepository
from app.monitoring.service import TenderMonitorService
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import connector_version
from app.sources.models import TenderNotice
from app.sources.opportunities import OpportunityRepository
from app.sources.ru_notice_identity import original_notice_key
from app.sources.snapshots import snapshot_catalog


ORIGINAL = "0114500000826002402"
OWNER = 80421
CHAT = 91423


def test_real_sql_monitor_deduplicates_ingushetia_mirrors_and_requires_chat_ack(tmp_path):
    """Bot can mark only the confirmed original; invalid receipt stays retryable."""
    cfg = MonitoringSettings(
        enabled=True, interval_seconds=600, max_items=10,
        max_notifications_per_cycle=5, request_timeout=12,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        ru_ingushetia_eis44_enabled=True,
        ru_ingushetia_fabrikant44_enabled=True,
        ru_background_catalog_enabled=True,
    )
    catalog = build_source_catalog(cfg)
    assert {"ru_ingushetia_eis44", "ru_ingushetia_fabrikant44"} <= set(catalog.enabled_keys)

    db = Database(DatabaseSettings("ingushetia-offline-delivery-contract", tmp_path / "source.sqlite"))
    try:
        store = OpportunityRepository(db)
        store.initialize()
        notices = [
            TenderNotice(
                source="ru_ingushetia_eis44", external_id=ORIGINAL,
                tender_number=ORIGINAL, title="Устройство ливневой канализации",
                url=("https://zakupki.gov.ru/epz/order/notice/ok20/view/"
                     "common-info.html?regNumber=" + ORIGINAL),
                customer="Комитет государственного заказа Республики Ингушетия",
                region="Республика Ингушетия", published_at="2026-10-20",
            ),
            TenderNotice(
                source="ru_ingushetia_fabrikant44", external_id=ORIGINAL,
                tender_number=ORIGINAL, title="Устройство ливневой канализации",
                url="https://44.fabrikant.ru/44/procedure/okb20/" + ORIGINAL,
                customer="Комитет государственного заказа Республики Ингушетия",
                region="Республика Ингушетия", published_at="2026-10-20",
            ),
        ]
        assert original_notice_key(notices[0]) == original_notice_key(notices[1]) == (
            "eis_44", ORIGINAL,
        )
        for notice in notices:
            assert store.upsert(notice, connector_version(notice.source))
            assert len(store.read(notice.source, limit=10)) == 1

        source_snapshot = snapshot_catalog(catalog, store)
        subscriptions = MonitoringRepository(tmp_path / "monitor.sqlite")
        subscriptions.initialize()
        subscriptions.set_subscription(OWNER, CHAT, True)
        service = TenderMonitorService(cfg, None, subscriptions, None)
        keys = ("ru_ingushetia_eis44", "ru_ingushetia_fabrikant44")

        async def check_matches():
            matches, report = await service.fetch_matches_from_catalog(
                source_snapshot, OWNER, source_keys=keys,
            )
            assert not report.failures
            assert set(report.attempted_sources) == set(keys)
            assert matches and all(m.notice.tender_number == ORIGINAL for m in matches)
            assert len(await service.unseen_matches(OWNER, matches)) == 1

        asyncio.run(check_matches())

        class SyntheticBot:
            def __init__(self, stop, valid_receipt):
                self.stop, self.valid_receipt = stop, valid_receipt
                self.calls = []

            async def send_message(self, chat_id, text, **kwargs):
                self.calls.append((chat_id, text))
                self.stop.set()
                assert chat_id == CHAT
                assert ORIGINAL in text and "НОВАЯ ЗАКУПКА" in text
                assert kwargs.get("disable_web_page_preview") is True
                return SimpleNamespace(
                    message_id=19,
                    chat=SimpleNamespace(id=CHAT if self.valid_receipt else CHAT + 1),
                )

        async def one_cycle(valid_receipt):
            stop = asyncio.Event()
            bot = SyntheticBot(stop, valid_receipt)
            await asyncio.wait_for(
                monitor_loop(bot, service, stop, source_catalog=source_snapshot),
                timeout=12,
            )
            return bot.calls

        # Simulate a wrong-chat Bot API acknowledgment: never mark delivered.
        bad = asyncio.run(one_cycle(False))
        assert len(bad) == 1
        assert not subscriptions.seen(OWNER, "eis_44", ORIGINAL)

        # The same real stored regional original remains eligible and sends
        # just one message even though it exists on both official mirror routes.
        good = asyncio.run(one_cycle(True))
        assert len(good) == 1
        assert subscriptions.seen(OWNER, "eis_44", ORIGINAL)

        asyncio.run(check_no_repeated_alert(service, source_snapshot, keys))
    finally:
        db.close()


async def check_no_repeated_alert(service, snapshot, keys):
    matches, report = await service.fetch_matches_from_catalog(
        snapshot, OWNER, source_keys=keys,
    )
    assert not report.failures
    assert await service.unseen_matches(OWNER, matches) == []


def test_two_authorized_chats_have_independent_original_ack_and_retry(tmp_path):
    """Offline real SQL contract: invalid receipt for one user cannot affect another."""
    cfg = MonitoringSettings(
        enabled=True, interval_seconds=600, max_items=5,
        max_notifications_per_cycle=5, request_timeout=12,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        ru_ingushetia_fabrikant44_enabled=True,
        ru_background_catalog_enabled=True,
    )
    catalog = build_source_catalog(cfg)
    db = Database(DatabaseSettings("ingushetia-two-chat-test", tmp_path / "source.sqlite"))
    try:
        store = OpportunityRepository(db)
        store.initialize()
        original = TenderNotice(
            source="ru_ingushetia_fabrikant44", external_id=ORIGINAL,
            tender_number=ORIGINAL, title="Устройство ливневой канализации",
            url="https://44.fabrikant.ru/44/procedure/okb20/" + ORIGINAL,
            customer="Комитет государственного заказа Республики Ингушетия",
            region="Республика Ингушетия", published_at="2026-10-20",
        )
        assert store.upsert(original, connector_version(original.source))
        snapshot = snapshot_catalog(catalog, store)
        repository = MonitoringRepository(tmp_path / "subscriptions.sqlite")
        repository.initialize()
        first_owner, second_owner = 121001, 121002
        first_chat, second_chat = 122001, 122002
        repository.set_subscription(first_owner, first_chat, True)
        repository.set_subscription(second_owner, second_chat, True)
        service = TenderMonitorService(cfg, None, repository, None)

        class ControlledBot:
            def __init__(self, stop, *, wrong_chat):
                self.stop = stop
                self.wrong_chat = wrong_chat
                self.delivered_to = []

            async def send_message(self, chat_id, text, **kwargs):
                self.delivered_to.append(chat_id)
                self.stop.set()
                assert ORIGINAL in text and "НОВАЯ ЗАКУПКА" in text
                assert kwargs["disable_web_page_preview"] is True
                recipient = chat_id + 1 if self.wrong_chat == chat_id else chat_id
                return SimpleNamespace(
                    message_id=17, chat=SimpleNamespace(id=recipient), text=text,
                )

        async def cycle(wrong_chat):
            stop = asyncio.Event()
            bot = ControlledBot(stop, wrong_chat=wrong_chat)
            await asyncio.wait_for(
                monitor_loop(bot, service, stop, source_catalog=snapshot),
                timeout=12,
            )
            return bot.delivered_to

        sent = asyncio.run(cycle(first_chat))
        assert len(sent) == 2 and set(sent) == {first_chat, second_chat}
        assert not repository.seen(first_owner, "eis_44", ORIGINAL)
        assert repository.seen(second_owner, "eis_44", ORIGINAL)

        # The first tenant retries its unacknowledged message. The second,
        # already-acknowledged tenant receives no duplicate publication.
        retried = asyncio.run(cycle(None))
        assert retried == [first_chat]
        assert repository.seen(first_owner, "eis_44", ORIGINAL)
        assert repository.seen(second_owner, "eis_44", ORIGINAL)
        # No notification remains for either user.  A periodic monitor with
        # zero sends cannot set the synthetic bot's stop event and will
        # correctly wait its 600-second poll interval; calling cycle(None)
        # here merely times out the test, not a real delivery regression.
        # Verify the production SQL-backed unseen decision for both tenants.
        async def verify_no_cross_tenant_duplicate():
            for owner in (first_owner, second_owner):
                matches, report = await service.fetch_matches_from_catalog(
                    snapshot, owner,
                    source_keys=("ru_ingushetia_fabrikant44",),
                )
                assert not report.failures
                assert await service.unseen_matches(owner, matches) == []

        asyncio.run(verify_no_cross_tenant_duplicate())
    finally:
        db.close()
