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

    async def fetch_matches_from_catalog_for_profile(self, catalog, p, *, source_keys, max_items=None):
        assert p is None
        assert max_items == 100  # regional candidate pool, pre-tenant limit
        self.calls.append(("shared", tuple(source_keys)))
        if self.total_failure:
            matches = []
            success = ()
            failed = ("ru_ingushetia_eis44", "ru_ingushetia_fabrikant44")
        else:
            matches = [MonitorMatch(n, ("no prefilter",)) for n in self.notices
                       if n.source in source_keys]
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
        self.calls.append(("per_user", owner_id, tuple(source_keys)))
        return [MonitorMatch(n, ("unfiltered",)) for n in self.notices
                if n.source in source_keys], SimpleNamespace(
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
        # Even with default broader EIS enabled, fixed regional EIS is polled
        # once for all chats; only tenant-specific EIS requests run per-user.
        assert service.calls == [
            ("shared", ("ru_ingushetia_eis44",)),
            ("per_user", 1, ("eis",)),
            ("per_user", 2, ("eis",)),
        ]
        # Only the fixed EIS branch is enabled. Fabrikant notices from
        # the synthetic pool must never leak through a disabled source.
        assert len(bot.sent) == 1
        assert bot.sent[0][0] == 22 and IDS[1] in bot.sent[0][1]
    asyncio.run(run())


def test_shared_source_exception_does_not_kill_monitor_or_claim_any_alert():
    """An upstream exception before the per-user loop must not crash the bot."""
    async def run():
        stop = asyncio.Event()
        service = FakeService(stop)
        bot = FakeBot()
        async def fail_shared(catalog, p, *, source_keys, max_items=None):
            assert max_items == 100
            service.calls.append(("shared", tuple(source_keys)))
            raise OSError("internal proxy token=NEVER_LOG")
        service.fetch_matches_from_catalog_for_profile = fail_shared
        await monitor_loop(bot, service, stop,
                           source_catalog=FakeCatalog(("ru_ingushetia_eis44",)))
        assert service.calls == [("shared", ("ru_ingushetia_eis44",))]
        assert bot.sent == []
        assert service.claimed == []
    asyncio.run(run())


def test_shared_ingushetia_second_cycle_replays_no_old_alert_and_releases_new_match():
    """Offline three-cycle regression: only newly matched originals get receipts."""
    async def run():
        stop = asyncio.Event()
        service = FakeService(stop)
        bot = FakeBot()
        catalog = FakeCatalog(("ru_ingushetia_eis44", "ru_ingushetia_fabrikant44"))

        await monitor_loop(bot, service, stop, source_catalog=catalog)
        assert len(bot.sent) == 2
        assert service.claimed == [(1, IDS[0]), (2, IDS[1])]

        # The next scheduled poll rediscovers the same exact originals.
        # Each user must retain their acknowledgement across cycles.
        stop.clear()
        await monitor_loop(bot, service, stop, source_catalog=catalog)
        assert len(bot.sent) == 2
        assert service.claimed == [(1, IDS[0]), (2, IDS[1])]

        # A genuinely different regionally corroborated original later
        # appears in the same fixed feed. Only the matching tenant gets it.
        fresh_id = "0114500000826002403"
        service.notices.append(tender(
            fresh_id, "Монтаж ливневой канализации", "ru_ingushetia_fabrikant44"
        ))
        stop.clear()
        await monitor_loop(bot, service, stop, source_catalog=catalog)
        assert len(bot.sent) == 3
        assert bot.sent[2][0] == 11 and fresh_id in bot.sent[2][1]
        assert (1, fresh_id) in service.claimed
        assert (2, fresh_id) not in service.claimed
        assert len([c for c in service.calls if c[0] == "shared"]) == 3
        assert not any(c[0] == "per_user" for c in service.calls)

    asyncio.run(run())


def test_real_sqlite_shared_catalog_dedups_same_original_per_chat_only_after_verified_ack(tmp_path):
    """Offline: actual multi-source merge, tenant profiles, SQL receipts, and retry.

    Not a live procurement fetch or actual Telegram network delivery proof.
    """
    from app.monitoring.config import MonitoringSettings
    from app.monitoring.repository import MonitoringRepository
    from app.monitoring.service import TenderMonitorService
    from app.scoring.models import CompanyProfile
    from app.sources.catalog import SourceCatalog
    from app.sources.multi import MultiSourceFetcher
    from app.sources.registry import SourceRegistry, SourceRegistration

    number = "0114500000826002402"
    other = "0114500000826002403"
    events = []
    class SyntheticFixedSource:
        def __init__(self, name, notices):
            self.name, self.notices = name, notices
        async def fetch(self, limit=20):
            events.append(("fetch", self.name))
            return self.notices[:limit]

    official = TenderNotice(
        source="ru_ingushetia_eis44", external_id=number, tender_number=number,
        title="Поставка медицинского оборудования",
        region="Республика Ингушетия",
        customer="КОМИТЕТ ГОСЗАКАЗА РЕСПУБЛИКИ ИНГУШЕТИЯ",
        url="https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber=" + number,
    )
    mirror = TenderNotice(
        source="ru_ingushetia_fabrikant44", external_id=number, tender_number=number,
        title=official.title, region=official.region, customer=official.customer,
        url="https://44.fabrikant.ru/44/procedure/ea21/" + number,
    )
    repair = TenderNotice(
        source="ru_ingushetia_fabrikant44", external_id=other, tender_number=other,
        title="Ремонт кровли школы", region=official.region, customer=official.customer,
        url="https://44.fabrikant.ru/44/procedure/ea21/" + other,
    )

    registry = SourceRegistry([
        SourceRegistration(
            key="ru_ingushetia_eis44", display_name="Synthetic EIS fixed regional",
            source=SyntheticFixedSource("ru_ingushetia_eis44", [official]),
            jurisdictions=("RU",),
        ),
        SourceRegistration(
            key="ru_ingushetia_fabrikant44", display_name="Synthetic Fabrikant fixed regional",
            source=SyntheticFixedSource("ru_ingushetia_fabrikant44", [mirror, repair]),
            jurisdictions=("RU",),
        ),
    ])
    catalog = SourceCatalog(registry, MultiSourceFetcher(registry))
    repo = MonitoringRepository(tmp_path / "monitor-real.sqlite")
    repo.initialize()
    repo.set_subscription(1, 11, True)
    repo.set_subscription(2, 22, True)
    settings = MonitoringSettings(
        enabled=True, interval_seconds=600, max_items=10,
        max_notifications_per_cycle=5, request_timeout=15,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        ru_background_catalog_enabled=True,
    )

    profiles = {
        1: CompanyProfile(profile_version="1", company_name="Tenant equipment",
                          search_keywords=["оборудования"],
                          allowed_regions=["Ингушетия"]),
        2: CompanyProfile(profile_version="1", company_name="Tenant repairs",
                          search_keywords=["ремонт"],
                          allowed_regions=["Ингушетия"]),
    }
    service = TenderMonitorService(
        settings, None, repo, None,
        profile_resolver=lambda owner: profiles[owner],
    )
    stop = asyncio.Event()
    actual_subscriptions = service.active_subscriptions
    async def one_cycle():
        stop.set()
        return await actual_subscriptions()
    service.active_subscriptions = one_cycle

    class BotWithOneFailedAck:
        def __init__(self):
            self.attempts = []
            self.fail_chat22_once = True
        async def send_message(self, chat_id, text, **kwargs):
            self.attempts.append((chat_id, text))
            if chat_id == 22 and self.fail_chat22_once:
                self.fail_chat22_once = False
                return SimpleNamespace(message_id=0, chat=SimpleNamespace(id=22))
            return SimpleNamespace(
                message_id=len(self.attempts), chat=SimpleNamespace(id=chat_id)
            )

    async def run():
        bot = BotWithOneFailedAck()
        await monitor_loop(bot, service, stop, source_catalog=catalog)
        assert len([item for item in events if item[0] == "fetch"]) == 2
        assert len(bot.attempts) == 2
        by_chat = {chat: text for chat, text in bot.attempts}
        assert set(by_chat) == {11, 22}
        assert number in by_chat[11] and other not in by_chat[11]
        assert other in by_chat[22] and number not in by_chat[22]
        assert repo.seen(1, "eis_44", number)
        assert not repo.seen(2, "eis_44", other)

        # The retry must not re-notify tenant 1 about the EIS/Fabrikant
        # duplicate. Tenant 2 gets only its previously unconfirmed repair.
        stop.clear()
        await monitor_loop(bot, service, stop, source_catalog=catalog)
        assert len([item for item in events if item[0] == "fetch"]) == 4
        assert len(bot.attempts) == 3
        assert bot.attempts[-1][0] == 22 and other in bot.attempts[-1][1]
        assert repo.seen(2, "eis_44", other)
        assert not repo.seen(2, "eis_44", number)
        assert len([a for a in bot.attempts if a[0] == 11]) == 1

    asyncio.run(run())


def test_mixed_other_source_outage_keeps_independently_verified_regional_alerts(caplog):
    async def run():
        stop = asyncio.Event()
        service = FakeService(stop)
        bot = FakeBot()
        async def failing_extra(catalog, owner_id, *, source_keys):
            service.calls.append(("per_user", owner_id, tuple(source_keys)))
            raise OSError("private personalized query token=SECRET_MUST_NOT_LOG")
        service.fetch_matches_from_catalog = failing_extra
        await monitor_loop(
            bot, service, stop,
            source_catalog=FakeCatalog(("eis", "ru_ingushetia_eis44", "ru_ingushetia_fabrikant44")),
        )
        assert service.calls == [
            ("shared", ("ru_ingushetia_eis44", "ru_ingushetia_fabrikant44")),
            ("per_user", 1, ("eis",)),
            ("per_user", 2, ("eis",)),
        ]
        assert len(bot.sent) == 2
        assert {chat_id for chat_id, _ in bot.sent} == {11, 22}
        assert service.claimed == [(1, IDS[0]), (2, IDS[1])]
    asyncio.run(run())
    assert "Personalized RU source poll failed" in caplog.text
    assert "SECRET_MUST_NOT_LOG" not in caplog.text


def test_mixed_shared_outage_keeps_verified_personalized_matches(caplog):
    async def run():
        stop = asyncio.Event()
        service = FakeService(stop)
        bot = FakeBot()
        personal = [
            tender(IDS[0], "Устройство ливневой канализации", "eis"),
            tender(IDS[1], "Поставка лекарственных средств", "eis"),
        ]
        async def failed_fixed(catalog, profile, *, source_keys, max_items=None):
            assert max_items == 100
            service.calls.append(("shared", tuple(source_keys)))
            raise OSError("regional transport token=SECRET_MUST_NOT_LOG")
        async def fetched_extra(catalog, owner_id, *, source_keys):
            service.calls.append(("per_user", owner_id, tuple(source_keys)))
            assert source_keys == ("eis",)
            return [MonitorMatch(personal[owner_id - 1], ("personalized EIS",))], SimpleNamespace(
                attempted_sources=tuple(source_keys), successful_sources=tuple(source_keys),
                total_failure=False, failures=(),
            )
        service.fetch_matches_from_catalog_for_profile = failed_fixed
        service.fetch_matches_from_catalog = fetched_extra
        await monitor_loop(
            bot, service, stop,
            source_catalog=FakeCatalog(("eis", "ru_ingushetia_eis44")),
        )
        assert service.calls == [
            ("shared", ("ru_ingushetia_eis44",)),
            ("per_user", 1, ("eis",)),
            ("per_user", 2, ("eis",)),
        ]
        assert len(bot.sent) == 2
        assert {chat_id for chat_id, _ in bot.sent} == {11, 22}
        assert service.claimed == [(1, IDS[0]), (2, IDS[1])]
    asyncio.run(run())
    assert "Ingushetia shared source poll failed" in caplog.text
    assert "SECRET_MUST_NOT_LOG" not in caplog.text


def test_shared_regional_user_keyword_after_candidate_limit_does_not_miss_late_tender():
    """Synthetic regional batch: matching notice is after per-user max_items."""
    async def run():
        stop = asyncio.Event()
        service = FakeService(stop)
        service.settings.max_items = 3
        service.settings.max_notifications_per_cycle = 3
        service.notices = [
            tender(str(114500000826002500 + i).zfill(19),
                   "Закупка бумаги и канцелярии", "ru_ingushetia_eis44")
            for i in range(25)
        ] + [tender("0114500000826002599", "Устройство ливневой канализации",
                    "ru_ingushetia_eis44")]

        async def bounded_shared(catalog, p, *, source_keys, max_items=None):
            service.calls.append(("shared", tuple(source_keys)))
            assert p is None and max_items == 100
            from app.monitoring.service import MonitorMatch
            matches = [MonitorMatch(n, ("candidate",)) for n in service.notices
                       if n.source in source_keys][:max_items]
            return matches, SimpleNamespace(
                attempted_sources=tuple(source_keys),
                successful_sources=tuple(source_keys),
                total_failure=False, failures=(),
            )
        service.fetch_matches_from_catalog_for_profile = bounded_shared

        # User 1 searches "канализации" while user 2 searches "лекарственных";
        # only the first should receive the matching late regional procurement.
        bot = FakeBot()
        await monitor_loop(bot, service, stop,
                           source_catalog=FakeCatalog(("ru_ingushetia_eis44",)))
        assert service.calls == [("shared", ("ru_ingushetia_eis44",))]
        assert len(bot.sent) == 1
        assert bot.sent[0][0] == 11 and "0114500000826002599" in bot.sent[0][1]
        assert service.claimed == [(1, "0114500000826002599")]
    asyncio.run(run())


def test_real_monitor_service_defaults_to_user_limit_but_shared_fetches_100_candidates():
    """Verify the actual source-catalog boundary, not just a fake monitor method."""
    from app.monitoring.config import MonitoringSettings
    from app.monitoring.service import TenderMonitorService

    opts = MonitoringSettings(
        enabled=True, interval_seconds=600, max_items=3,
        max_notifications_per_cycle=2, request_timeout=15,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        ru_background_catalog_enabled=True,
    )
    seen = []

    class Catalog:
        async def fetch(self, *, limit_per_source, source_keys, search_terms, max_eis_feeds):
            seen.append((limit_per_source, source_keys, search_terms))
            all_notices = [
                tender(str(114500000826002500 + i).zfill(19),
                       "Поставка хозяйственных товаров", "ru_ingushetia_eis44")
                for i in range(25)
            ] + [tender("0114500000826002599", "Устройство ливневой канализации",
                        "ru_ingushetia_eis44")]
            return SimpleNamespace(notices=tuple(all_notices[:limit_per_source]))

    service = TenderMonitorService(opts, None, None, None)

    async def check():
        normal, _ = await service.fetch_matches_from_catalog_for_profile(
            Catalog(), None, source_keys=("ru_ingushetia_eis44",))
        shared, _ = await service.fetch_matches_from_catalog_for_profile(
            Catalog(), None, source_keys=("ru_ingushetia_eis44",), max_items=100)
        assert len(normal) == 3
        assert len(shared) == 26
        assert shared[-1].notice.tender_number == "0114500000826002599"
        for invalid in (0, 101, -1, True, 3.5, "100"):
            try:
                await service.fetch_matches_from_catalog_for_profile(
                    Catalog(), None, source_keys=("ru_ingushetia_eis44",),
                    max_items=invalid,
                )
            except ValueError:
                pass
            else:
                raise AssertionError("Unbounded or invalid shared poll candidate limit")

    asyncio.run(check())
    assert seen == [
        (3, ("ru_ingushetia_eis44",), ()),
        (100, ("ru_ingushetia_eis44",), ()),
    ]


def test_late_unseen_regional_notice_is_not_starved_by_seen_per_source_prefix():
    """Synthetic fixed regional batch; no live procurement or Bot API claims.

    Five matching originals exist, first three were already delivered.
    max_items=3 is a per-source limit of *unseen* matches, not a reason
    to discard the fourth notice before checking durable seen identity.
    """
    async def run():
        stop = asyncio.Event()
        service = FakeService(stop)
        service.settings.max_items = 3
        service.settings.max_notifications_per_cycle = 2
        service.notices = [
            tender(f"011450000082600{2600 + i:04d}",
                   "Устройство ливневой канализации",
                   "ru_ingushetia_eis44")
            for i in range(5)
        ]
        first_three = {n.tender_number for n in service.notices[:3]}
        service.claimed.extend((1, number) for number in first_three)
        bot = FakeBot()
        await monitor_loop(
            bot, service, stop,
            source_catalog=FakeCatalog(("ru_ingushetia_eis44",)),
        )
        owner_one = [body for chat, body in bot.sent if chat == 11]
        assert len(owner_one) == 2
        assert service.notices[3].tender_number in owner_one[0]
        assert service.notices[4].tender_number in owner_one[1]
        assert not any(number in body for number in first_three for body in owner_one)
        assert len([call for call in service.calls if call[0] == "shared"]) == 1
        assert (1, service.notices[3].tender_number) in service.claimed
        assert (1, service.notices[4].tender_number) in service.claimed
    asyncio.run(run())
