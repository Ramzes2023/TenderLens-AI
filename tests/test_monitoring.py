import asyncio
import tempfile
import unittest
from pathlib import Path

from app.monitoring.repository import MonitoringRepository
from app.monitoring.service import TenderMonitorService, prefilter_notice
from app.monitoring.config import MonitoringSettings
from app.scoring.models import CompanyProfile
from app.sources.eis_rss import build_eis_rss_urls, parse_eis_feed
from app.sources.models import TenderNotice


RSS = '''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>EIS</title>
<item>
<title>Поставка низковольтного оборудования 0123456789012345678</title>
<link>https://zakupki.gov.ru/example/1</link>
<guid>notice-1</guid>
<pubDate>Thu, 01 Oct 2026 10:00:00 +0300</pubDate>
<description><![CDATA[Заказчик: ООО Тест; НМЦК: 4 850 000 руб.; Окончание подачи заявок: 15.10.2026 18:00; Регион: Москва]]></description>
</item>
</channel></rss>'''.encode('utf-8')


class FakeSource:
    def __init__(self, notices):
        self.notices = notices
        self.calls = 0

    async def fetch(self, limit=20):
        self.calls += 1
        return self.notices[:limit]




class DynamicFakeSource(FakeSource):
    def __init__(self, notices, terms=()):
        super().__init__(notices)
        self.terms = tuple(terms)

    def for_search_terms(self, search_terms, *, max_feeds=5):
        return DynamicFakeSource(self.notices, tuple(search_terms)[:max_feeds])


class MonitoringTests(unittest.TestCase):
    def profile(self):
        return CompanyProfile(
            profile_version="1",
            company_name="Demo",
            product_keywords=["низковольтного оборудования"],
            allowed_regions=["Москва"],
            max_contract_value=5_000_000,
        )

    def settings(self):
        return MonitoringSettings(
            enabled=False,
            interval_seconds=600,
            max_items=20,
            max_notifications_per_cycle=5,
            request_timeout=30.0,
            eis_rss_urls=("https://zakupki.gov.ru/rss",),
            ca_bundle_file=None,
        )

    def test_parse_rss_normalizes_notice(self):
        notices = parse_eis_feed(RSS)
        self.assertEqual(len(notices), 1)
        notice = notices[0]
        self.assertEqual(notice.external_id, "notice-1")
        self.assertEqual(notice.customer, "ООО Тест")
        self.assertEqual(notice.initial_price, 4_850_000)
        self.assertEqual(notice.currency, "RUB")
        self.assertEqual(notice.region, "Москва")
        self.assertEqual(notice.deadline, "15.10.2026 18:00")

    def test_prefilter_matches_profile(self):
        notice = parse_eis_feed(RSS)[0]
        match = prefilter_notice(notice, self.profile())
        self.assertIsNotNone(match)
        self.assertTrue(any("Направление" in reason for reason in match.reasons))

    def test_prefilter_rejects_wrong_product(self):
        notice = TenderNotice(source="eis", external_id="x", title="Услуги клининга", url="https://example.test")
        self.assertIsNone(prefilter_notice(notice, self.profile()))

    def test_repository_deduplicates_per_user(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = MonitoringRepository(Path(directory) / "test.db")
            repo.initialize()
            self.assertTrue(repo.mark_seen(1, "eis", "n1"))
            self.assertFalse(repo.mark_seen(1, "eis", "n1"))
            self.assertTrue(repo.mark_seen(2, "eis", "n1"))

    def test_subscription_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = MonitoringRepository(Path(directory) / "test.db")
            repo.initialize()
            repo.set_subscription(7, 99, True)
            self.assertTrue(repo.get_subscription(7).enabled)
            self.assertEqual(repo.list_active()[0].chat_id, 99)
            repo.set_subscription(7, 99, False)
            self.assertFalse(repo.get_subscription(7).enabled)
            self.assertEqual(repo.list_active(), [])

    def test_service_scan_marks_only_first_delivery(self):
        notice = parse_eis_feed(RSS)[0]
        async def scenario():
            with tempfile.TemporaryDirectory() as directory:
                repo = MonitoringRepository(Path(directory) / "test.db")
                repo.initialize()
                source = FakeSource([notice])
                service = TenderMonitorService(self.settings(), source, repo, self.profile())
                first = await service.scan_new(1)
                second = await service.scan_new(1)
                return first, second
        first, second = asyncio.run(scenario())
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])

    def test_build_eis_urls_encodes_company_keywords(self):
        urls = build_eis_rss_urls(["алюминиевый профиль", "лист алюминиевый"], max_feeds=2)
        self.assertEqual(len(urls), 2)
        self.assertIn("searchString=%D0%B0%D0%BB%D1%8E%D0%BC", urls[0])
        self.assertIn("fz44=on", urls[0])

    def test_service_uses_owner_specific_profile_terms(self):
        notice = TenderNotice(
            source="eis", external_id="alu-1", title="Поставка алюминиевого профиля",
            url="https://example.test", initial_price=1_000_000, currency="RUB",
        )
        profiles = {
            1: CompanyProfile(profile_version="1", company_name="Alu", product_keywords=["алюминиевого профиля"], search_keywords=["алюминиевый профиль"]),
            2: CompanyProfile(profile_version="1", company_name="Cable", product_keywords=["кабель"], search_keywords=["кабель"]),
        }
        async def scenario():
            with tempfile.TemporaryDirectory() as directory:
                repo = MonitoringRepository(Path(directory) / "test.db")
                repo.initialize()
                source = DynamicFakeSource([notice])
                service = TenderMonitorService(
                    self.settings(), source, repo, None,
                    profile_resolver=lambda owner: profiles[owner],
                    scope_resolver=lambda owner: str(owner),
                )
                alu = await service.fetch_matches(1)
                cable = await service.fetch_matches(2)
                first = await service.claim_new(1, alu)
                second_same_company = await service.claim_new(1, alu)
                other_company_scope = await service.claim_new(2, [alu[0]])
                dynamic = service._source_for_profile(profiles[1])
                return alu, cable, first, second_same_company, other_company_scope, dynamic.terms
        alu, cable, first, second, other_scope, terms = asyncio.run(scenario())
        self.assertEqual(len(alu), 1)
        self.assertEqual(cable, [])
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(len(other_scope), 1)
        self.assertEqual(terms, ("алюминиевый профиль",))


if __name__ == "__main__":
    unittest.main()
