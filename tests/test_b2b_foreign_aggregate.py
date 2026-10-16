"""Mixed public B2B aggregate: strictly ignore known non-B2B source cards."""
from pathlib import Path

import pytest

from app.sources.b2b_center import parse_b2b_center_listing
from app.sources.eis_rss import SourceError

CAPTURE = (Path(__file__).parent / "fixtures" / "ru08" / "b2b_search.html").read_bytes()


def extra_card(host, *, duplicate_organization=False):
    organization = '<div itemtype="https://schema.org/Organization"></div>'
    if duplicate_organization:
        organization *= 2
    return (f'<div class="cards" itemtype="https://schema.org/ListItem">'
            f'{organization}'
            f'<div itemtype="https://schema.org/Demand">'
            f'<meta itemprop="businessFunction" content="http://purl.org/goodrelations/v1#Buy">'
            f'<link itemprop="url" href="https://{host}/notices/other-platform">'
            f'</div></div>').encode("utf-8")


def inject_inside_listing(card):
    # Put synthetic card *before* an existing procurement card, not after
    # the closing HTML root (which HTMLParser may legally ignore).
    marker = CAPTURE.find(b'class="cards"')
    assert marker > 0, "Capture no longer has a procurement card"
    start = CAPTURE.rfind(b'<div', 0, marker)
    assert start > 0
    return CAPTURE[:start] + card + CAPTURE[start:]


@pytest.mark.parametrize("host", [
    "www.rosatom.rts-tender.ru", "www.rts-tender.ru",
    "otc.ru", "www.otc.ru", "zakupki.gov.ru",
])
@pytest.mark.parametrize("ambiguous", [False, True])
def test_known_external_aggregator_cards_never_become_b2b_notices(host, ambiguous):
    baseline = parse_b2b_center_listing(CAPTURE, limit=100)
    mixed = parse_b2b_center_listing(
        inject_inside_listing(extra_card(host, duplicate_organization=ambiguous)), limit=100
    )
    assert len(baseline) == len(mixed) == 10
    assert [notice.identity for notice in baseline] == [notice.identity for notice in mixed]


@pytest.mark.parametrize("host", [
    "evil.invalid", "www.b2b-center.ru.evil.invalid", "rts-tender.ru.evil.invalid",
])
def test_unrecognized_hosts_still_fail_closed(host):
    with pytest.raises(SourceError):
        parse_b2b_center_listing(inject_inside_listing(extra_card(host)))


def test_foreign_only_page_is_not_reported_as_success():
    with pytest.raises(SourceError, match="no usable"):
        parse_b2b_center_listing(extra_card("www.rts-tender.ru"))


def test_valid_b2b_card_without_optional_organization_is_not_fabricated():
    fragment = (
        '<div class="cards" itemtype="https://schema.org/ListItem">'
        '<div itemtype="https://schema.org/Demand">'
        '<meta itemprop="businessFunction" content="http://purl.org/goodrelations/v1#Buy">'
        '<link itemprop="url" href="https://www.b2b-center.ru/search/number/l99999999-1/">'
        '<meta itemprop="name" content="Тестовая поставка: карточка без указанного заказчика">'
        '</div></div>'
    ).encode("utf-8")
    notices = parse_b2b_center_listing(inject_inside_listing(fragment), limit=100)
    found = [n for n in notices if n.external_id == "l99999999-1"]
    assert len(found) == 1
    assert found[0].customer is None
    assert len(notices) == 11


def test_multiple_b2b_organizations_remain_rejected():
    fragment = (
        '<div class="cards" itemtype="https://schema.org/ListItem">'
        '<div itemtype="https://schema.org/Organization"></div>'
        '<div itemtype="https://schema.org/Organization"></div>'
        '<div itemtype="https://schema.org/Demand">'
        '<meta itemprop="businessFunction" content="http://purl.org/goodrelations/v1#Buy">'
        '<link itemprop="url" href="https://www.b2b-center.ru/search/number/l88888888-1/">'
        '<meta itemprop="name" content="Ambiguous buyer">'
        '</div></div>'
    ).encode("utf-8")
    with pytest.raises(SourceError, match="structure"):
        parse_b2b_center_listing(inject_inside_listing(fragment), limit=100)


def test_optional_cross_platform_url_fragment_does_not_drop_genuine_b2b_notice():
    # A third-party URL containing a fragment is not a verified source link.
    needle = b'?regNumber=0338200012226000019"'
    assert CAPTURE.count(needle) == 1
    mutated = CAPTURE.replace(needle, b'?regNumber=0338200012226000019#tracking"', 1)
    records = parse_b2b_center_listing(mutated, limit=100)
    assert len(records) == 10
    notice = next(n for n in records if n.external_id == "l0338200012226000019-1")
    assert notice.url == (
        "https://www.b2b-center.ru/search/number/l0338200012226000019-1/"
    )
    assert notice.upstream_url is None
    assert notice.tender_number is None


def test_bounded_b2b_office_fallback_is_real_provenance_not_full_coverage(monkeypatch):
    """Fallback only when unrestricted listing transport fails non-retryably."""
    import asyncio
    import json
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from app.sources.b2b_center import (
        B2B_CENTER_LIST_URL, B2B_CENTER_OFFICE_LIST_URL, B2BCenterSource,
    )
    from app.sources.http import ConnectorTransportError, _policy
    import app.sources.b2b_center as module

    calls = []

    class Client:
        async def get(self, url):
            calls.append(url)
            if url == B2B_CENTER_LIST_URL:
                raise ConnectorTransportError(retryable=False)
            assert url == B2B_CENTER_OFFICE_LIST_URL
            return SimpleNamespace(content=CAPTURE, status_code=200,
                                   raise_for_status=lambda: None)

    @asynccontextmanager
    async def client(**kwargs):
        assert not kwargs["follow_redirects"]
        assert not kwargs["trust_env"]
        assert _policy.get().hosts == frozenset({"www.b2b-center.ru"})
        assert _policy.get().max_requests == 2
        assert _policy.get().max_bytes == module.MAX_BYTES
        yield Client()

    monkeypatch.setattr(module, "source_client", client)
    notices = asyncio.run(B2BCenterSource().fetch(limit=2))
    assert calls == [B2B_CENTER_LIST_URL, B2B_CENTER_OFFICE_LIST_URL]
    assert len(notices) == 2
    for notice in notices:
        metadata = json.loads(notice.summary)
        assert metadata["listing_url"] == B2B_CENTER_OFFICE_LIST_URL
        assert metadata["coverage_scope"] == "office_only"
        assert notice.url.startswith("https://www.b2b-center.ru/search/number/")


def test_retryable_b2b_error_not_masked_by_fallback(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    from app.sources.b2b_center import B2B_CENTER_LIST_URL, B2BCenterSource
    from app.sources.http import ConnectorTransportError
    import app.sources.b2b_center as module

    class Client:
        async def get(self, url):
            assert url == B2B_CENTER_LIST_URL
            raise ConnectorTransportError(retryable=True)

    @asynccontextmanager
    async def client(**kwargs):
        yield Client()

    monkeypatch.setattr(module, "source_client", client)
    with pytest.raises(ConnectorTransportError) as exc:
        asyncio.run(B2BCenterSource().fetch(limit=2))
    assert exc.value.retryable is True


def test_unapproved_listing_origin_cannot_be_injected():
    from app.sources.b2b_center import parse_b2b_center_listing
    with pytest.raises(SourceError, match="Unapproved"):
        parse_b2b_center_listing(CAPTURE, listing_url="https://attacker.invalid/list")
