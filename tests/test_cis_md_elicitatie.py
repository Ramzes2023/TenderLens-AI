"""Strict offline e-Licitație card/detail, buyer, amount, deadline and host contracts.

Synthetic fixtures are not proof of upstream connectivity. Hosted live leased
worker -> disposable SQLite -> saved-search acceptance must pass separately.
"""
import unittest

from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.eis_rss import SourceError
from app.sources.ingestion import HOSTS
from app.sources.md_elicitatie import (
    HOST, INDEX_URL, MAX_CANDIDATES, MAX_DETAILS, discover_index,
    parse_marketplace_detail,
)

URL = "https://e-licitatie.md/achizitii/101527/reparatia-strazii-molodaa-gvardia"
TITLE = 'Reparația străzii „Молодая Гвардия” și „Советская”'
DETAIL = f"""<html>
<script>ocds-b3wdp1-MD-0000000000000</script>
<h1>Achiziție - {TITLE}</h1>
<h2>Achiziție Primaria Troitcoe</h2>
<h3>Informație generală</h3>
<a href="/beneficiari">Primaria Troitcoe</a>
<div>1007601011478</div><div>{TITLE}</div>
<div>421,990.09 MDL</div><div>perioada de clarificari</div>
<div>ocds-b3wdp1-MD-1792159067210</div>
<div>{TITLE}</div><div>COP</div>
<div>publicată</div><div>17/10/2026 10:27</div>
<div>clarificări</div><div>21/10/2026 11:30</div>
<div>depunere</div><div>30/10/2026 11:30</div>
<h3>Surse de finanțare</h3><div>421,990.09 MDL</div>
</html>"""


class MoldovaELicitatieContracts(unittest.TestCase):
    def test_public_cards_and_normalized_detail(self):
        html = ('<script><a href="/achizitii/12345/evil">Fake tender</a></script>'
                f'<h3><a href="/achizitii/101527/reparatia-strazii-molodaa-gvardia">{TITLE}</a></h3>'
                '<h3><a href="/achizitii/101521/drumuri-municipiul-cahul">'
                'Lucrari de reparatie drumurilor Cahul</a></h3>')
        cards = discover_index(html)
        self.assertEqual(len(cards), 2)
        notice = parse_marketplace_detail(DETAIL, url=URL, expected_title=TITLE)
        self.assertEqual(notice.source, 'md_elicitatie')
        self.assertEqual(notice.external_id, 'ocds-b3wdp1-MD-1792159067210')
        self.assertEqual(notice.customer, 'Primaria Troitcoe')
        self.assertEqual(notice.initial_price, 421990.09)
        self.assertEqual(notice.currency, 'MDL')
        self.assertEqual(notice.published_at, '2026-10-17T10:27:00')
        self.assertEqual(notice.deadline, '2026-10-30T11:30:00')

    def test_bad_buyer_amount_id_deadline_and_title_fail_closed(self):
        for old, new in (
            ('<h2>Achiziție Primaria Troitcoe</h2>', '<h2>Unclear buyer</h2>'),
            ('421,990.09 MDL', 'unknown USD'),
            ('ocds-b3wdp1-MD-1792159067210', 'not-an-ocid'),
            ('30/10/2026 11:30', '01/10/2020 11:30'),
            ('<h3>Surse de finanțare</h3>', '<h3>Missing footer</h3>'),
        ):
            with self.subTest(old=old), self.assertRaises(SourceError):
                parse_marketplace_detail(DETAIL.replace(old, new), url=URL, expected_title=TITLE)
        with self.assertRaises(SourceError):
            parse_marketplace_detail(DETAIL, url=URL, expected_title='Incorrect indexed title')
        for url in (URL.replace('https:', 'http:'),
                    URL.replace('e-licitatie.md', 'evil.example'),
                    URL + '?token=secret'):
            with self.subTest(url=url), self.assertRaises(SourceError):
                parse_marketplace_detail(DETAIL, url=url, expected_title=TITLE)

    def test_javascript_only_and_foreign_hosts_never_qualify(self):
        for bad in ('<script><a href="/achizitii/101527/notice">Fake tender title</a></script>',
                    '<a href="https://evil.example/achizitii/101527/notice">Fake tender title</a>',
                    '<a href="http://e-licitatie.md/achizitii/101527/notice">Fake tender title</a>'):
            with self.subTest(bad=bad), self.assertRaises(SourceError):
                discover_index(bad)

    def test_catalog_stays_disabled_and_host_request_budget_is_pinned(self):
        config = MonitoringSettings(False, 600, 20, 5, 12, (), None)
        entry = build_source_catalog(config).registry.get('md_elicitatie')
        self.assertFalse(entry.official)
        self.assertFalse(entry.enabled)
        self.assertEqual(entry.jurisdictions, ('MD',))
        self.assertEqual(HOSTS['md_elicitatie'], frozenset({HOST}))
        self.assertEqual(MAX_DETAILS, 5)
        self.assertEqual(MAX_CANDIDATES, 10)
        self.assertEqual(INDEX_URL, 'https://e-licitatie.md/achizitii')


if __name__ == '__main__':
    unittest.main()
