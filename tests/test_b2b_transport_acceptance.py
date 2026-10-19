"""Offline adversarial transport and durable acceptance, never live proof."""
import asyncio
import json
import ssl

import httpx
import pytest

import app.sources.b2b_center as b2b
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.sources.catalog import build_source_catalog
from app.sources.http import ConnectorTransportError, source_client, _policy
from app.sources.opportunities import OpportunityRepository
from scripts.ci_ru_b2b_real_worker import b2b_settings, ingest_live_b2b
from tests.test_b2b_foreign_aggregate import CAPTURE, extra_card


def install_transport(monkeypatch, handler):
    # Retain legacy transport regressions explicitly; new SSR transport is
    # independently exercised in test_b2b_next_market_adapter.py.
    import app.sources.catalog as catalog_module
    original_source = catalog_module.B2BCenterSource
    monkeypatch.setattr(catalog_module, "B2BCenterSource",
                        lambda **kw: original_source(listing_url=b2b.B2B_CENTER_LIST_URL, **kw))
    def client(**kwargs):
        return source_client(**kwargs, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(b2b, 'source_client', client)


@pytest.mark.parametrize('failure', ['policy', 'public_ip', 'tls_certificate', 'http_status'])
def test_nonretryable_failure_cannot_trigger_office_or_new_claim(monkeypatch, tmp_path, failure):
    calls = []
    def denied(request):
        calls.append(str(request.url))
        raise ConnectorTransportError(reason=failure)
    install_transport(monkeypatch, denied)
    db = Database(DatabaseSettings('', tmp_path / 'isolated.sqlite'))
    try:
        store = OpportunityRepository(db)
        store.initialize()
        with pytest.raises(AssertionError, match='permanent_failure'):
            ingest_live_b2b(db, build_source_catalog(b2b_settings()), store)
        assert calls == [b2b.B2B_CENTER_LIST_URL]
        assert store.read('b2b_center') == []
    finally:
        db.close()


def test_real_bounded_dispatch_size_fallback_and_no_third_request(monkeypatch):
    calls, budgets = [], []
    def reply(request):
        calls.append(str(request.url))
        budgets.append(_policy.get())
        return httpx.Response(200, content=b'x' * (b2b.MAX_BYTES + 1)
                              if len(calls) == 1 else CAPTURE)
    install_transport(monkeypatch, reply)
    notices = asyncio.run(b2b.B2BCenterSource(listing_url=b2b.B2B_CENTER_LIST_URL).fetch())
    assert calls == [b2b.B2B_CENTER_LIST_URL, b2b.B2B_CENTER_OFFICE_LIST_URL]
    assert budgets[0] is budgets[1]
    assert budgets[0].requests == budgets[0].max_requests == 2
    assert budgets[0].max_bytes == b2b.MAX_BYTES
    assert json.loads(notices[0].summary)['coverage_scope'] == 'office_only'


@pytest.mark.parametrize('office_native', [True, False])
def test_foreign_only_root_uses_only_official_partial_office(monkeypatch, office_native):
    calls = []
    foreign = extra_card('www.rts-tender.ru')
    def reply(request):
        calls.append(str(request.url))
        assert 'cookie' not in request.headers
        return httpx.Response(200, content=CAPTURE if len(calls) == 2 and office_native else foreign,
                              headers={'set-cookie': 'tracking=synthetic; Path=/'})
    install_transport(monkeypatch, reply)
    if office_native:
        notice = asyncio.run(b2b.B2BCenterSource(listing_url=b2b.B2B_CENTER_LIST_URL).fetch())[0]
        assert notice.listing_url == b2b.B2B_CENTER_OFFICE_LIST_URL
    else:
        from app.sources.eis_rss import SourceError
        with pytest.raises(SourceError, match='no usable'):
            asyncio.run(b2b.B2BCenterSource(listing_url=b2b.B2B_CENTER_LIST_URL).fetch())
    assert calls == [b2b.B2B_CENTER_LIST_URL, b2b.B2B_CENTER_OFFICE_LIST_URL]


@pytest.mark.parametrize('payload', [b'<html>CAPTCHA</html>', b'<html>Login required</html>'])
def test_unrecognized_or_challenge_page_cannot_trigger_fallback(monkeypatch, payload):
    calls = []
    def reply(request):
        calls.append(str(request.url))
        return httpx.Response(200, content=payload)
    install_transport(monkeypatch, reply)
    from app.sources.eis_rss import SourceError
    with pytest.raises(SourceError):
        asyncio.run(b2b.B2BCenterSource(listing_url=b2b.B2B_CENTER_LIST_URL).fetch())
    assert calls == [b2b.B2B_CENTER_LIST_URL]


@pytest.mark.parametrize('status', [408, 429, 503])
def test_durable_retry_recovers_without_fallback_or_duplicate(monkeypatch, tmp_path, status):
    calls, budgets = [], []
    def reply(request):
        calls.append(str(request.url))
        budgets.append(_policy.get())
        return httpx.Response(status if len(calls) == 1 else 200, content=CAPTURE)
    install_transport(monkeypatch, reply)
    db = Database(DatabaseSettings('', tmp_path / 'isolated.sqlite'))
    try:
        store = OpportunityRepository(db)
        store.initialize()
        result = ingest_live_b2b(db, build_source_catalog(b2b_settings()), store)
        assert result['inserted_count'] == result['accepted_count'] == 1
        assert calls == [b2b.B2B_CENTER_LIST_URL] * 2
        assert budgets[0] is not budgets[1]
        assert all(p.max_requests == 2 and p.requests == 1 for p in budgets)
        assert len(store.read('b2b_center')) == 1
    finally:
        db.close()


def test_certificate_verification_is_permanent_and_not_fallback(monkeypatch):
    calls = []
    def reply(request):
        calls.append(request)
        try:
            raise ssl.SSLCertVerificationError(1, 'synthetic certificate rejection')
        except ssl.SSLCertVerificationError as error:
            raise httpx.ConnectError('synthetic TLS failure') from error
    install_transport(monkeypatch, reply)
    with pytest.raises(ConnectorTransportError) as caught:
        asyncio.run(b2b.B2BCenterSource(listing_url=b2b.B2B_CENTER_LIST_URL).fetch())
    assert caught.value.reason == 'tls_certificate'
    assert not caught.value.retryable
    assert len(calls) == 1


def test_retry_exhaustion_stays_red_without_inserting_data(monkeypatch, tmp_path):
    calls = []
    def reply(request):
        calls.append(str(request.url))
        return httpx.Response(503)
    install_transport(monkeypatch, reply)
    db = Database(DatabaseSettings('', tmp_path / 'isolated.sqlite'))
    try:
        store = OpportunityRepository(db)
        store.initialize()
        with pytest.raises(AssertionError, match='handler_error'):
            ingest_live_b2b(db, build_source_catalog(b2b_settings()), store)
        assert calls == [b2b.B2B_CENTER_LIST_URL] * 3
        assert store.read('b2b_center') == []
    finally:
        db.close()


def test_offline_auth_acceptance_uses_actual_connector_and_scoring_workers(monkeypatch):
    from scripts.ci_ru_b2b_user_scoring import acceptance
    calls = []
    def reply(request):
        calls.append(str(request.url))
        return httpx.Response(200, content=CAPTURE)
    install_transport(monkeypatch, reply)
    evidence = acceptance()
    assert calls == [b2b.B2B_CENTER_LIST_URL]
    assert evidence['ingested_by_worker'] == evidence['db_search_verified'] == 1
    assert evidence['authorized_score_results'] == 1
    assert evidence['tenant_isolation'] and evidence['idempotent_replay']
