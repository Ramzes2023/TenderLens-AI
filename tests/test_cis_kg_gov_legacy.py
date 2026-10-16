"""Strict offline safety contracts for the Kyrgyz official legacy notice listing.

Synthetic HTML only tests the parser: it never substitutes for mandatory live
official HTTPS -> leased worker -> disposable SQLite -> saved search acceptance.
"""
import unittest
from html import escape

from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.eis_rss import SourceError
from app.sources.ingestion import HOSTS
from app.sources.kg_gov_legacy import parse_kg_legacy_list, LIST_URL

COLUMNS = (
    "number 261016611792378",
    "Name of company Учреждение районная государственная больница",
    "Type of procurement Goods",
    "purchase Name Приобретение медицинских расходных материалов",
    "Open in New Tab",
    "procurement method REQUEST_FOR_QUOTATION",
    "Planned amount 255,200",
    "Date published 16.10.2026 17:56",
    "Bids Submission Deadline 22.10.2026 09:00",
    "",
    "",
)


def fixture(columns=COLUMNS, *, link="view.xhtml?id=561794973", second=False):
    cells = []
    for i, cell in enumerate(columns):
        value = escape(cell)
        if i == 4:
            value = '<a href="' + escape(link, quote=True) + '">open</a>'
        cells.append("<td>" + value + "</td>")
    extra = "".join(cells) if second else ""
    return "<html><table><tr>" + "<th>header</th>" * 11 + "</tr><tr>" + "".join(cells) + "</tr>" + (
        "<tr>" + extra + "</tr>" if second else ""
    ) + "</table></html>"


class KyrgyzGovernmentLegacyContracts(unittest.TestCase):
    def test_real_shape_normalizes_public_notice(self):
        notices = parse_kg_legacy_list(fixture())
        self.assertEqual(len(notices), 1)
        n = notices[0]
        self.assertEqual(n.source, "kg_gov_legacy")
        self.assertEqual(n.external_id, "261016611792378")
        self.assertEqual(n.url, "https://zakupki.gov.kg/popp/view/order/view.xhtml?id=561794973")
        self.assertEqual(n.initial_price, 255200.0)
        self.assertEqual(n.currency, "KGS")
        self.assertEqual(n.published_at, "2026-10-16T17:56:00")
        self.assertEqual(n.deadline, "2026-10-22T09:00:00")

    def test_rejects_incomplete_and_unsafe_fields(self):
        for index, bad in ((0, "number 123"), (1, "Name of company"),
                           (3, "purchase Name"), (6, "Planned amount infinity"),
                           (7, "Date published 2026-10-16"),
                           (8, "Bids Submission Deadline 10.10.2026 09:00")):
            row = list(COLUMNS)
            row[index] = bad
            with self.subTest(index=index), self.assertRaises(SourceError):
                parse_kg_legacy_list(fixture(row))
        for link in ("https://attacker.example/popp/view/order/view.xhtml?id=12345",
                     "javascript:alert(1)", "view.xhtml?id=1&token=x"):
            with self.subTest(link=link), self.assertRaises(SourceError):
                parse_kg_legacy_list(fixture(link=link))
        with self.assertRaises(SourceError):
            parse_kg_legacy_list(fixture(second=True))

    def test_no_static_js_application_as_public_notices(self):
        for html in ("<script>const number=261016611792378;</script>",
                     "<table><tr><td>Loading ...</td></tr></table>",
                     "<html></html>"):
            with self.assertRaises(SourceError):
                parse_kg_legacy_list(html)

    def test_source_default_disabled_and_host_allowlist(self):
        catalog = build_source_catalog(MonitoringSettings(False, 600, 20, 5, 12, (), None))
        reg = catalog.registry.get("kg_gov_legacy")
        self.assertTrue(reg.official)
        self.assertFalse(reg.enabled)
        self.assertEqual(reg.jurisdictions, ("KG",))
        self.assertEqual(reg.homepage_url, LIST_URL)
        self.assertEqual(HOSTS["kg_gov_legacy"], frozenset({"zakupki.gov.kg"}))


if __name__ == "__main__":
    unittest.main()
