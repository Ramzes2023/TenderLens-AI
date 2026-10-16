"""Strict offline contracts. Synthetic HTML never counts as upstream success."""
import unittest
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.eis_rss import SourceError
from app.sources.ingestion import HOSTS
from app.sources.kz_gov_html import HOST, INDEX_URL, parse_kz_public_html

COLUMNS = ("№", "Наименование объявления", "Способ", "Начало приема заявок",
           "Окончание приема заявок", "Сумма, тг.", "Статус")


def fixture(*, bad_link=None, bad_buyer=None, bad_date=None, repeat=5):
    import html
    result = ["<html><table><tr>"]
    result += ["<th>" + html.escape(s) + "</th>" for s in COLUMNS]
    result += ["</tr>"]
    for n in range(repeat):
        num = str(17804133 + n)
        href = bad_link if bad_link is not None else "/ru/announce/index/" + num
        buyer = bad_buyer if bad_buyer is not None else ("Закупка оборудования "
                 "Организатор: Государственное коммунальное казенное предприятие "
                 "«Городская техническая служба»")
        deadline = bad_date or "2026-10-19 17:00"
        cells = [f'<a href="{html.escape(href,quote=True)}">{num}-1</a>',
                 buyer, "Запрос ценовых предложений",
                 "2026-10-16 09:00", deadline, "115 990.00", "Опубликовано"]
        result.append("<tr>"+"".join("<td>"+s+"</td>" for s in cells)+"</tr>")
    result.append("</table></html>")
    return "".join(result)


class KazakhstanPublicHTMLContracts(unittest.TestCase):
    def test_strict_real_shape_normalizes_5_notices(self):
        rows = parse_kz_public_html(fixture())
        self.assertEqual(len(rows), 5)
        item = rows[0]
        self.assertEqual(item.source, "kz_gov_html")
        self.assertEqual(item.external_id, "17804133")
        self.assertEqual(item.currency, "KZT")
        self.assertEqual(item.initial_price, 115990.0)
        self.assertEqual(item.deadline, "2026-10-19T17:00:00")
        self.assertEqual(item.url, "https://old.goszakup.gov.kz/ru/announce/index/17804133")
        self.assertIn("Городская техническая служба", item.customer)

    def test_official_single_digit_hour_is_valid_but_invalid_date_fails(self):
        listing = fixture().replace("2026-10-16 09:00", "2026-10-16 9:00")
        notices = parse_kz_public_html(listing)
        self.assertEqual(len(notices), 5)
        with self.assertRaises(SourceError):
            parse_kz_public_html(fixture().replace("2026-10-16 09:00", "2026-99-16 09:00"))

    def test_no_html_or_partial_fields_never_count_as_tenders(self):
        for bad in ("<html>Loading</html>", "<script>var tender=17804133;</script>",
                    "<table><tr><td>17804133-1</td></tr></table>"):
            with self.assertRaises(SourceError):
                parse_kz_public_html(bad)
        with self.assertRaises(SourceError):
            parse_kz_public_html(fixture(repeat=4))
        for url in ("http://old.goszakup.gov.kz/ru/announce/index/17804133",
                    "https://evil.example/ru/announce/index/17804133",
                    "/ru/announce/index/17804133?token=x"):
            with self.subTest(url=url), self.assertRaises(SourceError):
                parse_kz_public_html(fixture(bad_link=url))
        for buyer in ("Организатор:", "Заголовок без заказчика"):
            with self.subTest(buyer=buyer), self.assertRaises(SourceError):
                parse_kz_public_html(fixture(bad_buyer=buyer))
        with self.assertRaises(SourceError):
            parse_kz_public_html(fixture(bad_date="2020-01-01 09:00"))
        with self.assertRaises(SourceError):
            parse_kz_public_html(fixture(repeat=5) * 2)

    def test_distinct_from_tokened_kz_goszakup_and_inactive(self):
        cfg = MonitoringSettings(False, 600, 20, 5, 12, (), None)
        catalog = build_source_catalog(cfg)
        new = catalog.registry.get("kz_gov_html")
        self.assertFalse(new.enabled)
        self.assertTrue(new.official)
        self.assertEqual(new.jurisdictions, ("KZ",))
        self.assertEqual(HOSTS["kz_gov_html"], frozenset({HOST}))
        self.assertEqual(INDEX_URL,
                         "https://old.goszakup.gov.kz/ru/search/announce?count_record=50&page=1")


if __name__ == "__main__":
    unittest.main()
