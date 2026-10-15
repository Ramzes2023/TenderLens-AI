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
