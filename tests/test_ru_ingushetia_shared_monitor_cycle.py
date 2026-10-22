"""Offline tests: fixed Ingushetia feed is polled once per monitoring cycle.

Synthetic source/Telegram only. No live delivery, no customer credentials.
"""
import asyncio
from types import SimpleNamespace

from app.bot.monitoring import monitor_loop
from app.monitoring.service import MonitorMatch
from app.sources.models import TenderNotice


IDS = ("0114500000826002402", "0114500000826002380")


def tender(number, title, source):
    return TenderNotice(
        source=source, external_id=number, tender_number=number,
        title=title, region="Республика Ингушетия",
        url="https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber=" + number,
        customer="Комитет государственного заказа Республики Ингушетия",
    )


def profile(keyword):
    return SimpleNamespace(
        monitoring_keywords=(keyword,), excluded_keywords=(),
        accepted_currencies=(), min_contract_value=None, max_contract_value=None,
        hard_stop_on_budget=False, allowed_regions=("Ингушетия",),
        hard_stop_on_region=True,
    )


class FakeCatalog:
    class Registry:
        def __init__(self, keys):
            self.keys = keys

        def metadata(self):
            return [SimpleNamespace(key=k, enabled=True, jurisdictions=("RU",))
                    for k in self.keys]

    def __init__(self, keys):
        self.registry = self.Registry(keys)


class FakeService:
    def __init__(self, stop, *, total_failure=False):
        self.stop = stop
        self.total_failure = total_failure
        self.settings = SimpleNamespace(
            ru_background_catalog_enabled=True, max_notifications_per_cycle=5,
            max_items=10, interval_seconds=600,
        )
        self.calls = []
        self.claimed = []
        self.notices = [
            tender(IDS[0], "Устройство ливневой канализации", "ru_ingushetia_fabrikant44"),
            tender(IDS[1], "Поставка лекарственных средств", "ru_ingushetia_eis44"),
        ]

    async def active_subscriptions(self):
        # Ensure one cycle only; the event does not interrupt this cycle.
        self.stop.set()
        return [SimpleNamespace(owner_user_id=1, chat_id=11),
                SimpleNamespace(owner_user_id=2, chat_id=22)]

    async def fetch_matches_from_catalog_for_profile(self, catalog, p, *, source_keys):
        assert p is None
        self.calls.append(("shared", tuple(source_keys)))
        if self.total_failure:
            matches = []
            success = ()
            failed = ("ru_ingushetia_eis44", "ru_ingushetia_fabrikant44")
        else:
            matches = [MonitorMatch(n, ("no prefilter",)) for n in self.notices]
            success = tuple(source_keys)
            failed = ()
        report = SimpleNamespace(
            attempted_sources=tuple(source_keys),
            successful_sources=success,
            total_failure=self.total_failure,
            failures=tuple(SimpleNamespace(source=k) for k in failed),
        )
        return matches, report

    async def fetch_matches_from_catalog(self, catalog, owner_id, *, source_keys):
        self.calls.append(("per_user", owner_id))
        return [MonitorMatch(n, ("unfiltered",)) for n in self.notices], SimpleNamespace(
            attempted_sources=tuple(source_keys), successful_sources=tuple(source_keys),
            total_failure=False, failures=(),
        )

    async def profile_for_owner(self, owner_id):
        return profile("канализации" if owner_id == 1 else "лекарственных")

    async def unseen_matches(self, owner_id, matches):
        return [m for m in matches
                if (owner_id, m.notice.tender_number) not in self.claimed]

    async def claim_new(self, owner_id, matches):
        self.claimed.extend((owner_id, m.notice.tender_number) for m in matches)


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))
        return SimpleNamespace(message_id=len(self.sent), chat=SimpleNamespace(id=chat_id))


def test_two_profiles_share_one_ingushetia_poll_but_filter_and_ack_separately():
    async def run():
        stop = asyncio.Event()
        service = FakeService(stop)
        bot = FakeBot()
        catalog = FakeCatalog(("ru_ingushetia_eis44", "ru_ingushetia_fabrikant44"))
        await monitor_loop(bot, service, stop, source_catalog=catalog)
        assert service.calls == [("shared", ("ru_ingushetia_eis44", "ru_ingushetia_fabrikant44"))]
        assert len(bot.sent) == 2
        assert bot.sent[0][0] == 11 and IDS[0] in bot.sent[0][1]
        assert IDS[1] not in bot.sent[0][1]
        assert bot.sent[1][0] == 22 and IDS[1] in bot.sent[1][1]
        assert IDS[0] not in bot.sent[1][1]
        assert service.claimed == [(1, IDS[0]), (2, IDS[1])]
    asyncio.run(run())


def test_ingushetia_total_source_failure_does_not_claim_or_send_anything():
    async def run():
        stop = asyncio.Event()
        service = FakeService(stop, total_failure=True)
        bot = FakeBot()
        await monitor_loop(bot, service, stop,
                           source_catalog=FakeCatalog(("ru_ingushetia_eis44",)))
        assert service.calls == [("shared", ("ru_ingushetia_eis44",))]
        assert bot.sent == [] and service.claimed == []
    asyncio.run(run())


def test_mixed_profile_specific_eis_keeps_per_owner_upstream_search():
    async def run():
        stop = asyncio.Event()
        service = FakeService(stop)
        bot = FakeBot()
        await monitor_loop(bot, service, stop,
                           source_catalog=FakeCatalog(("eis", "ru_ingushetia_eis44")))
        assert service.calls == [("per_user", 1), ("per_user", 2)]
    asyncio.run(run())
