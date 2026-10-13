"""Offline RU-05 acceptance gates; no authentic upstream success is available.

MockTransport cases are synthetic failures, never evidence of a live source.
No SOAP operation, wrapper, request field or positive notice is invented here.
"""
import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from app.monitoring.config import MonitoringSettings
from app.scoring.runs import ScoringInputError, validate_configuration
from app.sources.base import TenderSource
from app.sources.catalog import build_source_catalog
from app.sources.http import ConnectorTransportError, FetchPolicy, bounded_fetch, source_client
from app.sources.ingestion import connector_version, validate_payload
from app.jobs.worker import PermanentJobError
from app.sources.registry import SourceRegistration, SourceRegistry, SourceRegistryError
from app.sources.tektorg import (
    MAX_BYTES, ExportProcedure, TekTorgOfflineSource, parse_export_fragment,
    validate_filters, validate_procedure_url,
)


DIRECT_KEYS = ('tektorg', 'roseltorg', 'fabrikant')
PROBE_URLS = (
    'https://api.tektorg.ru/procedures/wsdl',
    'https://www.roseltorg.ru/torgi',
    'https://www.fabrikant.ru/',
)


@pytest.fixture(autouse=True)
def no_network():
    with patch('socket.getaddrinfo', side_effect=AssertionError('Offline RU-05: no DNS')), \
         patch.object(httpx.AsyncHTTPTransport, 'handle_async_request',
                      side_effect=AssertionError('Offline RU-05: no connections')):
        yield


def test_host_evidence_does_not_claim_notices_or_contract():
    evidence = json.loads((Path(__file__).parent / 'fixtures' / 'ru05' /
                           'host_probe_evidence.json').read_text(encoding='utf-8'))
    assert tuple(row['url'] for row in evidence.values()) == PROBE_URLS
    assert all(row['status'] == 'BLOCKED_OR_UNVERIFIED' and
               row['content_sha256'] is None for row in evidence.values())


def test_unsupported_direct_sources_are_not_routed(monkeypatch):
    # Construct settings directly: do not read .env or change legacy configuration.
    monkeypatch.delenv('SAM_GOV_API_KEY', raising=False)
    monkeypatch.delenv('KZ_GOSZAKUP_API_TOKEN', raising=False)
    settings = MonitoringSettings(False, 600, 20, 5, 30, (), None,
                                  profile_feeds_enabled=False)
    catalog = build_source_catalog(settings)
    assert not set(DIRECT_KEYS).intersection(catalog.registry.keys())
    assert len(catalog.registry.keys()) == len(set(catalog.registry.keys()))
    for key in DIRECT_KEYS:
        payload = {'schema': 1, 'source_id': key, 'sync_window': '2026-10-13T00Z',
                   'connector_version': connector_version(key)}
        with pytest.raises(PermanentJobError):
            validate_payload(payload, catalog.registry)
        with pytest.raises(ScoringInputError):
            validate_configuration([key], 20)


def test_offline_contract_stays_default_off_and_registry_rejects_duplicates():
    source = TekTorgOfflineSource()
    assert isinstance(source, TenderSource)
    assert source.enabled is False
    assert asyncio.run(source.fetch()) == []
    registration = SourceRegistration('tektorg', 'Offline only', source, enabled=False)
    registry = SourceRegistry([registration])
    assert registry.keys(enabled_only=True) == ()
    with pytest.raises(SourceRegistryError):
        registry.register(registration)
    with pytest.raises(ValueError):
        asyncio.run(TekTorgOfflineSource(enabled=True).fetch())


def test_local_identity_contract_without_upstream_records():
    # Empty record bytes: identity serialization only, not a parsed real notice.
    first = ExportProcedure('local-section', 'local-id', b'')
    same = ExportProcedure('local-section', 'local-id', b'')
    other = ExportProcedure('other-section', 'local-id', b'')
    assert first.external_id == same.external_id
    assert json.loads(first.external_id) == ['local-section', 'local-id']
    assert first.external_id != other.external_id


