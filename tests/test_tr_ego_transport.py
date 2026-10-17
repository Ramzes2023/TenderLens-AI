"""Offline official Ankara EGO transportation tender origin and KİK tests."""
import asyncio
from datetime import datetime,timedelta,timezone
from html import escape
import pytest
from app.sources.tr_ego_transport import (
    SOURCE_ID,INDEX_URL,EGOTenderSource,parse_ego_listing,parse_ego_detail,
)
from app.sources.eis_rss import SourceError
from app.sources.opportunities import validate_notice

TRT=timezone(timedelta(hours=3))
TODAY=datetime(2026,10,17,13,tzinfo=TRT)
DETAIL=("https://www.ego.gov.tr/tr/ihale/detay/11894/"
        "metro-isletme-sube-mudurlugu-crrc-trenleri-icin-bo?tip=0")
KIK="2026/1873146"
TITLE="METRO İŞLETME ŞUBE MÜDÜRLÜĞÜ CRRC TRENLERİ İÇİN BOJİ CER MİLİ MAL ALIMI"

def listing(url=DETAIL,day="27.10.2026",kik=KIK,title=TITLE):
    return (('<html><h1>İHALELER</h1><table>'
             '<tr><td>e-ihale</td><td>'+escape(day)+'</td><td>'
             '<a href="'+escape(url,quote=True)+'">'+escape(title)+'</a></td><td>'
             +escape(kik)+'</td></tr></table></html>')).encode("utf-8")

def detail(title=TITLE,kik=KIK,day="27.10.2026 15:00"):
    return (('<html><h1>İHALE DETAYI</h1><div>İHALE ADI</div><div>'
             +escape(title)+'</div><div>İHALE BİRİMİ</div>'
             '<div>ULAŞIM PLANLAMA ve RAYLI SİSTEM DAİRESİ BAŞKANLIĞI</div>'
             '<div>KİK KAYIT NO</div><div>'+escape(kik)+'</div>'
             '<div>İHALE TARİHİ</div><div>'+escape(day)+'</div></html>')).encode("utf-8")

def test_genuine_bid_list_filters_by_official_individual_and_future_date():
    assert parse_ego_listing(listing(),as_of=TODAY)==((DETAIL,KIK,TITLE),)

def test_detail_stable_ikn_title_buying_agency_deadline_and_identity():
    n=parse_ego_detail(detail(),link=DETAIL,kik=KIK,title=TITLE,as_of=TODAY)
    assert n is not None
    validate_notice(n,SOURCE_ID)
    assert n.external_id=="11894" and n.tender_number==KIK
    assert n.url==DETAIL and n.title==TITLE
    assert n.customer.startswith("ULAŞIM PLANLAMA")
    assert n.deadline.endswith("+03:00") and n.published_at is None
    assert n.initial_price is None

@pytest.mark.parametrize("link",[
    "https://www.ego.gov.tr.attacker.example/tr/ihale/detay/11894/test-name?tip=0",
    "http://www.ego.gov.tr/tr/ihale/detay/11894/test-name?tip=0",
    "https://evil.example/tr/ihale/detay/11894/test-name?tip=0",
    "https://www.ego.gov.tr:8080/tr/ihale/detay/11894/test-name?tip=0",
    "https://www.ego.gov.tr/tr/ihale/detay/11894/test-name?tip=1",
    "https://www.ego.gov.tr/tr/ihale/detay/11894/test-name?tip=0&token=secret",
    "https://www.ego.gov.tr/tr/ihale/detay/11894/test-name?tip=0#section",
])
def test_unapproved_link_is_not_a_public_tender(link):
    with pytest.raises(SourceError):
        parse_ego_listing(listing(url=link),as_of=TODAY)

def test_expired_or_unverified_tender_rejected():
    with pytest.raises(SourceError):
        parse_ego_listing(listing(day="01.10.2026"),as_of=TODAY)
    with pytest.raises(SourceError):
        parse_ego_listing(listing(kik="not-number"),as_of=TODAY)
    assert parse_ego_detail(detail(kik="2026/5555555"),link=DETAIL,kik=KIK,title=TITLE,as_of=TODAY) is None
    assert parse_ego_detail(detail(day="01.10.2026 10:00"),link=DETAIL,kik=KIK,title=TITLE,as_of=TODAY) is None
    assert parse_ego_detail(detail(title="Procurement other"),link=DETAIL,kik=KIK,title=TITLE,as_of=TODAY) is None

def test_invalid_html_does_not_create_tender():
    with pytest.raises(SourceError):
        parse_ego_listing(b"<html>No tenders</html>",as_of=TODAY)
    with pytest.raises(SourceError):
        parse_ego_detail(b"x"*(1024*1024+1),link=DETAIL,kik=KIK,title=TITLE,as_of=TODAY)

def test_one_list_one_detail_only_fixed_official_site(monkeypatch):
    called=[]
    async def stub(url,timeout,accept):
        called.append(url)
        when=(datetime.now(TRT)+timedelta(days=7))
        if url==INDEX_URL:return listing(day=when.strftime("%d.%m.%Y"))
        return detail(day=when.strftime("%d.%m.%Y %H:%M"))
    monkeypatch.setattr("app.sources.tr_ego_transport._fetch",stub)
    records=asyncio.run(EGOTenderSource().fetch())
    assert len(records)==1 and records[0].source==SOURCE_ID
    assert called==[INDEX_URL,DETAIL]

def test_registration_exact_opt_in(monkeypatch):
    from scripts.asia_six_live_acceptance import settings
    from app.sources.catalog import build_source_catalog
    from app.sources.ingestion import HOSTS
    monkeypatch.delenv("VALYQON_ASIA_TURKEY_EGO_ENABLED",raising=False)
    assert SOURCE_ID not in build_source_catalog(settings()).registry.keys()
    monkeypatch.setenv("VALYQON_ASIA_TURKEY_EGO_ENABLED","1")
    assert SOURCE_ID in build_source_catalog(settings()).enabled_keys
    assert HOSTS[SOURCE_ID]==frozenset({"www.ego.gov.tr"})
