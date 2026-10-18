"""Official ASKİ independently gated, bounded real tender details contracts."""
import asyncio
from datetime import datetime,timedelta,timezone
from html import escape
import pytest

from app.sources.tr_aski_water import (
    SOURCE_ID,LIST_URL,ASKIWaterTendersSource,listing_rows,parse_detail,
)
from app.sources.eis_rss import SourceError
from app.sources.opportunities import validate_notice

TRT=timezone(timedelta(hours=3))
NOW=datetime(2026,10,17,13,tzinfo=TRT)
DETAIL="https://www.aski.gov.tr/tr/IhaleDetay.aspx?ID=3746"

def listing(link=DETAIL,post="16.10.2026",close="11.11.2026",kik="2026/1827948"):
    return (('<html><h1>Aski Genel Müdürlüğü Güncel İhale İlanları</h1>'
             '<table><tr><th>İlan Tarihi</th><th>İhale Tarihi</th><th>İhale Adı</th>'
             '<th>Kik Kayıt Numarası</th><th>İhale Türü</th><th>Detay</th></tr>'
             '<tr><td>'+post+'</td><td>'+close+'</td><td>97 Kalem Malzeme Alımı</td>'
             '<td>'+escape(kik)+'</td><td>Mal Alımı</td>'
             '<td><a href="'+escape(link,quote=True)+'">Detay</a></td></tr></table></html>')).encode()

def detail(kik="2026/1827948",close="11.11.2026 - 10:30"):
    return (('<html><h1>97 Kalem Malzeme Alımı</h1><h2>Aski Genel Müdürlüğü İhale Detayı</h2>'
             '<table><tr><td>İhale Kayıt Numarası (İKN)</td><td>:</td><td>'+escape(kik)+'</td></tr>'
             '<tr><td>2.1. Tarih ve Saati</td><td>:</td><td>'+escape(close)+'</td></tr></table></html>')).encode()

def test_official_listing_detail_and_deadline_normalization():
    assert listing_rows(listing(),as_of=NOW)==((DETAIL,"2026/1827948","97 Kalem Malzeme Alımı","2026-10-16"),)
    item=parse_detail(detail(),url=DETAIL,kik="2026/1827948",title="97 Kalem Malzeme Alımı",
                      published="2026-10-16",as_of=NOW)
    assert item is not None
    validate_notice(item,SOURCE_ID)
    assert item.external_id=="3746" and item.tender_number=="2026/1827948"
    assert item.url==DETAIL and item.deadline.endswith("+03:00")
    assert item.published_at=="2026-10-16" and item.initial_price is None

@pytest.mark.parametrize("url",[
    "https://www.aski.gov.tr.evil.example/tr/IhaleDetay.aspx?ID=3746",
    "https://evil.example/tr/IhaleDetay.aspx?ID=3746",
    "http://www.aski.gov.tr/tr/IhaleDetay.aspx?ID=3746",
    "https://www.aski.gov.tr:8080/tr/IhaleDetay.aspx?ID=3746",
    "https://www.aski.gov.tr/tr/IhaleDetay.aspx?ID=3746&token=bad",
    "https://www.aski.gov.tr/tr/IhaleDetay.aspx?ID=1",
    DETAIL+"#fragment",
])
def test_unapproved_detail_links_rejected(url):
    with pytest.raises(SourceError):
        listing_rows(listing(link=url),as_of=NOW)

def test_publication_after_now_or_closed_not_marked_active():
    with pytest.raises(SourceError):
        listing_rows(listing(post="01.11.2026"),as_of=NOW)
    with pytest.raises(SourceError):
        listing_rows(listing(close="01.10.2026"),as_of=NOW)

def test_detail_wrong_reference_or_deadline_fails_closed():
    assert parse_detail(detail(kik="2026/9999999"),url=DETAIL,
                        kik="2026/1827948",title="test",published="2026-10-16",
                        as_of=NOW) is None
    assert parse_detail(detail(close="12.10.2026 - 10:30"),url=DETAIL,
                        kik="2026/1827948",title="test",published="2026-10-16",
                        as_of=NOW) is None

def test_single_list_and_one_detail_no_network_outside_gov(monkeypatch):
    requests=[]
    async def fake(url,timeout,accept):
        requests.append(url)
        if url==LIST_URL:
            return listing(post=(datetime.now(TRT)-timedelta(days=1)).strftime("%d.%m.%Y"),
                           close=(datetime.now(TRT)+timedelta(days=15)).strftime("%d.%m.%Y"))
        due=(datetime.now(TRT)+timedelta(days=15)).strftime("%d.%m.%Y - %H:%M")
        return detail(close=due)
    monkeypatch.setattr("app.sources.tr_aski_water._fetch",fake)
    n=asyncio.run(ASKIWaterTendersSource().fetch())
    assert len(n)==1 and n[0].url==DETAIL and requests==[LIST_URL,DETAIL]

def test_catalog_default_off_exact_flag_and_worker_allowlist(monkeypatch):
    from scripts.asia_six_live_acceptance import settings
    from app.sources.catalog import build_source_catalog
    from app.sources.ingestion import HOSTS
    monkeypatch.delenv("VALYQON_ASIA_TURKEY_ASKI_ENABLED",raising=False)
    assert SOURCE_ID not in build_source_catalog(settings()).registry.keys()
    monkeypatch.setenv("VALYQON_ASIA_TURKEY_ASKI_ENABLED","1")
    assert SOURCE_ID in build_source_catalog(settings()).enabled_keys
    assert HOSTS[SOURCE_ID]==frozenset({"www.aski.gov.tr"})
