"""Synthetic OFFLINE route discovery; never proof of public cards."""
import pytest

from scripts.research_ru_samara_disclosed_notice_route import (
    DETAIL_PREFIX, detail_url_from_original_native_link, disclosed_notice_contract,
)


def test_declared_fixed_original_route_must_exist_on_first_party_markup():
    assert disclosed_notice_contract(
        b'<html><script>window.open("/smallpurchases/GzwSP/Notice?noticeLink=" + id)</script></html>'
    )
    assert disclosed_notice_contract(
        b'<script>var noticeLink=key; var path="/smallpurchases/GzwSP/Notice";</script>'
    )


@pytest.mark.parametrize("markup", [
    b"", b"<html>Nothing</html>",
    b'<script src="/smallpurchases/GzwSP/Notice?noticeLink=123"></script>',
    b'<html><script>var p="/smallpurchases/GzwSP/Notice";</script></html>',
    b'<html><script>noticeLink=1;</script></html>',
    b'<html><script>"/smallpurchases/GzwSP/Notice";' + b"x" * 1500 + b'noticeLink</script></html>',
])
def test_unpublished_or_nonlocal_route_cannot_be_assumed(markup):
    if markup:
        assert disclosed_notice_contract(markup) is False
    else:
        with pytest.raises(ValueError):
            disclosed_notice_contract(markup)


def test_only_exact_live_numeric_listing_reference_can_supply_notice_link():
    first = "https://webtorgi.samregion.ru/smallpurchases/GzwSP/5611196"
    assert detail_url_from_original_native_link(first) == DETAIL_PREFIX + "5611196"
    assert DETAIL_PREFIX.startswith("https://webtorgi.samregion.ru/")


@pytest.mark.parametrize("value", [
    None, "",
    "http://webtorgi.samregion.ru/smallpurchases/GzwSP/5611196",
    "https://evil.invalid/smallpurchases/GzwSP/5611196",
    "https://webtorgi.samregion.ru/smallpurchases/GzwSP/NoticesGrid",
    "https://webtorgi.samregion.ru/smallpurchases/GzwSP/5611196?token=x",
    "https://webtorgi.samregion.ru/smallpurchases/GzwSP/5611196#x",
    "https://webtorgi.samregion.ru/smallpurchases/GzwSP/../login",
])
def test_no_external_untrusted_or_guessed_detail_ids(value):
    with pytest.raises(ValueError):
        detail_url_from_original_native_link(value)
