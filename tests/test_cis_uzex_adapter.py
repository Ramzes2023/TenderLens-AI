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


class CurrentBatchUzexContracts(unittest.TestCase):
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

    def test_live_only_bounded_missing_title_or_buyer_is_excluded(self):
        # Genuine official 2026-10-19 TypeId=1 had 19 complete / 20 native rows.
        # An incomplete row must never reach user search, while complete rows
        # keep all independently checked original IDs, amounts and deadlines.
        incomplete = dict(FIRST, id=510592, seller_name="")
        result = parse_uzex_tradelist(
            [FIRST, incomplete], type_id=1, allow_incomplete=True,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].external_id, "1-510591")
        self.assertEqual(result[0].initial_price, FIRST["cost"])
        self.assertEqual(result[0].deadline, FIRST["end_date"])
        # Strict callers cannot accidentally opt into skipping.
        with self.assertRaises(SourceError):
            parse_uzex_tradelist([FIRST, incomplete], type_id=1)

    def test_live_incomplete_policy_never_accepts_malicious_invalid_rows(self):
        incomplete = dict(FIRST, id=510592, seller_name="")
        with self.assertRaises(SourceError):
            parse_uzex_tradelist([incomplete], type_id=1, allow_incomplete=True)
        with self.assertRaises(SourceError):
            parse_uzex_tradelist([FIRST, incomplete, incomplete], type_id=1,
                                allow_incomplete=True)
        rows = [dict(FIRST, id=510600 + n, seller_name="") for n in range(3)]
        with self.assertRaises(SourceError):
            parse_uzex_tradelist([FIRST] + rows, type_id=1, allow_incomplete=True)
        with self.assertRaises(SourceError):
            parse_uzex_tradelist([FIRST, dict(FIRST, id=510593, cost=-1)],
                                type_id=1, allow_incomplete=True)
        with self.assertRaises(SourceError):
            parse_uzex_tradelist([FIRST, dict(FIRST, id=510593, type_id=3)],
                                type_id=1, allow_incomplete=True)
        with self.assertRaises(SourceError):
            parse_uzex_tradelist([FIRST, dict(FIRST, id=510593, currency_codeabc="BTC_USD")],
                                type_id=1, allow_incomplete=True)
        with self.assertRaises(SourceError):
            parse_uzex_tradelist([FIRST, dict(FIRST, id=510593, end_date="bad")],
                                type_id=1, allow_incomplete=True)

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


def test_uneven_live_uzex_categories_preserve_every_verified_notice(monkeypatch):
    """Synthetic official responses: type 1 has one notice, type 2 has three."""
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    import app.sources.uz_uzex as adapter

    first = dict(FIRST)
    selections = [
        dict(FIRST, id=512029 + i, type_id=2, display_no=str(26110012512029 + i))
        for i in range(3)
    ]
    seen = []

    class Client:
        async def post(self, url, *, json, headers):
            assert url == adapter.API_URL
            assert headers["Accept"] == "application/json"
            kind = json["TypeId"]
            seen.append(kind)
            rows = [first] if kind == 1 else selections
            return SimpleNamespace(
                content=b"official-public-JSON",
                headers={"content-type": "application/json"},
                json=lambda: rows,
                raise_for_status=lambda: None,
            )

    @asynccontextmanager
    async def fake_client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        yield Client()

    monkeypatch.setattr(adapter, "source_client", fake_client)
    records = asyncio.run(adapter.UzbekistanUzexSource()._fetch(4))
    assert seen == [1, 2]  # both real categories fetched, neither bypassed
    assert [record.external_id for record in records] == [
        "1-510591", "2-512029", "2-512030", "2-512031",
    ]
    assert all(record.title and record.customer and record.url.startswith(adapter.DETAIL_PREFIX)
               for record in records)
