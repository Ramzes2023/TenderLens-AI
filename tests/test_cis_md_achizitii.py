"""Strict Moldova certified-marketplace normalization and activation tests.

Synthetic HTML only verifies parser contracts; real live tenant-free worker
acceptance is mandatory in a separate GitHub-hosted job.
"""
import unittest

from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.eis_rss import SourceError
from app.sources.ingestion import HOSTS
from app.sources.md_achizitii import (
    INDEX_URL, MAX_DETAILS, _amount, _calendar, discover_index, parse_marketplace_detail,
)

URL = "https://achizitii.md/ro/public/tender/21697174/"
HTML = """<html>
 <h2>Achiziție comercială</h2><span>21697174</span>
 <h1>Achiziționarea amestecurilor de gaze de calibrare</h1>
 <div>Propunerea ofertelor</div><div>de la</div><div>26.10.2026 11:00</div>
 <div>până la</div><div>05.11.2026 15:00</div>
 <div>Valoarea estimată fără TVA</div><div>100 000 MDL</div>
 <div>Informaţia despre solicitant</div><div>Denumirea</div>
 <a href="/ro/company/1003600026295">TERMOELECTRICA</a>
 <div>Datele achizitiei</div><div>Data publicării</div><div>16 oct 2026, 16:42</div>
 <div>MTender ID</div>
 <a href="https://mtender.gov.md/tenders/ocds-b3wdp1-MD-1792157952470">ocds-b3wdp1-MD-1792157952470</a>
 </html>"""


class MoldovaMarketplaceContracts(unittest.TestCase):
    def test_normalized_real_shape_with_public_buyer_ocid(self):
        n = parse_marketplace_detail(HTML, url=URL)
        self.assertEqual(n.source, "md_achizitii")
        self.assertEqual(n.external_id, "21697174")
        self.assertEqual(n.title, "Achiziționarea amestecurilor de gaze de calibrare")
        self.assertEqual(n.customer, "TERMOELECTRICA")
        self.assertEqual(n.tender_number, "ocds-b3wdp1-MD-1792157952470")
        self.assertEqual(n.currency, "MDL")
        self.assertEqual(n.initial_price, 100000.0)
        self.assertEqual(n.published_at, "2026-10-16T16:42:00")
        self.assertEqual(n.deadline, "2026-11-05T15:00:00")

    def test_identity_buyer_ocid_deadline_and_amount_fail_closed(self):
        for old,new in (
            ("21697174", "21212121"),
            ("TERMOELECTRICA", ""),
            ("ocds-b3wdp1-MD-1792157952470", "ocds-invalid"),
            ("05.11.2026 15:00", "05.11.2020 15:00"),
            ("100 000 MDL", "not-a-price"),
        ):
            with self.subTest(field=old), self.assertRaises(SourceError):
                parse_marketplace_detail(HTML.replace(old,new), url=URL)
        for other in ("https://evil.example/ro/public/tender/21697174/",
                      "http://achizitii.md/ro/public/tender/21697174/",
                      URL+"?token=secret"):
            with self.assertRaises(SourceError):
                parse_marketplace_detail(HTML,url=other)

    def test_index_contains_exact_public_detail_link(self):
        index = '<html><script><a href="/ro/public/tender/9999999/">bad</a></script>' + (
            '<h2><a href="/ro/public/tender/21697174/">Real tender title</a></h2>'
        ) + '</html>'
        self.assertEqual(discover_index(index), (URL,))
        with self.assertRaises(SourceError):
            discover_index("<html><script>var id=21697174</script></html>")

    def test_dates_and_amount_precise(self):
        self.assertEqual(_calendar("16 oct 2026, 16:42").isoformat(), "2026-10-16T16:42:00")
        self.assertEqual(_amount("100 000 MDL"), 100000.0)
        self.assertEqual(_amount("416 558,97 MDL"), 416558.97)
        for invalid in ("unknown", "NaN MDL", "20000000 USD", "1,1,1 MDL"):
            with self.assertRaises(SourceError):
                _amount(invalid)

    def test_staged_non_official_and_bounded_worker_host(self):
        cfg = MonitoringSettings(False, 600, 20, 5, 12, (), None)
        r = build_source_catalog(cfg).registry.get("md_achizitii")
        self.assertFalse(r.enabled)
        self.assertFalse(r.official)
        self.assertEqual(r.jurisdictions, ("MD",))
        self.assertEqual(HOSTS["md_achizitii"], frozenset({"achizitii.md"}))
        self.assertEqual(MAX_DETAILS, 5)
        self.assertEqual(INDEX_URL, "https://achizitii.md/ro/")


if __name__ == "__main__":
    unittest.main()
