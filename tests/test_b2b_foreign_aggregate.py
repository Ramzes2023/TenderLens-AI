"""Mixed public B2B aggregate: strictly ignore known non-B2B source cards."""
from pathlib import Path

import pytest

from app.sources.b2b_center import parse_b2b_center_listing
from app.sources.eis_rss import SourceError

ORIGINAL_AGGREGATE = (Path(__file__).parent / "fixtures" / "ru08" / "b2b_search.html").read_bytes()

# Explicitly synthetic first-party-shaped input for OFFLINE contracts only.
# The original capture contains foreign aggregate records, never live proof.
CAPTURE = (b'<html><div class="cards" itemtype="https://schema.org/ListItem">'
           b'<div itemtype="https://schema.org/Demand">'
           b'<meta itemprop="businessFunction" content="http://purl.org/goodrelations/v1#Buy">'
           b'<link itemprop="url" href="https://www.b2b-center.ru/search/number/99999999/">'
           b'<meta itemprop="name" content="Synthetic offline office supplies">'
           b'<a href="https://www.b2b-center.ru/market/synthetic/tender-99999999/">'
           b'&#1047;&#1072;&#1082;&#1091;&#1087;&#1082;&#1072; &#8470;99999999</a>'
           b'</div></div></html>')



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
    assert len(baseline) == len(mixed) == 1
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
        '<link itemprop="url" href="https://www.b2b-center.ru/search/number/88888888/">'
        '<meta itemprop="name" content="Тестовая поставка: карточка без указанного заказчика">'
        '<a href="https://www.b2b-center.ru/market/synthetic/tender-88888888/">'
        '&#1047;&#1072;&#1082;&#1091;&#1087;&#1082;&#1072; &#8470;88888888</a></div></div>'
    ).encode("utf-8")
    notices = parse_b2b_center_listing(inject_inside_listing(fragment), limit=100)
    found = [n for n in notices if n.external_id == "88888888"]
    assert len(found) == 1
    assert found[0].customer is None
    assert len(notices) == 2


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


def test_original_aggregate_capture_cannot_be_claimed_as_b2b():
    records = parse_b2b_center_listing(ORIGINAL_AGGREGATE)
    assert [n.external_id for n in records] == ["l4639392-4-12-1"]
    assert records[0].origin == "first_party"
    assert records[0].tender_number == "4639392"


@pytest.mark.parametrize('native_url', [
    b'http://www.b2b-center.ru/market/synthetic/tender-99999999/',
    b'https://www.b2b-center.ru.evil.invalid/market/synthetic/tender-99999999/',
    b'https://www.b2b-center.ru/market/synthetic/tender-99999999/?tracking=1',
    b'https://www.b2b-center.ru/market/synthetic/tender-99999998/',
    b'https://www.b2b-center.ru/market/synthetic/tender-99999999/#tracking',
])
def test_native_ownership_requires_exact_https_procedure_and_matching_number(native_url):
    payload = CAPTURE.replace(
        b'https://www.b2b-center.ru/market/synthetic/tender-99999999/', native_url)
    with pytest.raises(SourceError, match='no usable'):
        parse_b2b_center_listing(payload)


@pytest.mark.parametrize("suffix", ["", "#tracking"])
def test_optional_foreign_provenance_cannot_be_erased(suffix):
    reference = ('<a href="https://zakupki.gov.ru/notice' + suffix +
                 '">&#1047;&#1072;&#1082;&#1091;&#1087;&#1082;&#1072; &#8470;123</a>').encode()
    start = CAPTURE.index(b'<a '); end = CAPTURE.index(b'</a>', start) + 4
    payload = CAPTURE[:start] + reference + CAPTURE[end:]
    with pytest.raises(SourceError, match="no usable"):
        parse_b2b_center_listing(payload)


@pytest.mark.parametrize("external_id", ["l123-1", "l0338200012226000019-1"])
def test_unproven_aggregate_identity_without_provenance_is_not_native(external_id):
    with pytest.raises(SourceError, match="no usable"):
        parse_b2b_center_listing(CAPTURE.replace(b'number/99999999/', b'number/' + external_id.encode() + b'/'))


def test_bounded_b2b_office_fallback_is_real_provenance_not_full_coverage(monkeypatch):
    """Fallback only for a bounded response-size failure."""
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
        from httpx import Cookies
        cookies = Cookies()
        async def get(self, url):
            calls.append(url)
            if url == B2B_CENTER_LIST_URL:
                raise ConnectorTransportError(reason="response_size")
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
    notices = asyncio.run(B2BCenterSource(listing_url=B2B_CENTER_LIST_URL).fetch(limit=2))
    assert calls == [B2B_CENTER_LIST_URL, B2B_CENTER_OFFICE_LIST_URL]
    assert len(notices) == 1
    for notice in notices:
        assert notice.listing_url == B2B_CENTER_OFFICE_LIST_URL
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
        asyncio.run(B2BCenterSource(listing_url=B2B_CENTER_LIST_URL).fetch(limit=2))
    assert exc.value.retryable is True


def test_unapproved_listing_origin_cannot_be_injected():
    from app.sources.b2b_center import parse_b2b_center_listing
    with pytest.raises(SourceError, match="Unapproved"):
        parse_b2b_center_listing(CAPTURE, listing_url="https://attacker.invalid/list")
