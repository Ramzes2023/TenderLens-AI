"""Strict AZ ADIF independent public small-quotation parser contracts."""
from datetime import date
import unittest

from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.eis_rss import SourceError
from app.sources.ingestion import HOSTS
from app.sources.az_adif_small import (
    SOURCE, BUYER, URL, MAX_RESULTS, parse_public_articles,
)

def fixture(title='mətbəə məhsullarının', deadline='19 oktyabr 2026-cı il saat 12:00-dək',
            date_value='02.10.2026', doc='https://adif.gov.az/media/2026/10/09/kotirovka_sorusu___-mtb.docx'):
    return f"""<html><article>
    <p>{BUYER} {title} satınalınması ilə bağlı kotirovka sorğusu elan edir.</p>
    <p>Təkliflər {deadline} qəbul olunur.</p>
    <p>Elanın yerləşdirilmə tarixi: {date_value}</p>
    <a href="{doc}">Kotirovka sorğusu</a>
    <a href="https://adif.gov.az/media/2026/05/13/ddiann_kotirovka_tklifi.docx">Generic vendor template</a>
    </article></html>"""

class ADIFSmallContracts(unittest.TestCase):
    def test_normalized_first_party_current_small_quotation(self):
        items = parse_public_articles(fixture(), today=date(2026,10,18))
        self.assertEqual(len(items), 1)
        n=items[0]
        self.assertEqual(n.source, SOURCE)
        self.assertEqual(n.customer, BUYER)
        self.assertEqual(n.published_at, "2026-10-02")
        self.assertEqual(n.deadline, "2026-10-19T12:00:00")
        self.assertEqual(n.url, "https://adif.gov.az/media/2026/10/09/kotirovka_sorusu___-mtb.docx")
        self.assertIsNone(n.initial_price)
        self.assertIsNone(n.currency)
        self.assertEqual(len(n.external_id),32)
        self.assertEqual(n.external_id,parse_public_articles(fixture(),today=date(2026,10,18))[0].external_id)

    def test_three_distinct_original_quote_documents(self):
        html="<html>"+''.join(fixture(title=name,doc=url).replace("<html>","").replace("</html>","")
          for name,url in (
            ("mətbəə məhsullarının","https://adif.gov.az/media/2026/10/09/kotirovka_sorusu___-mtb.docx"),
            ("dəftərxana məhsullarının","https://adif.gov.az/media/2026/10/09/kotirovka_sorusu___-dftrxana.docx"),
            ("təsərrüfat məhsullarının","https://adif.gov.az/media/2026/10/09/kotirovka_sorusu___-_tsrrfat.docx")
          ))+"</html>"
        items = parse_public_articles(html,today=date(2026,10,18))
        self.assertEqual(len(items),3)
        self.assertEqual(len(set(x.identity for x in items)),3)
        self.assertEqual(len(set(x.url for x in items)),3)

    def test_fail_closed_for_impostor_doc_wrong_date_or_malformed_evidence(self):
        for change in (
            {"doc":"https://evil.example/media/2026/10/09/kotirovka_sorusu___-mtb.docx"},
            {"doc":"http://adif.gov.az/media/2026/10/09/kotirovka_sorusu___-mtb.docx"},
            {"doc":"https://adif.gov.az/media/2026/05/13/kotirovka_sorusu___-mtb.docx"},
            {"doc":"https://adif.gov.az/media/2026/10/09/kotirovka_sorusu___-mtb.docx?token=abc"},
            {"deadline":"01 oktyabr 2026-cı il saat 12:00-dək"},
            {"deadline":"99 oktyabr 2026-cı il saat 12:00-dək"},
            {"date_value":"32.10.2026"},
        ):
            with self.subTest(change=change),self.assertRaises(SourceError):
                parse_public_articles(fixture(**change),today=date(2026,10,18))
        with self.assertRaises(SourceError):
            parse_public_articles(fixture()+fixture(),today=date(2026,10,18))
        with self.assertRaises(SourceError):
            parse_public_articles("<script>"+fixture()+"</script>",today=date(2026,10,18))

    def test_stale_notices_are_not_falsely_active(self):
        with self.assertRaises(SourceError):
            parse_public_articles(fixture(),today=date(2026,10,20))
        with self.assertRaises(SourceError):
            parse_public_articles(fixture(date_value="02.10.2028"),today=date(2026,10,18))

    def test_disabled_first_party_catalog_and_worker_host(self):
        cfg=MonitoringSettings(False,600,20,5,12,(),None)
        r=build_source_catalog(cfg).registry.get(SOURCE)
        self.assertTrue(r.official)
        self.assertFalse(r.enabled)
        self.assertEqual(r.jurisdictions,("AZ",))
        self.assertEqual(r.homepage_url,URL)
        self.assertEqual(HOSTS[SOURCE],frozenset({"adif.gov.az"}))
        self.assertEqual(MAX_RESULTS,5)

if __name__=="__main__":
    unittest.main()
