import tempfile
import unittest
from pathlib import Path

from app.auth import AuthRepository, AuthRepositoryError
from app.companies import CompanyRepository
from app.database import TenderRepository
from app.monitoring import MonitoringRepository
from app.scoring.models import CompanyProfile
from app.models.tender import TenderAnalysis


def profile(name: str) -> CompanyProfile:
    return CompanyProfile(
        profile_version="1",
        company_name=name,
        business_mode="sell",
        product_keywords=["aluminium"],
        search_keywords=["aluminium"],
    )


class SafeLegacyOwnerLinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "link.db"

        self.auth = AuthRepository(self.path)
        self.auth.initialize()

        self.companies = CompanyRepository(self.path)
        self.companies.initialize()

        self.monitoring = MonitoringRepository(self.path)
        self.monitoring.initialize()

        self.tenders = TenderRepository(self.path)
        self.tenders.initialize()

    def account(self):
        return self.auth.create_account(
            "owner@example.com",
            "not-a-real-password-hash",
        )

    def test_moves_company_active_state_and_monitor_seen_to_legacy_owner(self):
        account = self.account()
        source = account.owner_user_id
        target = 1844282717

        company = self.companies.create(
            source,
            "AluTrade Test",
            profile("AluTrade Test"),
            make_active=True,
        )
        self.monitoring.mark_seen(source, "eis", "one")
        self.monitoring.mark_seen(source, "eis", "two")

        linked = self.auth.link_owner(account.id, target)

        self.assertEqual(linked.owner_user_id, target)
        moved = self.companies.list_for_owner(target)
        self.assertEqual([item.name for item in moved], ["AluTrade Test"])
        self.assertTrue(moved[0].is_active)
        self.assertEqual(moved[0].id, company.id)
        self.assertEqual(self.companies.list_for_owner(source), [])
        self.assertTrue(self.monitoring.seen(target, "eis", "one"))
        self.assertTrue(self.monitoring.seen(target, "eis", "two"))
        self.assertFalse(self.monitoring.seen(source, "eis", "one"))

    def test_fresh_web_account_can_claim_existing_legacy_owner_state(self):
        account = self.account()
        source = account.owner_user_id
        target = 1844282717

        legacy = self.companies.create(
            target,
            "AluTrade",
            profile("AluTrade"),
            make_active=True,
        )
        self.monitoring.mark_seen(target, "eis", "legacy")

        linked = self.auth.link_owner(account.id, target)

        self.assertEqual(linked.owner_user_id, target)
        self.assertEqual(self.companies.active(target).id, legacy.id)
        self.assertTrue(self.monitoring.seen(target, "eis", "legacy"))
        self.assertEqual(self.companies.list_for_owner(source), [])

    def test_preserves_existing_legacy_active_company_when_both_sides_have_data(self):
        account = self.account()
        source = account.owner_user_id
        target = 1844282717

        self.companies.create(
            source,
            "Web Company",
            profile("Web Company"),
            make_active=True,
        )
        legacy = self.companies.create(
            target,
            "Legacy Company",
            profile("Legacy Company"),
            make_active=True,
        )

        self.auth.link_owner(account.id, target)

        items = self.companies.list_for_owner(target)
        self.assertEqual({item.name for item in items}, {"Web Company", "Legacy Company"})
        self.assertEqual(self.companies.active(target).id, legacy.id)

    def test_duplicate_company_name_blocks_link_and_rolls_back(self):
        account = self.account()
        source = account.owner_user_id
        target = 1844282717

        self.companies.create(source, "Same Name", profile("Same Name"))
        self.companies.create(target, "Same Name", profile("Same Name"))

        with self.assertRaises(AuthRepositoryError):
            self.auth.link_owner(account.id, target)

        self.assertEqual(
            self.auth.find_account_by_id(account.id).owner_user_id,
            source,
        )
        self.assertEqual(len(self.companies.list_for_owner(source)), 1)
        self.assertEqual(len(self.companies.list_for_owner(target)), 1)

    def test_source_pdf_history_blocks_link_to_protect_qdrant_namespace(self):
        account = self.account()
        source = account.owner_user_id
        target = 1844282717

        analysis = TenderAnalysis()
        self.tenders.save_success(
            owner_user_id=source,
            chat_id=source,
            pdf_sha256="a" * 64,
            source_filename="test.pdf",
            pages=1,
            characters=10,
            analysis=analysis,
            scoring=None,
            analysis_truncated=False,
        )

        with self.assertRaisesRegex(AuthRepositoryError, "PDF history"):
            self.auth.link_owner(account.id, target)

        self.assertEqual(
            self.auth.find_account_by_id(account.id).owner_user_id,
            source,
        )


if __name__ == "__main__":
    unittest.main()
