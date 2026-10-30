"""No upstream mock can be treated as live; strict HTML evidence parser contracts."""
from dataclasses import dataclass, replace
from datetime import datetime, timezone

import pytest

from app.sources.eis_official_detail_deadline import verified_detail_deadline


@dataclass
class Notice:
    source: str
    tender_number: str
    external_id: str
    url: str


N44 = "0316300145126000012"
N223 = "32616521305"
NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


def n(source="eis"):
    num = N44 if source == "eis" else N223
    path = ("/epz/order/notice/ea44/view/common-info.html"
            if source == "eis" else
            "/223/purchase/public/purchase/info/common-info.html")
    return Notice(source, num, num,
                  "https://zakupki.gov.ru" + path + "?regNumber=" + num)


def html(number, due="10.12.2026 19:45", label="Дата и время окончания подачи заявок"):
    return (
        "<!doctype html><html><head><title>ЕИС</title></head><body>"
        "<h1>Извещение об осуществлении закупки</h1>"
        "<p>Реестровый номер закупки: " + number + "</p>"
        "<div>" + label + ": " + due + "</div>"
        "</body></html>"
    ).encode("utf-8")


@pytest.mark.parametrize("law", ("eis", "eis_223"))
def test_verified_original_explicit_current_bid_deadline(law):
    assert verified_detail_deadline(n(law), html(n(law).tender_number), now=NOW) == "10.12.2026 19:45"


@pytest.mark.parametrize("law", ("eis", "eis_223"))
def test_number_must_be_visible_body_not_script_attribute_or_other_notice(law):
    item = n(law)
    other = "32616521305" if law == "eis" else N44
    assert verified_detail_deadline(item, html(other), now=NOW) is None
    injected = (
        '<html><body><script>Реестровый номер закупки: ' + item.tender_number
        + '</script><div>Окончание подачи заявок: 10.12.2026 19:45</div></body></html>'
    ).encode("utf-8")
    assert verified_detail_deadline(item, injected, now=NOW) is None
    attribute = (
        '<html><body><div data-number="Реестровый номер закупки: ' + item.tender_number
        + '">Окончание подачи заявок: 10.12.2026 19:45</div></body></html>'
    ).encode("utf-8")
    assert verified_detail_deadline(item, attribute, now=NOW) is None


@pytest.mark.parametrize("law", ("eis", "eis_223"))
def test_rejects_expired_invalid_and_conflicting_closing_clocks(law):
    item = n(law)
    for due in ("01.01.2026 09:00", "30.10.2026 14:00", "31.02.2027 13:00"):
        assert verified_detail_deadline(item, html(item.tender_number, due=due), now=NOW) is None
    two = html(item.tender_number).replace(
        b"</body>",
        "<p>Окончание подачи заявок: 11.12.2026 13:00</p></body>".encode(),
    )
    assert verified_detail_deadline(item, two, now=NOW) is None
    no_clock = html(item.tender_number, label="Дата публикации")
    assert verified_detail_deadline(item, no_clock, now=NOW) is None


@pytest.mark.parametrize("law", ("eis", "eis_223"))
def test_rejects_foreign_original_and_non_html(law):
    item = n(law)
    forged = replace(item, url=item.url.replace("zakupki.gov.ru", "invalid.example"))
    assert verified_detail_deadline(forged, html(item.tender_number), now=NOW) is None
    wrong_law = replace(item, source="eis_223" if law == "eis" else "eis")
    assert verified_detail_deadline(wrong_law, html(item.tender_number), now=NOW) is None
    assert verified_detail_deadline(item, b"", now=NOW) is None
    assert verified_detail_deadline(item, b"<rss></rss>", now=NOW) is None
    assert verified_detail_deadline(item, b"\x00", now=NOW) is None
    assert verified_detail_deadline(item, b"x" * 1_200_001, now=NOW) is None


def test_rejects_unaware_check_clock():
    with pytest.raises(ValueError, match="Aware"):
        verified_detail_deadline(n(), html(N44), now=datetime(2026, 10, 30))


def test_does_not_invent_clock_from_publication_date():
    item = n()
    body = (
        "<html><body>№ " + item.tender_number
        + " Дата публикации: 10.12.2026 19:45"
        + "</body></html>"
    ).encode()
    assert verified_detail_deadline(item, body, now=NOW) is None
