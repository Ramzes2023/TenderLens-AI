"""Real Worker URL acceptance contract (offline inputs; no fake live PASS)."""
from app.sources.models import TenderNotice
from scripts.ci_ru_b2b_real_worker import _verified_b2b_public_url


def test_new_first_party_url_must_match_original_number():
    url = 'https://www.b2b-center.ru/app/market-next/slug/tender-4646931/'
    n = TenderNotice('b2b_center', '4646931', 'Original test', url,
                     tender_number='4646931')
    assert _verified_b2b_public_url(n)
    assert not _verified_b2b_public_url(TenderNotice(
        'b2b_center', '4646932', 'Different number', url, tender_number='4646932'))
    assert not _verified_b2b_public_url(TenderNotice(
        'b2b_center', '4646931', 'Wrong number field', url, tender_number='4646932'))


def test_legacy_search_number_is_kept_strict():
    url = 'https://www.b2b-center.ru/search/number/l4646931-4-12-1/'
    n = TenderNotice('b2b_center', 'l4646931-4-12-1', 'Original legacy', url)
    assert _verified_b2b_public_url(n)
    assert not _verified_b2b_public_url(TenderNotice('b2b_center', 'wrong', 'Wrong', url))


def test_new_first_party_rejects_noncanonical_or_foreign_urls():
    for url in (
        'https://www.b2b-center.ru.evil.invalid/app/market-next/slug/tender-4646931/',
        'http://www.b2b-center.ru/app/market-next/slug/tender-4646931/',
        'https://www.b2b-center.ru/app/market-next/slug/tender-4646931/?token=1',
        'https://www.b2b-center.ru/app/market-next/slug/tender-4646931/#unknown',
        'https://www.b2b-center.ru/app/market-next/slug/tender-4646932/',
    ):
        assert not _verified_b2b_public_url(TenderNotice(
            'b2b_center', '4646931', 'Untrusted', url, tender_number='4646931'))