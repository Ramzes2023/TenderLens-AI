"""Offline guards for independent real EIS detail verification."""
from types import SimpleNamespace

import pytest

from scripts.ci_ru_eis_detail_identity import (
    SOURCES, MAX_DETAIL_REQUESTS, detail_candidate, detail_page_has_identity,
)


def notice(source="eis", url=None, number="0123456789012"):
    return SimpleNamespace(
        source=source, tender_number=number,
        url=url or ("https://zakupki.gov.ru/epz/order/notice/"
                    "view/common-info.html?regNumber=0123456789012"),
    )


def test_exact_official_44_and_223_identity_candidates():
    assert SOURCES == ("eis", "eis_223")
    assert MAX_DETAIL_REQUESTS == 2
    assert detail_candidate(notice(), "eis")[1] == "0123456789012"
    n = notice(source="eis_223", number=None,
               url=("https://zakupki.gov.ru/223/purchase/public/purchase/"
                    "info/common-info.html?regNumber=0123456789012"))
    assert detail_candidate(n, "eis_223")[1] == "0123456789012"


@pytest.mark.parametrize("url", [
    "http://zakupki.gov.ru/epz/order/notice/view?regNumber=0123456789012",
    "https://evil.invalid/epz/order/notice/view?regNumber=0123456789012",
    "https://zakupki.gov.ru.evil.invalid/epz/order/notice/view?regNumber=0123456789012",
    "https://user@zakupki.gov.ru/epz/order/notice/view?regNumber=0123456789012",
    "https://zakupki.gov.ru:444/epz/order/notice/view?regNumber=0123456789012",
    "https://zakupki.gov.ru/epz/order/notice/view#fragment",
    "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html",
    "https://zakupki.gov.ru/internal/notice?regNumber=0123456789012",
])
def test_unsafe_or_wrong_resource_url_rejected(url):
    with pytest.raises(ValueError):
        detail_candidate(notice(url=url), "eis")


def test_cross_source_identity_is_refused():
    with pytest.raises(ValueError, match="WRONG_SOURCE"):
        detail_candidate(notice(source="eis_223"), "eis")


def test_ambiguous_numbers_not_falsely_verified():
    n = notice(url=("https://zakupki.gov.ru/223/purchase/public/purchase/info/"
                    "common-info.html?regNumber=9999999999999"))
    with pytest.raises(ValueError, match="AMBIGUOUS"):
        detail_candidate(n, "eis")


def test_missing_stable_number_not_a_verified_detail():
    n = notice(number=None, url="https://zakupki.gov.ru/epz/order/notice/view/common-info.html")
    with pytest.raises(ValueError, match="NUMBER_NOT_AVAILABLE"):
        detail_candidate(n, "eis")


def test_independent_html_number_must_match_exactly():
    number = "0123456789012"
    html = ("<html><body>Извещение о закупке № " + number + "</body></html>").encode()
    assert detail_page_has_identity(html, number, "text/html; charset=utf-8")
    assert not detail_page_has_identity(html.replace(number.encode(), b"8888888888888"),
                                        number, "text/html")
    assert not detail_page_has_identity(html, number, "application/xml")
    assert not detail_page_has_identity(
        ("<html>captcha " + number + "</html>").encode(), number, "text/html"
    )
    assert not detail_page_has_identity(
        ("<html>" + number + "8</html>").encode(), number, "text/html"
    )


def test_no_detail_proof_from_rss_or_empty_body():
    number = "0123456789012"
    assert not detail_page_has_identity(b"", number, "text/html")
    assert not detail_page_has_identity(
        ("<rss><item>" + number + "</item></rss>").encode(), number, "application/rss+xml"
    )
