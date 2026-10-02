import unittest

from app.bot.companies import (
    _parse_budget,
    _parse_csv,
    _parse_mode,
    build_profile_from_setup,
    format_setup_summary,
)


class CompanyOnboardingTests(unittest.TestCase):
    def test_mode_accepts_english_and_russian_aliases(self):
        self.assertEqual(_parse_mode("sell"), "sell")
        self.assertEqual(_parse_mode("продавать"), "sell")
        self.assertEqual(_parse_mode("покупать"), "buy")
        self.assertEqual(_parse_mode("оба"), "both")
        self.assertIsNone(_parse_mode("unknown"))

    def test_csv_and_budget_parsers(self):
        self.assertEqual(_parse_csv("алюминий, профиль, лист"), ["алюминий", "профиль", "лист"])
        self.assertEqual(_parse_csv("-"), [])
        self.assertEqual(_parse_budget("50 000 000"), 50_000_000)
        self.assertIsNone(_parse_budget("-"))
        with self.assertRaises(ValueError):
            _parse_budget("ноль")

    def test_build_profile_matches_wizard_data(self):
        profile = build_profile_from_setup({
            "name": "AluTrade",
            "mode": "sell",
            "keywords": ["алюминий", "алюминиевый профиль"],
            "regions": ["Москва"],
            "budget": 50_000_000,
        })
        self.assertEqual(profile.company_name, "AluTrade")
        self.assertEqual(profile.business_mode, "sell")
        self.assertEqual(profile.monitoring_keywords, ["алюминий", "алюминиевый профиль"])
        self.assertEqual(profile.allowed_regions, ["Москва"])
        self.assertEqual(profile.max_contract_value, 50_000_000)
        self.assertTrue(profile.hard_stop_on_region)
        self.assertTrue(profile.hard_stop_on_budget)

    def test_summary_is_human_readable(self):
        summary = format_setup_summary({
            "name": "MedSupply",
            "mode": "sell",
            "keywords": ["медицинское оборудование"],
            "regions": [],
            "budget": None,
        })
        self.assertIn("MedSupply", summary)
        self.assertIn("медицинское оборудование", summary)
        self.assertIn("без ограничения", summary)
        self.assertIn("без лимита", summary)


if __name__ == "__main__":
    unittest.main()
