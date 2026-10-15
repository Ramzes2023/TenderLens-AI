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
    assert MAX_DETAIL_REQUESTS == 6
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


@pytest.mark.parametrize("statuses,failures,expected", [
    ([404, 404], ["CONNECTOR_TRANSPORT"], "OFFICIAL_DETAIL_HTTP_404"),
    ([404, 200], ["CONNECTOR_TRANSPORT"], "SOME_OFFICIAL_DETAILS_HTTP_404"),
    ([302], ["CONNECTOR_TRANSPORT"], "REDIRECT_NOT_FOLLOWED"),
    ([403], ["CONNECTOR_TRANSPORT"], "ACCESS_RESTRICTED"),
    ([429], ["CONNECTOR_TRANSPORT"], "REMOTE_RATE_LIMIT_OR_SERVER_ERROR"),
    ([503], ["CONNECTOR_TRANSPORT"], "REMOTE_RATE_LIMIT_OR_SERVER_ERROR"),
    ([200], ["CONNECTOR_TRANSPORT"], "HTTP_TRANSPORT_OR_BODY_FAILURE"),
    ([200], [], "HTML_CONTENT_OR_NUMBER_MISMATCH"),
    ([], ["ConnectTimeout"], "HTTP_TRANSPORT_OR_BODY_FAILURE"),
    ([], [], "NO_HTTP_RESPONSE_OBSERVED"),
])
def test_detail_status_outcome_is_classified_without_unsafe_data(
    statuses, failures, expected
):
    from scripts.ci_ru_eis_detail_identity import detail_blocker

    record = {"statuses": statuses, "failures": failures, "verified": 0}
    assert detail_blocker(record) == expected
    record["verified"] = 1
    assert detail_blocker(record) is None


def test_detail_failure_codes_exclude_exception_messages_and_urls():
    from app.sources.http import ConnectorTransportError
    from scripts.ci_ru_eis_detail_identity import detail_failure_code

    assert detail_failure_code(ConnectorTransportError()) == "CONNECTOR_TRANSPORT"
    secret = "https://zakupki.gov.ru/secret?id=0123456789012"
    assert detail_failure_code(RuntimeError(secret)) == "OTHER_FAILURE"
    assert secret not in detail_failure_code(RuntimeError(secret))
    assert detail_failure_code(TimeoutError(secret)) == "TimeoutError"


def test_diverse_44fz_routes_checked_before_repeated_ea20():
    from scripts.ci_ru_eis_detail_identity import (
        select_diverse_routes, MAX_DETAIL_REQUESTS,
    )

    def route(name, number):
        return (f"https://zakupki.gov.ru/epz/order/notice/{name}/view/"
                f"common-info.html?regNumber={number}", number)

    items = [
        route("ea20", "0123456789012"),
        route("ea20", "0123456789013"),
        route("zk20", "0123456789014"),
        route("ea20", "0123456789015"),
        route("ok20", "0123456789016"),
        route("zk20", "0123456789017"),
        route("ea20", "0123456789018"),
    ]
    sample = select_diverse_routes(items)
    assert len(sample) == MAX_DETAIL_REQUESTS == 6
    assert [url.split("/notice/")[1].split("/")[0]
            for url, _ in sample[:3]] == ["ea20", "zk20", "ok20"]
    assert sample[3:] == [items[1], items[3], items[5]]


def test_223fz_sample_keeps_original_rss_urls_and_respects_request_limit():
    from scripts.ci_ru_eis_detail_identity import (
        select_diverse_routes, MAX_DETAIL_REQUESTS,
    )
    items = [
        (f"https://zakupki.gov.ru/223/purchase/public/purchase/info/"
         f"common-info.html?regNumber={i:013d}", str(i))
        for i in range(1, 11)
    ]
    assert select_diverse_routes(items) == items[:MAX_DETAIL_REQUESTS]
    assert select_diverse_routes(items, limit=0) == []


@pytest.mark.parametrize("location,expected_target,expected_path,expected_number", [
    ("https://zakupki.gov.ru/223/purchase/public/purchase/info/common-info.html?regNumber=0123456789012",
     "EXACT_OFFICIAL_HTTPS_HOST",
     "/223/purchase/public/purchase/info/common-info.html", "MATCH"),
    ("/223/purchase/public/purchase/info/common-info.html?regNumber=0123456789012",
     "EXACT_OFFICIAL_HTTPS_HOST",
     "/223/purchase/public/purchase/info/common-info.html", "MATCH"),
    ("/223/purchase/public/purchase/info/common-info.html?regNumber=9999999999999",
     "EXACT_OFFICIAL_HTTPS_HOST",
     "/223/purchase/public/purchase/info/common-info.html", "MISMATCH"),
    ("/223/purchase/public/purchase/info/common-info.html?foo=bar",
     "EXACT_OFFICIAL_HTTPS_HOST",
     "/223/purchase/public/purchase/info/common-info.html", "NOT_IN_RECOGNIZED_QUERY"),
    ("https://example.invalid/private?id=0123456789012",
     "NOT_EXACT_OFFICIAL_HTTPS_HOST", "REDACTED", "UNKNOWN"),
    ("https://zakupki.gov.ru.evil.invalid/223/purchase/public/purchase/info/common-info.html",
     "NOT_EXACT_OFFICIAL_HTTPS_HOST", "REDACTED", "UNKNOWN"),
    ("https://evil@zakupki.gov.ru/223/purchase/public/purchase/info/common-info.html",
     "NOT_EXACT_OFFICIAL_HTTPS_HOST", "REDACTED", "UNKNOWN"),
    ("http://zakupki.gov.ru/223/purchase/public/purchase/info/common-info.html",
     "NOT_EXACT_OFFICIAL_HTTPS_HOST", "REDACTED", "UNKNOWN"),
    ("/223/purchase/private/0123456789012/secret",
     "EXACT_OFFICIAL_HTTPS_HOST", "/223/purchase/private/{ID}/secret", "NOT_IN_RECOGNIZED_QUERY"),
    ("https://zakupki.gov.ru/223/purchase/public/purchase/info/common-info.html#fragment",
     "NOT_EXACT_OFFICIAL_HTTPS_HOST", "REDACTED", "UNKNOWN"),
    (None, "UNSAFE_OR_MISSING", "REDACTED", "UNKNOWN"),
    ("https://zakupki.gov.ru/\nsecret", "UNSAFE_OR_MISSING", "REDACTED", "UNKNOWN"),
])
def test_223_redirect_shape_is_safe_and_number_is_never_logged(
        location, expected_target, expected_path, expected_number):
    from scripts.ci_ru_eis_detail_identity import describe_redirect_target

    origin = ("https://zakupki.gov.ru/223/purchase/public/purchase/info/"
              "common-info.html?regNumber=0123456789012")
    observed = describe_redirect_target(origin, location, "0123456789012")
    assert observed == {"target": expected_target, "path_shape": expected_path,
                        "number": expected_number}
    assert "0123456789012" not in str(observed)
    assert "9999999999999" not in str(observed)
    assert "evil.invalid" not in str(observed)


def test_223_redirect_duplicate_or_malformed_number_cannot_match():
    from scripts.ci_ru_eis_detail_identity import describe_redirect_target
    origin = ("https://zakupki.gov.ru/223/purchase/public/purchase/info/"
              "common-info.html?regNumber=0123456789012")
    target = ("https://zakupki.gov.ru/223/purchase/public/purchase/info/"
              "common-info.html?regNumber=0123456789012&regNumber=0123456789012")
    assert describe_redirect_target(origin, target, "0123456789012")["number"] == "AMBIGUOUS"
