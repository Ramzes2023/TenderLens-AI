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
        return SimpleNamespace(message_id=len(self.sent),
                               chat=SimpleNamespace(id=chat_id))


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

    async def unseen_matches(self, owner_user_id, matches):
        return [m for m in matches if m not in self.claimed]

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


def test_telegram_network_failure_retries_without_losing_procurement_notice():
    class FlakyBot(DummyBot):
        def __init__(self, event):
            super().__init__(event)
            self.try_count = 0
        async def send_message(self, chat_id, text, **kw):
            self.try_count += 1
            if self.try_count == 1:
                self.event.set()
                raise OSError("synthetic Telegram transport outage")
            return await super().send_message(chat_id, text, **kw)

    async def scenario():
        stop = asyncio.Event()
        bot, service = FlakyBot(stop), DummyService(stop)
        await monitor_loop(bot, service, stop, source_catalog=Catalog())
        assert service.claimed == [] and bot.sent == []
        stop.clear()
        await monitor_loop(bot, service, stop, source_catalog=Catalog())
        assert bot.try_count == 2
        assert len(bot.sent) == len(service.claimed) == 1
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


def test_partial_ingushetia_outage_keeps_valid_etp_alert_and_redacts_network_error(caplog):
    """Synthetic monitoring regression, not real Bot API or source acceptance."""
    from app.monitoring.service import MonitorMatch
    from app.sources.models import TenderNotice

    class IngushRegistry:
        def metadata(self):
            return (
                SimpleNamespace(key="ru_ingushetia_eis44", enabled=True, jurisdictions=("RU",)),
                SimpleNamespace(key="ru_ingushetia_fabrikant44", enabled=True, jurisdictions=("RU",)),
            )

    class IngushCatalog:
        registry = IngushRegistry()

    class PartiallyUnavailable(DummyService):
        async def fetch_matches_from_catalog(self, catalog, owner_user_id, *, source_keys):
            assert source_keys == ("ru_ingushetia_eis44", "ru_ingushetia_fabrikant44")
            self.fetched.append((catalog, owner_user_id, source_keys))
            self.event.set()
            notice = TenderNotice(
                source="ru_ingushetia_fabrikant44",
                external_id="0114500000826002402",
                tender_number="0114500000826002402",
                title="Устройство ливневой канализации",
                customer="КОМИТЕТ ГОСУДАРСТВЕННОГО ЗАКАЗА РЕСПУБЛИКИ ИНГУШЕТИЯ",
                url="https://44.fabrikant.ru/44/procedure/okb20/0114500000826002402",
                region="Республика Ингушетия",
            )
            # Unknown names and exception text in a failure must not be
            # forwarded into the operator logs or Telegram messages.
            report = SimpleNamespace(
                attempted_sources=source_keys, total_failure=False,
                successful_sources=("ru_ingushetia_fabrikant44",),
                failures=(
                    SimpleNamespace(source="ru_ingushetia_eis44", error="private-token-DO-NOT-LOG"),
                    SimpleNamespace(source="evil-external-input", error="secret-credentials"),
                ),
            )
            return [MonitorMatch(notice, ("ливневая канализация",))], report

    async def scenario():
        stop = asyncio.Event()
        bot, service = DummyBot(stop), PartiallyUnavailable(stop)
        await monitor_loop(bot, service, stop, source_catalog=IngushCatalog())
        assert len(bot.sent) == 1
        assert len(service.claimed) == 1
        assert "0114500000826002402" in bot.sent[0][1]
        assert "НОВАЯ ЗАКУПКА" in bot.sent[0][1]
        assert not any("token" in text for _, text, _ in bot.sent)

    asyncio.run(scenario())
    assert "Russian source partial outage: ru_ingushetia_eis44" in caplog.text
    assert "private-token-DO-NOT-LOG" not in caplog.text
    assert "secret-credentials" not in caplog.text
    assert "evil-external-input" not in caplog.text


def test_bot_api_success_receipt_requires_exact_chat_and_positive_message_number():
    from app.bot.monitoring import _require_telegram_delivery_ack

    _require_telegram_delivery_ack(
        SimpleNamespace(message_id=19, chat=SimpleNamespace(id=-1007000001)),
        -1007000001,
    )
    with pytest.raises(ValueError, match="acknowledgement invalid"):
        _require_telegram_delivery_ack(
            SimpleNamespace(message_id=19, chat=SimpleNamespace(id=-1007000001)),
            -1007000002,
        )


def test_ru_background_env_is_strict_and_defaults_off(monkeypatch, tmp_path):
    env = tmp_path / "nonexistent.env"
    monkeypatch.delenv("VALYQON_RU_BACKGROUND_CATALOG_ENABLED", raising=False)
    assert not load_monitoring_settings(env).ru_background_catalog_enabled
    monkeypatch.setenv("VALYQON_RU_BACKGROUND_CATALOG_ENABLED", "true")
    assert load_monitoring_settings(env).ru_background_catalog_enabled
    monkeypatch.setenv("VALYQON_RU_BACKGROUND_CATALOG_ENABLED", "invalid")
    with pytest.raises(ValueError):
        load_monitoring_settings(env)


@pytest.mark.parametrize("receipt", [
    None,
    SimpleNamespace(message_id=0, chat=SimpleNamespace(id=201)),
    SimpleNamespace(message_id=7, chat=SimpleNamespace(id=999)),
    SimpleNamespace(message_id=True, chat=SimpleNamespace(id=201)),
])
def test_invalid_automatic_bot_ack_never_claims_notice_and_retry_recovers(receipt):
    """Offline: an awaited send without valid Bot API ACK is NOT delivery."""
    class Unconfirmed(DummyBot):
        async def send_message(self, chat_id, text, **kwargs):
            self.sent.append((chat_id, text, kwargs))
            self.event.set()
            return receipt

    async def run():
        stop = asyncio.Event()
        service = DummyService(stop)
        first = Unconfirmed(stop)
        await monitor_loop(first, service, stop, source_catalog=Catalog())
        assert service.claimed == []
        stop.clear()
        second = DummyBot(stop)
        await monitor_loop(second, service, stop, source_catalog=Catalog())
        assert len(second.sent) == len(service.claimed) == 1

    asyncio.run(run())
