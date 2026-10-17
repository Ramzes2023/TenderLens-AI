"""No-network security and field contracts for UAE federal government RFQs."""
from datetime import datetime, timedelta, timezone
from html import escape
import asyncio

import pytest
from app.sources.uae_mof_rfqs import URL,SOURCE_ID,UAEMinistryFinanceSource,parse_uae_open_rfqs
from app.sources.eis_rss import SourceError
from app.sources.opportunities import validate_notice

GST=timezone(timedelta(hours=4))
NOW=datetime(2026,10,17,14,tzinfo=GST)
DETAIL="https://procurement.gov.ae/page.aspx/en/bpm/process_manage_extranet/12764"

def html_page(link=DETAIL, rfq="12764",title="Zoom License",
              start="16/10/2026 11:27:12 AM",end="06/11/2026 12:00:00 PM"):
    return (('<html><h1>Current Business Opportunities</h1><h2>Open tenders</h2>'
             '<table><tr><th>RFQ Number</th><th>Entity Name</th><th>Title</th>'
             '<th>Open Date</th><th>Close Date</th><th>Link</th></tr>'
             '<tr><td>'+escape(rfq)+'</td>'
             '<td>Ministry of Education - (109/16894)</td><td>'+escape(title)+'</td>'
             '<td>'+escape(start)+'</td><td>'+escape(end)+'</td>'
             '<td><a href="'+escape(link,quote=True)+'">Click here</a></td></tr>'
             '</table></html>')).encode()

def test_exact_official_rfqs_normalize_and_preserve_real_dates():
    notice=parse_uae_open_rfqs(html_page(),as_of=NOW)[0]
    validate_notice(notice,SOURCE_ID)
    assert notice.source==SOURCE_ID and notice.external_id=="12764"
    assert notice.tender_number=="12764"
    assert notice.title=="Zoom License"
    assert notice.url==DETAIL
    assert notice.customer.startswith("Ministry of Education")
    assert notice.published_at.endswith("+04:00") and notice.deadline.endswith("+04:00")
    assert notice.initial_price is None
    assert parse_uae_open_rfqs(html_page(),as_of=NOW)[0].identity==notice.identity

@pytest.mark.parametrize("link",[
    "https://procurement.gov.ae.attacker.example/page.aspx/en/bpm/process_manage_extranet/12764",
    "http://procurement.gov.ae/page.aspx/en/bpm/process_manage_extranet/12764",
    "https://evil.example/page.aspx/en/bpm/process_manage_extranet/12764",
    "https://procurement.gov.ae:8080/page.aspx/en/bpm/process_manage_extranet/12764",
    "https://procurement.gov.ae/page.aspx/en/bpm/process_manage_extranet/12345",
    "https://procurement.gov.ae/page.aspx/en/bpm/process_manage_extranet/12764?token=secret",
    DETAIL+"#unsafe",
])
def test_rejects_wrong_official_ref_unsafe_and_nonpublic_links(link):
    with pytest.raises(SourceError,match="no verified"):
        parse_uae_open_rfqs(html_page(link=link),as_of=NOW)

@pytest.mark.parametrize("start,end",[
    ("16/10/2026 11:27:12 AM","17/10/2026 10:00:00 AM"),
    ("16/11/2026 11:27:12 AM","06/12/2026 10:00:00 AM"),
    ("invalid","06/11/2026 12:00:00 PM"),
])
def test_closed_future_and_malformed_opportunities_not_current(start,end):
    with pytest.raises(SourceError):
        parse_uae_open_rfqs(html_page(start=start,end=end),as_of=NOW)

def test_non_tender_markup_and_oversized_rejected():
    for data in (b"",b"<html>news</html>",b"X"*(1024*1024+1)):
        with pytest.raises(SourceError):
            parse_uae_open_rfqs(data,as_of=NOW)

def test_one_exact_government_html_request(monkeypatch):
    calls=[]
    async def fake(url,timeout,accept):
        calls.append((url,timeout,accept))
        today=datetime.now(GST)
        start=(today-timedelta(days=1)).strftime("%d/%m/%Y %I:%M:%S %p")
        close=(today+timedelta(days=15)).strftime("%d/%m/%Y %I:%M:%S %p")
        return html_page(start=start,end=close)
    monkeypatch.setattr("app.sources.uae_mof_rfqs._fetch",fake)
    assert len(asyncio.run(UAEMinistryFinanceSource().fetch()))==1
    assert calls==[(URL,25.0,"text/html,application/xhtml+xml")]

def test_default_off_and_independent_activation(monkeypatch):
    from app.sources.catalog import build_source_catalog
    from scripts.asia_six_live_acceptance import settings
    from app.sources.ingestion import HOSTS
    monkeypatch.delenv("VALYQON_ASIA_UAE_FEDERAL_ENABLED",raising=False)
    assert SOURCE_ID not in build_source_catalog(settings()).registry.keys()
    monkeypatch.setenv("VALYQON_ASIA_UAE_FEDERAL_ENABLED","1")
    assert SOURCE_ID in build_source_catalog(settings()).enabled_keys
    assert HOSTS[SOURCE_ID]==frozenset({"mof.gov.ae"})