@pytest.mark.parametrize('url', PROBE_URLS)
@pytest.mark.parametrize('status', [301, 302, 307, 401, 403, 429, 503])
def test_access_failure_or_redirect_never_follows_or_retries(url, status):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(status, headers={'location': 'https://127.0.0.1/private'})
    async def run():
        policy = FetchPolicy(frozenset({httpx.URL(url).host}), 1)
        with bounded_fetch(policy):
            async with source_client(transport=httpx.MockTransport(respond),
                                     trust_env=False) as client:
                with pytest.raises(ConnectorTransportError):
                    await client.get(url)
        assert policy.requests == 1
    asyncio.run(run())
    assert len(calls) == 1


@pytest.mark.parametrize('url', [
    'http://api.tektorg.ru/procedures/wsdl',
    'https://api.tektorg.ru.evil.example/procedures/wsdl',
    'https://user@api.tektorg.ru/procedures/wsdl',
    'https://api.tektorg.ru:444/procedures/wsdl',
    'https://127.0.0.1/procedures/wsdl',
])
def test_host_boundary_before_dispatch(url):
    calls = []
    async def run():
        with bounded_fetch(FetchPolicy(frozenset({'api.tektorg.ru'}), 1)):
            async with source_client(transport=httpx.MockTransport(lambda r: calls.append(r)),
                                     trust_env=False) as client:
                with pytest.raises(ConnectorTransportError):
                    await client.get(url)
    asyncio.run(run())
    assert calls == []


def test_timeout_is_failure_with_one_dispatch():
    calls = []
    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout('Synthetic timeout', request=request)
    async def run():
        with bounded_fetch(FetchPolicy(frozenset({'api.tektorg.ru'}), 1)):
            async with source_client(transport=httpx.MockTransport(timeout),
                                     trust_env=False, timeout=0.1) as client:
                with pytest.raises(ConnectorTransportError):
                    await client.get(PROBE_URLS[0])
    asyncio.run(run())
    assert len(calls) == 1


def test_exhausted_request_budget_prevents_dispatch():
    calls = []
    async def run():
        policy = FetchPolicy(frozenset({'api.tektorg.ru'}), 1, requests=1)
        with bounded_fetch(policy):
            async with source_client(transport=httpx.MockTransport(lambda r: calls.append(r)),
                                     trust_env=False) as client:
                with pytest.raises(ConnectorTransportError):
                    await client.get(PROBE_URLS[0])
        assert policy.requests == 1
    asyncio.run(run())
    assert calls == []


def test_transport_payload_over_budget_is_rejected():
    responses = []
    def oversize(request):
        response = httpx.Response(200, content=b'x' * 65)
        responses.append(response)
        return response
    async def run():
        with bounded_fetch(FetchPolicy(frozenset({'api.tektorg.ru'}), 1, max_bytes=64)):
            async with source_client(transport=httpx.MockTransport(oversize),
                                     trust_env=False) as client:
                with pytest.raises(ConnectorTransportError):
                    await client.get(PROBE_URLS[0])
    asyncio.run(run())
    assert len(responses) == 1
    assert responses[0].is_closed


@pytest.mark.parametrize('payload', [
    b'<html><body>Login required</body></html>',
    b'<html><body>CAPTCHA</body></html>',
    b'<Fault><faultstring>Authentication required</faultstring></Fault>',
    b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///blocked">]><x>&e;</x>',
    b'<Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/"/>',
])
def test_access_pages_and_unverified_soap_are_not_export_fragments(payload):
    with pytest.raises(ValueError):
        parse_export_fragment(payload)


def test_xml_byte_and_pagination_limits_are_local_safety_bounds():
    # Allocate inside the test, never in a pytest parameter ID / environment value.
    with pytest.raises(ValueError):
        parse_export_fragment(b'x' * (MAX_BYTES + 1))
    for values in ({'page': '6'}, {'limitPage': '501'}):
        with pytest.raises(ValueError):
            validate_filters(values)
    with pytest.raises(ValueError):
        asyncio.run(TekTorgOfflineSource(pages=(b'<invalid/>',) * 6,
                                       projector=lambda r, p: None, enabled=True).fetch())
    with pytest.raises(ValueError):
        validate_procedure_url(PROBE_URLS[0])
