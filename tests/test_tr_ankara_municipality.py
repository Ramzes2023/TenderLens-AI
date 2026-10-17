"""No-network safety/contract tests for official Ankara public bid details."""
import asyncio
from datetime import datetime,timedelta,timezone
from html import escape

import pytest
from app.sources.tr_ankara_municipality import (
    SOURCE_ID, INDEX_URL, AnkaraMunicipalitySource,
    listing_detail_links,parse_ankara_tender,
)
from app.sources.eis_rss import SourceError
from app.sources.opportunities import validate_notice

TRT=timezone(timedelta(hours=3))
TODAY=datetime(2026,10,17,14,tzinfo=TRT)
DETAIL="https://www.ankara.bel.tr/ihaleler/detay/4149"

def listing(href="/ihaleler/detay/4149"):
    return ('<html><h1>İhaleler</h1><div><a href="'+escape(href,quote=True)+
            '">İhale Detayı</a></div></html>').encode()

def detail(url=DETAIL,ikn="2026/1727635",date="27.10.2026 14:30",title="Motorhane Kısmı 230 Kalem Yedek Parça Alım İşi"):
    return (('<html><h1>İhale Detayı</h1><div>İhale Konusu</div>'
             '<div>'+escape(title)+'</div>'
             '<div>İhale Birimi</div><div>Makine İkmal Bakım ve Onarım Dairesi Başkanlığı</div>'
             '<div>İhale Kısa Özeti</div><div>Mal alımı açık ihale</div>'
             '<div>KİK Kayıt No</div><div>'+escape(ikn)+'</div>'
             '<div>İhale Tarihi/Saati</div><div>'+escape(date)+'</div>'
             '</html>')).encode()

def test_listing_has_only_fixed_public_government_tender_detail():
    assert listing_detail_links(listing())==(DETAIL,)
    assert listing_detail_links(listing()+b'')==(DETAIL,)

@pytest.mark.parametrize("url",[
    "https://www.ankara.bel.tr.evil.example/ihaleler/detay/4149",
    "http://evil.example/ihaleler/detay/4149",
    "https://www.ankara.bel.tr:8080/ihaleler/detay/4149",
    "https://www.ankara.bel.tr/ihaleler/detay/4149?token=secret",
    "https://www.ankara.bel.tr/ihaleler/other/4149",
    DETAIL+"#fragment",
])
def test_listing_rejects_unapproved_origins_and_routes(url):
    with pytest.raises(SourceError,match="no verifiable"):
        listing_detail_links(listing(url))

def test_current_detail_fields_canonical_and_no_invented_price():
    n=parse_ankara_tender(detail(),detail_url=DETAIL,as_of=TODAY)
    assert n is not None
    validate_notice(n,SOURCE_ID)
    assert n.source==SOURCE_ID
    assert n.external_id=="4149"
    assert n.tender_number=="2026/1727635"
    assert n.title.startswith("Motorhane")
    assert n.customer.startswith("Makine")
    assert n.deadline.endswith("+03:00")
    assert n.url==DETAIL
    assert n.published_at is None and n.initial_price is None
    assert n.identity==parse_ankara_tender(detail(),detail_url=DETAIL,as_of=TODAY).identity

def test_expired_future_unparseable_or_missing_reference_not_sold_as_open():
    assert parse_ankara_tender(detail(date="12.10.2026 14:30"),detail_url=DETAIL,as_of=TODAY) is None
    assert parse_ankara_tender(detail(date="05.11.2028 14:30"),detail_url=DETAIL,as_of=TODAY) is None
    assert parse_ankara_tender(detail(date="invalid"),detail_url=DETAIL,as_of=TODAY) is None
    assert parse_ankara_tender(detail(ikn="not-an-IKN"),detail_url=DETAIL,as_of=TODAY) is None
    assert parse_ankara_tender(detail(title="İhale Sonucu"),detail_url=DETAIL,as_of=TODAY) is None

def test_detail_rejects_unsafe_gov_link_and_html_bombs():
    with pytest.raises(SourceError):
        parse_ankara_tender(detail(),detail_url=DETAIL+"?token=SECRET",as_of=TODAY)
    with pytest.raises(SourceError):
        parse_ankara_tender("<html>İhale list</html>".encode("utf-8"),detail_url=DETAIL,as_of=TODAY)
    with pytest.raises(SourceError):
        parse_ankara_tender(b"x"*(1024*1024+1),detail_url=DETAIL,as_of=TODAY)

def test_exact_two_requests_one_listing_plus_one_detail(monkeypatch):
    called=[]
    async def fake(url,timeout,accept):
        called.append(url)
        if url==INDEX_URL:return listing()
        deadline=(datetime.now(TRT)+timedelta(days=5)).strftime("%d.%m.%Y %H:%M")
        return detail(date=deadline)
    monkeypatch.setattr("app.sources.tr_ankara_municipality._fetch",fake)
    records=asyncio.run(AnkaraMunicipalitySource().fetch())
    assert len(records)==1
    assert called==[INDEX_URL,DETAIL]
    assert records[0].external_id=="4149"

def test_opt_in_off_by_default_and_allowlisted_worker(monkeypatch):
    from scripts.asia_six_live_acceptance import settings
    from app.sources.catalog import build_source_catalog
    from app.sources.ingestion import HOSTS
    monkeypatch.delenv("VALYQON_ASIA_TURKEY_ANKARA_ENABLED",raising=False)
    assert SOURCE_ID not in build_source_catalog(settings()).registry.keys()
    monkeypatch.setenv("VALYQON_ASIA_TURKEY_ANKARA_ENABLED","1")
    assert SOURCE_ID in build_source_catalog(settings()).enabled_keys
    assert HOSTS[SOURCE_ID]==frozenset({"www.ankara.bel.tr"})
