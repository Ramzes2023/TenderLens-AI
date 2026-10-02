import unittest
from types import SimpleNamespace

from app.bot.companies import (
    _is_keep,
    _resolve_company,
    build_profile_from_edit,
    company_switch_markup,
    format_edit_summary,
)
from app.scoring.models import CompanyProfile


class CompanyManagementTests(unittest.TestCase):
    def test_keep_aliases(self):
        self.assertTrue(_is_keep("="))
        self.assertTrue(_is_keep("оставить"))
        self.assertTrue(_is_keep(" KEEP "))
        self.assertFalse(_is_keep("новое значение"))

    def test_resolve_company_by_id_or_name(self):
        items = [
            SimpleNamespace(id=1, name="AluTrade"),
            SimpleNamespace(id=2, name="MedSupply"),
        ]
        self.assertEqual(_resolve_company(items, "2").name, "MedSupply")
        self.assertEqual(_resolve_company(items, "alutrade").id, 1)
        self.assertIsNone(_resolve_company(items, "unknown"))

    def test_edit_preserves_advanced_profile_fields(self):
        original = CompanyProfile(
            profile_version="workspace-1",
            company_name="AluTrade",
            business_mode="sell",
            industry="Metals",
            product_keywords=["алюминий"],
            search_keywords=["алюминий"],
            excluded_keywords=["лом"],
            allowed_regions=["Москва"],
            allowed_countries=["Россия"],
            accepted_currencies=["RUB", "EUR"],
            max_contract_value=50_000_000,
            max_bid_security_percent=5,
            available_document_keywords=["лицензия"],
        )
        updated = build_profile_from_edit({
            "original_profile": original.model_dump(mode="json"),
            "name": "AluTrade International",
            "mode": "both",
            "keywords": ["алюминий", "профиль"],
            "keywords_changed": True,
            "regions": [],
            "budget": 75_000_000,
        })
        self.assertEqual(updated.company_name, "AluTrade International")
        self.assertEqual(updated.business_mode, "both")
        self.assertEqual(updated.monitoring_keywords, ["алюминий", "профиль"])
        self.assertEqual(updated.allowed_regions, [])
        self.assertEqual(updated.max_contract_value, 75_000_000)
        self.assertEqual(updated.industry, "Metals")
        self.assertEqual(updated.excluded_keywords, ["лом"])
        self.assertEqual(updated.allowed_countries, ["Россия"])
        self.assertEqual(updated.accepted_currencies, ["RUB", "EUR"])
        self.assertEqual(updated.max_bid_security_percent, 5)
        self.assertEqual(updated.available_document_keywords, ["лицензия"])
        self.assertFalse(updated.hard_stop_on_region)
        self.assertTrue(updated.hard_stop_on_budget)

    def test_edit_can_keep_distinct_product_and_search_keywords(self):
        original = CompanyProfile(
            profile_version="workspace-1",
            company_name="Example",
            product_keywords=["product truth"],
            search_keywords=["search term"],
        )
        updated = build_profile_from_edit({
            "original_profile": original.model_dump(mode="json"),
            "name": "Example",
            "mode": "sell",
            "keywords": ["search term"],
            "keywords_changed": False,
            "regions": [],
            "budget": None,
        })
        self.assertEqual(updated.product_keywords, ["product truth"])
        self.assertEqual(updated.search_keywords, ["search term"])

    def test_edit_summary_is_human_readable(self):
        summary = format_edit_summary({
            "name": "MedSupply",
            "mode": "sell",
            "keywords": ["медицинское оборудование"],
            "regions": [],
            "budget": None,
        })
        self.assertIn("MedSupply", summary)
        self.assertIn("сохранить", summary)
        self.assertIn("без ограничения", summary)
        self.assertIn("без лимита", summary)

    def test_switch_markup_contains_company_ids(self):
        items = [
            SimpleNamespace(id=1, name="AluTrade", is_active=True),
            SimpleNamespace(id=2, name="MedSupply", is_active=False),
        ]
        markup = company_switch_markup(items)
        self.assertIsNotNone(markup)
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "company_use:1")
        self.assertEqual(markup.inline_keyboard[1][0].callback_data, "company_use:2")


if __name__ == "__main__":
    unittest.main()
