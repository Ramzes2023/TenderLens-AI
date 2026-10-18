"""Offline Russian pre-launch notification coverage; no Telegram calls or external feed I/O."""
import asyncio
from types import SimpleNamespace

import pytest

from app.bot.monitoring import (
    enabled_ru_catalog_keys, monitor_loop, monitor_on_handler,
)
from app.monitoring.config import MonitoringSettings, load_monitoring_settings


def configured(*, ru=True, enabled=True):
    return MonitoringSettings(
        enabled=enabled, interval_seconds=60, max_items=5,
        max_notifications_per_cycle=3, request_timeout=15,
        eis_rss_urls=(), ca_bundle_file=None,
        profile_feeds_enabled=False, ru_background_catalog_enabled=ru,
    )


class Registry:
    def metadata(self):
        return (
            SimpleNamespace(key="kavkaz_rf_firstparty", enabled=True, jurisdictions=("RU",)),
            SimpleNamespace(key="stan_commercial_public", enabled=True, jurisdictions=("RU",)),
            SimpleNamespace(key="draft_dagestan", enabled=False, jurisdictions=("RU",)),
            SimpleNamespace(key="ted", enabled=True, jurisdictions=("EU",)),
        )


class Catalog:
    registry = Registry()


class DummyBot:
    def __init__(self, event):
        self.event = event
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text, kw))
        self.event.set()


class DummyService:
    def __init__(self, event, *, fail=False, ru=True):
        self.settings = configured(ru=ru)
        self.event = event
        self.fail = fail
        self.fetched = []
        self.claimed = []
        self.legacy = 0

    async def active_subscriptions(self):
        return [SimpleNamespace(owner_user_id=101, chat_id=201)]

    async def fetch_matches_from_catalog(self, catalog, owner_user_id, *, source_keys):
        self.fetched.append((catalog, owner_user_id, source_keys))
        self.event.set()
        match = SimpleNamespace(notice=SimpleNamespace(
            source="kavkaz_rf_firstparty", title="Договор на обслуживание канатных дорог",
            tender_number="АЭФ-ДВА-397", customer="АО «КАВКАЗ.РФ»",
            initial_price=700000.0, currency="RUB", deadline=None,
            region="Северный Кавказ", url="https://xn--80aafvlc.xn--p1ai/"),
            reasons=("обслуживание",))
        report = SimpleNamespace(
            attempted_sources=("kavkaz_rf_firstparty", "stan_commercial_public"),
            total_failure=self.fail,
        )
        return [match], report

    async def fetch_matches(self, owner_user_id):
        self.legacy += 1
        self.event.set()
        return []

    async def claim_new(self, owner_user_id, matches):
        self.claimed.extend(matches)
        return matches


def test_only_explicitly_enabled_ru_registry_items_enter_background_scan():
    assert enabled_ru_catalog_keys(Catalog()) == (
        "kavkaz_rf_firstparty", "stan_commercial_public",
    )
    assert enabled_ru_catalog_keys(None) == ()


def test_ru_catalog_loop_sends_actual_profile_filtered_matches_not_non_ru():
    async def scenario():
        stop = asyncio.Event()
        bot = DummyBot(stop)
        service = DummyService(stop)
        await monitor_loop(bot, service, stop, source_catalog=Catalog())
        assert len(bot.sent) == 1
        assert "НОВАЯ ЗАКУПКА" in bot.sent[0][1]
        assert service.fetched[0][2] == (
            "kavkaz_rf_firstparty", "stan_commercial_public",
        )
        assert len(service.claimed) == 1
        assert service.legacy == 0
    asyncio.run(scenario())


def test_ru_catalog_total_outage_never_marks_notices_seen_or_sends():
    async def scenario():
        stop = asyncio.Event()
        bot = DummyBot(stop)
        service = DummyService(stop, fail=True)
        await monitor_loop(bot, service, stop, source_catalog=Catalog())
        assert service.fetched and service.claimed == []
        assert bot.sent == []
    asyncio.run(scenario())


def test_legacy_eis_background_stays_unchanged_without_opt_in():
    async def scenario():
        stop = asyncio.Event()
        bot = DummyBot(stop)
        service = DummyService(stop, ru=False)
        await monitor_loop(bot, service, stop, source_catalog=Catalog())
        assert service.legacy == 1
        assert not service.fetched and not service.claimed
    asyncio.run(scenario())


def test_invalid_ru_background_without_enabled_source_fails_closed():
    async def scenario():
        stop = asyncio.Event()
        service = DummyService(stop)
        with pytest.raises(ValueError, match="No approved Russian"):
            await monitor_loop(DummyBot(stop), service, stop, source_catalog=None)
    asyncio.run(scenario())


def test_on_handler_baselines_same_source_set_before_subscribing():
    class Message:
        from_user = SimpleNamespace(id=101)
        chat = SimpleNamespace(id=201)
        def __init__(self):
            self.answers = []
        async def answer(self, msg):
            self.answers.append(msg)
            return SimpleNamespace(edit_text=self.answer)

    class Service:
        settings = configured()
        def __init__(self):
            self.events = []
        async def baseline_from_catalog(self, catalog, owner, *, source_keys):
            self.events.append(("baseline", owner, source_keys))
            return 2, SimpleNamespace()
        async def subscribe(self, owner, chat):
            self.events.append(("subscribe", owner, chat))

    async def scenario():
        service, msg = Service(), Message()
        await monitor_on_handler(msg, service, Catalog())
        assert service.events == [
            ("baseline", 101, ("kavkaz_rf_firstparty", "stan_commercial_public")),
            ("subscribe", 101, 201),
        ]
        assert any("baseline: 2" in msg for msg in msg.answers)
    asyncio.run(scenario())


def test_ru_background_env_is_strict_and_defaults_off(monkeypatch, tmp_path):
    env = tmp_path / "nonexistent.env"
    monkeypatch.delenv("VALYQON_RU_BACKGROUND_CATALOG_ENABLED", raising=False)
    assert not load_monitoring_settings(env).ru_background_catalog_enabled
    monkeypatch.setenv("VALYQON_RU_BACKGROUND_CATALOG_ENABLED", "true")
    assert load_monitoring_settings(env).ru_background_catalog_enabled
    monkeypatch.setenv("VALYQON_RU_BACKGROUND_CATALOG_ENABLED", "invalid")
    with pytest.raises(ValueError):
        load_monitoring_settings(env)
