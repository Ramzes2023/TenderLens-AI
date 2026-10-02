import tempfile
import unittest
from pathlib import Path

from app.companies import CompanyRepository, CompanyRepositoryError, CompanyService
from app.scoring.models import CompanyProfile


class CompanyWorkspaceTests(unittest.TestCase):
    def profile(self, name: str, keyword: str) -> CompanyProfile:
        return CompanyProfile(
            profile_version="workspace-1",
            company_name=name,
            business_mode="sell",
            product_keywords=[keyword],
            search_keywords=[keyword, keyword + " профиль"],
            max_contract_value=10_000_000,
        )

    def test_create_list_activate_is_owner_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = CompanyRepository(Path(directory) / "companies.db")
            repo.initialize()
            first = repo.create(10, "Electrical", self.profile("Electrical", "контактор"))
            second = repo.create(10, "Aluminium", self.profile("Aluminium", "алюминий"))
            other = repo.create(20, "Medical", self.profile("Medical", "медицинское оборудование"))

            self.assertFalse(repo.get(10, first.id).is_active)
            self.assertTrue(repo.get(10, second.id).is_active)
            self.assertIsNone(repo.get(10, other.id))
            self.assertEqual(len(repo.list_for_owner(10)), 2)
            activated = repo.set_active(10, first.id)
            self.assertTrue(activated.is_active)
            self.assertEqual(repo.active(10).id, first.id)

    def test_service_returns_fallback_until_personal_profile_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = CompanyRepository(Path(directory) / "companies.db")
            repo.initialize()
            fallback = self.profile("Fallback", "электротехника")
            service = CompanyService(repo, fallback_profile=fallback)
            self.assertIs(service.profile_for_owner(99), fallback)
            created = service.create(99, "AluTrade", self.profile("AluTrade", "алюминий"))
            self.assertEqual(service.profile_for_owner(99).company_name, "AluTrade")
            self.assertEqual(service.scope_for_owner(99), str(created.id))

    def test_duplicate_name_and_cross_owner_activation_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = CompanyRepository(Path(directory) / "companies.db")
            repo.initialize()
            created = repo.create(1, "Demo", self.profile("Demo", "кабель"))
            with self.assertRaises(CompanyRepositoryError):
                repo.create(1, "Demo", self.profile("Demo 2", "шкаф"))
            with self.assertRaises(CompanyRepositoryError):
                repo.set_active(2, created.id)

    def test_delete_active_selects_remaining_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = CompanyRepository(Path(directory) / "companies.db")
            repo.initialize()
            first = repo.create(1, "One", self.profile("One", "один"))
            second = repo.create(1, "Two", self.profile("Two", "два"))
            self.assertEqual(repo.active(1).id, second.id)
            self.assertTrue(repo.delete(1, second.id))
            self.assertEqual(repo.active(1).id, first.id)

    def test_profile_budget_range_validation(self):
        with self.assertRaises(ValueError):
            CompanyProfile(
                profile_version="1",
                company_name="Bad",
                min_contract_value=1000,
                max_contract_value=100,
            )


if __name__ == "__main__":
    unittest.main()
