"""Session-safe Indian ePublishing official real-tender contracts (offline)."""
import asyncio
from datetime import datetime, timedelta, timezone
from html import escape

import pytest

from app.sources.india_epublish import (
    SOURCE_ID, LIST_URL, IndiaEpublishSource, parse_epublish_latest,
)
from app.sources.eis_rss import SourceError
from app.sources.opportunities import validate_notice

IST=timezone(timedelta(hours=5,minutes=30))
DATE=datetime(2026,10,17,14,tzinfo=IST)
LINK=("https://eprocure.gov.in/epublish/app?component=%24DirectLink"
      "&page=Home&service=direct&session=ABCD1234&sp=ZXCVB1234")


def fixture(href=LINK, title="Procurement of 65 laptops",
            ref="GEM/2026/B/8172809", close="30-Oct-2026 06:00 PM",
            open_time="31-Oct-2026 12:00 PM", section="Latest Tenders"):
    return (("<html><img alt='"+section+"'/>Tender Title Reference No"
             "<table><tr><td><a href='"+escape(href,quote=True)+"'>1. "+
             escape(title)+"</a></td><td>"+escape(ref)+"</td><td>"+
             escape(close)+"</td><td>"+escape(open_time)+"</td></tr></table>"
             '<img alt="Latest Corrigendums"/><table><tr><td><a href="'+
             escape(LINK,quote=True)+'">1. Award announcement</a></td>'+
             '<td>award ref</td><td>30-Oct-2026 06:00 PM</td>'+
             '<td>30-Oct-2026 06:30 PM</td></tr></table></html>')).encode()


def test_current_official_notice_uses_stable_no_session_link():
    one=parse_epublish_latest(fixture(),as_of=DATE)[0]
    validate_notice(one,SOURCE_ID)
    assert one.title=="Procurement of 65 laptops"
    assert one.tender_number=="GEM/2026/B/8172809"
    assert one.url==LIST_URL and "session=" not in one.url and "sp=" not in one.url
    assert one.deadline is not None and one.deadline.endswith("+05:30")
    assert one.published_at is None and one.initial_price is None
    assert one.region=="India"
    assert one.identity==parse_epublish_latest(fixture(),as_of=DATE)[0].identity


@pytest.mark.parametrize("href", [
    "https://eprocure.gov.in.attacker.example/epublish/app?component=%24DirectLink&page=Home&session=1&sp=1",
    "http://eprocure.gov.in/epublish/app?component=%24DirectLink&page=Home&session=1&sp=1",
    "https://evil.example/epublish/app?component=%24DirectLink&page=Home&session=1&sp=1",
    "https://eprocure.gov.in:8080/epublish/app?component=%24DirectLink&page=Home&session=1&sp=1",
    "https://eprocure.gov.in/epublish/app?component=%24DirectLink&page=Home&session=1&sp=1&token=secret",
    "https://eprocure.gov.in/epublish/app?component=News&page=Home&session=1&sp=1",
    "https://eprocure.gov.in/epublish/app?component=%24DirectLink&page=Home&session=1",
    LINK+"#fragment",
])
def test_no_unsafe_or_non_detail_session_proof(href):
    with pytest.raises(SourceError,match="no verified"):
        parse_epublish_latest(fixture(href=href),as_of=DATE)


def test_expired_tender_is_not_misrepresented_as_open():
    with pytest.raises(SourceError):
        parse_epublish_latest(fixture(close="15-Oct-2026 09:00 AM",
                                      open_time="15-Oct-2026 10:00 AM"),as_of=DATE)


def test_corrigendum_is_not_taken_as_new_procurement():
    with pytest.raises(SourceError,match="structure"):
        parse_epublish_latest(fixture(section="Latest Corrigendums"),as_of=DATE)


def test_malformed_html_nonmatching_tables_and_oversize_fail_closed():
    for payload in (b"",b"<html>Home</html>",b"x"*(1024*1024+1),
                    b"<html>Latest Tenders Tender Title Latest Corrigendum</html>"):
        with pytest.raises(SourceError):
            parse_epublish_latest(payload,as_of=DATE)


def test_actual_source_fetches_single_official_fixed_listing(monkeypatch):
    requests=[]
    async def fake(url,timeout,accept):
        requests.append((url,timeout,accept))
        return fixture()
    monkeypatch.setattr("app.sources.india_epublish._fetch",fake)
    monkeypatch.setattr("app.sources.india_epublish.datetime",datetime)
    # Live system clock after 2026-10-30 would treat this fixture as expired:
    # use a future close date on the isolated fixture instead.
    async def future(url,timeout,accept):
        requests.append((url,timeout,accept))
        future_dt=(datetime.now(IST)+timedelta(days=9)).strftime("%d-%b-%Y %I:%M %p")
        future_open=(datetime.now(IST)+timedelta(days=10)).strftime("%d-%b-%Y %I:%M %p")
        return fixture(close=future_dt,open_time=future_open)
    monkeypatch.setattr("app.sources.india_epublish._fetch",future)
    assert len(asyncio.run(IndiaEpublishSource().fetch(limit=3)))==1
    assert requests==[(LIST_URL,25.0,"text/html,application/xhtml+xml")]


def test_independent_opt_in_and_safe_worker_host(monkeypatch):
    from scripts.asia_six_live_acceptance import settings
    from app.sources.catalog import build_source_catalog
    from app.sources.ingestion import HOSTS
    monkeypatch.delenv("VALYQON_ASIA_INDIA_EPUBLISH_ENABLED",raising=False)
    assert SOURCE_ID not in build_source_catalog(settings()).registry.keys()
    monkeypatch.setenv("VALYQON_ASIA_INDIA_EPUBLISH_ENABLED","1")
    cat=build_source_catalog(settings())
    assert SOURCE_ID in cat.enabled_keys
    assert HOSTS[SOURCE_ID]==frozenset({"eprocure.gov.in"})
