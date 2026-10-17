"""HKMA official public API JSON contract; live gate uses actual Government API."""
import asyncio
import json
from datetime import date

import pytest

from app.sources.hk_hkma_tender import API_URL, SOURCE_ID, HKMATenderSource, parse_hkma_tenders
from app.sources.eis_rss import SourceError
from app.sources.opportunities import validate_notice

DETAIL=("https://egazette.gld.gov.hk/pdf?year=2026&volume=30&gno=5911"
        "&notice_no=4001&type=gn&extra=")


def payload(link=DETAIL,date_field="2026-10-09",title="HKMA IT infrastructure procurement"):
    return json.dumps({"result":{"datasize":1,"records":[{
        "title":title,"link":link,"date":date_field
    }]}},ensure_ascii=False).encode()


def test_parse_true_government_notice_and_stable_identity():
    record=parse_hkma_tenders(payload(),as_of=date(2026,10,16))[0]
    validate_notice(record,SOURCE_ID)
    assert record.source==SOURCE_ID
    assert record.url==DETAIL
    assert record.published_at=="2026-10-09"
    assert record.customer=="Hong Kong Monetary Authority"
    assert record.deadline is None and record.initial_price is None
    assert record.identity==parse_hkma_tenders(payload(),as_of=date(2026,10,16))[0].identity


@pytest.mark.parametrize("link",[
    "https://egazette.gld.gov.hk.evil.example/pdf?year=2026&notice_no=4&type=gn",
    "https://evil.example/pdf?year=2026&notice_no=4&type=gn",
    "http://egazette.gld.gov.hk/pdf?year=2026&notice_no=4&type=gn",
    "https://egazette.gld.gov.hk:8080/pdf?year=2026&notice_no=4&type=gn",
    "https://egazette.gld.gov.hk/index.html?year=2026&notice_no=4&type=gn",
    "https://egazette.gld.gov.hk/pdf?year=2026&notice_no=4&type=gn&token=SECRET",
    "https://egazette.gld.gov.hk/pdf?year=2026&type=gn",
    DETAIL+"#unapproved-fragment",
])
def test_official_gazette_links_fail_closed(link):
    with pytest.raises(SourceError,match="no verifiable"):
        parse_hkma_tenders(payload(link),as_of=date(2026,10,16))


@pytest.mark.parametrize("day",["2024-01-01","2026-04-01","2026-11-01","totally-unknown"])
def test_expired_or_future_notices_not_current(day):
    with pytest.raises(SourceError):
        parse_hkma_tenders(payload(date_field=day),as_of=date(2026,10,16))


def test_award_only_and_unexpected_schema_not_accepted():
    for value in [b"",b"<html/>",b"null",b"[]",
                  b'{"result":{"records":"not-list"}}',
                  b'{"result":{"records":[]}}',
                  b"X"*(1024*1024+1)]:
        with pytest.raises(SourceError):
            parse_hkma_tenders(value,as_of=date(2026,10,16))


def test_fixed_anonymous_api_endpoint(monkeypatch):
    calls=[]
    async def fake_fetch(url,timeout,accept):
        calls.append((url,timeout,accept))
        return payload()
    monkeypatch.setattr("app.sources.hk_hkma_tender._fetch",fake_fetch)
    records=asyncio.run(HKMATenderSource().fetch(limit=3))
    assert len(records)==1
    assert calls==[(API_URL,25.0,"application/json")]


def test_independent_default_off_and_only_hkma_enabled(monkeypatch):
    from scripts.asia_six_live_acceptance import settings
    from app.sources.catalog import build_source_catalog
    monkeypatch.delenv("VALYQON_ASIA_HKMA_ENABLED",raising=False)
    assert SOURCE_ID not in build_source_catalog(settings()).registry.keys()
    monkeypatch.setenv("VALYQON_ASIA_HKMA_ENABLED","1")
    catalog=build_source_catalog(settings())
    assert SOURCE_ID in catalog.enabled_keys
