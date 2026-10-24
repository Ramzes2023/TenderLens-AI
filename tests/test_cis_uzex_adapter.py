"""Strict normalized Uzbekistan notices and default-disabled catalog contracts."""
import unittest

from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.eis_rss import SourceError
from app.sources.ingestion import HOSTS
from app.sources.uz_uzex import DETAIL_PREFIX, parse_uzex_tradelist, parse_uzex_current_batch, _uzex_public_rows


FIRST = {
    "id": 510591,
    "type_id": 1,
    "display_no": "26111006510591",
    "name": "Maxsus uskunalar bilan jihozlangan xizmat mototsikllarini yetkazib berish",
    "seller_name": "ГУВД г.Ташкента",
    "start_date": "2026-09-10T10:38:42+05:00",
    "end_date": "2026-09-28T10:38:42+05:00",
    "cost": 6860000000.0,
    "currency_codeabc": "UZS",
}


class OfficialUzexContracts(unittest.TestCase):
    def test_one_bounded_public_tender_normalization(self):
        rows = parse_uzex_tradelist([FIRST], type_id=1)
        self.assertEqual(len(rows), 1)
        item = rows[0]
        self.assertEqual(item.source, "uz_uzex")
        self.assertEqual(item.external_id, "1-510591")
        self.assertEqual(item.title, FIRST["name"])
        self.assertEqual(item.customer, FIRST["seller_name"])
        self.assertEqual(item.deadline, FIRST["end_date"])
        self.assertEqual(item.url, DETAIL_PREFIX + "510591")
        self.assertEqual(item.currency, "UZS")
        self.assertEqual(item.initial_price, FIRST["cost"])

    def test_selection_has_separate_identity(self):
        selection = dict(FIRST, id=512029, type_id=2, display_no="26110012512029")
        row = parse_uzex_tradelist([selection], type_id=2)[0]
        self.assertEqual(row.external_id, "2-512029")
        self.assertIn("selection", row.summary)

    def test_strict_rejections(self):
        for property_name in ("name", "seller_name", "end_date", "start_date", "type_id"):
            bad = dict(FIRST)
            del bad[property_name]
            with self.subTest(property_name=property_name), self.assertRaises(SourceError):
                parse_uzex_tradelist([bad], type_id=1)
        for value in ("NaN", -1.0, float("inf"), True):
            with self.subTest(cost=value), self.assertRaises(SourceError):
                parse_uzex_tradelist([dict(FIRST, cost=value)], type_id=1)
        for currency in ("BTC_USD", "uzs", "javascript"):
            with self.subTest(currency=currency), self.assertRaises(SourceError):
                parse_uzex_tradelist([dict(FIRST, currency_codeabc=currency)], type_id=1)
        with self.assertRaises(SourceError):
            parse_uzex_tradelist([FIRST, FIRST], type_id=1)
        with self.assertRaises(SourceError):
            parse_uzex_tradelist([], type_id=1)
        with self.assertRaises(SourceError):
            parse_uzex_tradelist([{"id": 510591}], type_id=1)

    def test_live_batch_keeps_only_independently_complete_official_rows(self):
        valid2 = dict(FIRST, id=510592, display_no="26111006510592")
        invalid = dict(FIRST, id=510593, cost=float("nan"))
        invalid_date = dict(FIRST, id=510594, end_date="n/a")
        accepted = parse_uzex_current_batch(
            [FIRST, invalid, invalid_date, valid2], type_id=1)
        self.assertEqual([n.external_id for n in accepted], [
            "1-510591", "1-510592"])
        self.assertTrue(all(n.url.startswith(DETAIL_PREFIX) for n in accepted))
        with self.assertRaises(SourceError):
            parse_uzex_current_batch([invalid, invalid_date], type_id=1)
        with self.assertRaises(SourceError):
            parse_uzex_current_batch([FIRST, FIRST], type_id=1)
        with self.assertRaises(SourceError):
            parse_uzex_current_batch([{"id": 510591}], type_id=1)
        with self.assertRaises(SourceError):
            parse_uzex_current_batch([], type_id=1)

    def test_official_list_envelopes_never_bypass_row_validation(self):
        for body in ([FIRST], {"data": [FIRST]}, {"items": [FIRST]}):
            self.assertEqual(
                [n.external_id for n in parse_uzex_current_batch(_uzex_public_rows(body), type_id=1)],
                ["1-510591"],
            )
        for bad in ({"ok": False, "data": [FIRST]}, {"success": False, "items": [FIRST]},
                    {"data": {"id": FIRST["id"]}}, {"error": "blocked"}, {"items": "text"}):
            with self.subTest(bad=bad), self.assertRaises(SourceError):
                _uzex_public_rows(bad)
        with self.assertRaises(SourceError):
            parse_uzex_current_batch(_uzex_public_rows({"data": [{"id": FIRST["id"]}]}), type_id=1)

    def test_catalog_staged_and_worker_host_pinned(self):
        config = MonitoringSettings(False, 600, 20, 5, 12, (), None)
        registration = build_source_catalog(config).registry.get("uz_uzex")
        self.assertTrue(registration.official)
        self.assertFalse(registration.enabled)
        self.assertEqual(registration.jurisdictions, ("UZ",))
        self.assertEqual(HOSTS["uz_uzex"],
                         frozenset({"apietender.uzex.uz", "etender.uzex.uz"}))


if __name__ == "__main__":
    unittest.main()
