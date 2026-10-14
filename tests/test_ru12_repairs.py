"""Focused offline contracts. Captures and mocks never establish live proof."""
import asyncio
import hashlib
import ssl
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from app.sources import eis_rss, eis_223_rss
from app.sources.b2b_center import parse_b2b_center_listing
from app.sources.http import source_client, ConnectorTransportError


def test_windows_roots_require_server_auth_trust(monkeypatch):
    # Existing public certificate used only as a test store entry.
    pem = (Path(__file__).resolve().parents[1] / 'russian_trusted_root_ca_pem.crt').read_text()
    der = ssl.PEM_cert_to_DER_cert(pem)
    calls = []
    def store(name):
        calls.append(name)
        return [(der, 'x509_asn', {ssl.Purpose.SERVER_AUTH.oid}),
                (b'invalid-untrusted', 'x509_asn', {ssl.Purpose.CLIENT_AUTH.oid})]
    monkeypatch.setattr(ssl, 'enum_certificates', store, raising=False)
    context = eis_rss.eis_system_ssl_context()
    assert calls == ['ROOT']
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert context.cert_store_stats()['x509_ca'] == 1
    with pytest.raises(ValueError):
        context.verify_mode = ssl.CERT_NONE  # Hostname verification forbids this.


@pytest.mark.parametrize('cls,builder', [
    (eis_rss.EisRssSource, eis_rss.build_eis_rss_url),
    (eis_223_rss.Eis223RssSource, eis_223_rss.build_eis_223_rss_url)])
def test_system_trust_opt_in_scope(cls, builder):
    source = cls((builder('test'),))
    assert not source.direct and not source.system_trust
    with pytest.raises(ValueError):
        asyncio.run(cls(source.urls, system_trust=True).fetch())
    with pytest.raises(ValueError):
        eis_rss.eis_tls_verify(direct=True, system_trust=True, ca_bundle_file=Path('override'))
    assert cls(source.urls, direct=True, system_trust=True).for_search_terms(['new']).system_trust


def test_system_context_does_not_enable_proxy():
    async def run():
        async with source_client(verify=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
                                 trust_env=False, proxy='http://127.0.0.1:9') as client:
            with pytest.raises(ConnectorTransportError):
                await client.get('https://zakupki.gov.ru/')
    asyncio.run(run())


@pytest.mark.parametrize('law', ['44', '223'])
def test_secure_context_preserves_entire_feed_law_gate(law, monkeypatch):
    from test_ru11_eis_law import item, feed
    module = eis_rss if law == '44' else eis_223_rss
    cls = module.EisRssSource if law == '44' else module.Eis223RssSource
    builder = module.build_eis_rss_url if law == '44' else module.build_eis_223_rss_url
    payload = feed(item(law), item('223' if law == '44' else '44'))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    monkeypatch.setattr(eis_rss, 'eis_system_ssl_context', lambda: context)
    def client(**kwargs):
        assert kwargs['verify'] is context
        assert not kwargs['trust_env'] and not kwargs['follow_redirects']
        return source_client(**kwargs, transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=payload)))
    with patch.object(module, 'source_client', client), pytest.raises(eis_rss.SourceError):
        asyncio.run(cls((builder('test'),), direct=True, system_trust=True).fetch(limit=1))


def test_suppressed_nested_exception_diagnostics_are_sanitized():
    from ru12_six_sources_live_smoke import exception_frames
    try:
        try:
            raise ValueError('private-token-and-response-body')
        except ValueError:
            raise eis_rss.SourceError('private-url') from None
    except eis_rss.SourceError as error:
        report = exception_frames(error)
    assert [frame['type'] for frame in report] == ['SourceError', 'ValueError']
    assert report[-1]['frames'][-1]['file'] == 'tests/test_ru12_repairs.py'
    assert 'private' not in str(report)


def test_actual_b2b_capture_snapshot_lookup(tmp_path):
    from app.database.backend import Database
    from app.database.config import DatabaseSettings
    from app.sources.catalog import SourceCatalog
    from app.sources.multi import MultiSourceFetcher
    from app.sources.registry import SourceRegistry, SourceRegistration
    from app.sources.opportunities import OpportunityRepository
    from app.sources.snapshots import snapshot_catalog, SnapshotSource
    payload = (Path(__file__).with_name('fixtures') / 'ru08' / 'b2b_search.html').read_bytes()
    assert hashlib.sha256(payload).hexdigest() == 'b5ec85c85e9a29ff2fd02a6815adbdcdc61ca2155d34fb8c18e057325d945aa7'
    notices = parse_b2b_center_listing(payload)
    assert len(notices) == 10
    repo = OpportunityRepository(Database(DatabaseSettings('ru12-test', tmp_path / 'notices.sqlite')))
    repo.initialize()
    for notice in notices:
        assert repo.upsert(notice, 'connector-sync-v1:b2b_center:adapter-r1')
    registry = SourceRegistry([SourceRegistration('b2b_center', 'B2B-Center',
                                                  SnapshotSource(repo, 'b2b_center'))])
    catalog = snapshot_catalog(SourceCatalog(registry, MultiSourceFetcher(registry)), repo)
    with patch('socket.getaddrinfo', side_effect=AssertionError('Snapshot must not fetch')):
        report = asyncio.run(catalog.fetch(source_keys=('b2b_center',), search_terms=('l0338200012226000019-1',)))
    assert not report.failures
    assert [n.external_id for n in report.notices] == ['l0338200012226000019-1']
