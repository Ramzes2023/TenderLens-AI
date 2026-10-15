"""Synthetic RSS through the existing bounded connector, SQLite and scoring.

No live EIS coverage. Host test runner must execute this suite independently.
"""
import asyncio
import json
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.jobs import JobService
from app.jobs.worker import PermanentJobError, RetryableJobError
from app.monitoring.config import MonitoringSettings
from app.scoring.runs import ScoringRunService, ScoringInputError
from app.sources.catalog import build_source_catalog
from app.sources.eis_223_rss import build_eis_223_rss_url, parse_eis_223_feed
from app.sources import eis_223_rss as adapter
from app.sources.http import source_client, ConnectorTransportError
from app.sources.ingestion import ConnectorSyncService, ConnectorSyncHandler, SYSTEM_SCOPE
from app.sources.snapshots import snapshot_catalog
from test_scoring_workers import offline, system, run

URL = build_eis_223_rss_url('aluminium')
RSS = b'''<rss version="2.0"><channel><item>
<title>Supply of aluminium 32616463738</title><guid>ru03-notice-1</guid>
<link>https://zakupki.gov.ru/notice/32616463738</link>
<description>223-FZ; OKPD2: 24.42.11.110; KTRU: 24.42.11.110-00000001</description>
</item></channel></rss>'''


def settings(**values):
    return replace(MonitoringSettings(False, 600, 20, 5, 9, (), None), **values)


def enabled(**values):
    return build_source_catalog(settings(eis_223_enabled=True, eis_223_rss_urls=(URL,), **values))


def mock_http(monkeypatch, handler):
    calls, options = [], []
    def factory(**kwargs):
        options.append(kwargs.copy())
        def dispatch(request):
            calls.append(request)
            return handler(request)
        return source_client(**dict(kwargs, verify=True, trust_env=False,
                                    transport=httpx.MockTransport(dispatch)))
    monkeypatch.setattr(adapter, 'source_client', factory)
    return calls, options


def test_default_off_and_catalog_regression():
    baseline = build_source_catalog(settings())
    assert 'eis_223' not in baseline.registry.keys()
    assert build_source_catalog(settings(eis_223_rss_urls=(URL,))).registry.keys() == baseline.registry.keys()
    assert build_source_catalog(settings(eis_223_enabled=True)).registry.keys() == baseline.registry.keys()
    catalog = enabled()
    assert catalog.registry.keys()[:-1] == baseline.registry.keys()
    assert catalog.registry.get('eis') == baseline.registry.get('eis')


def test_profile_terms_and_ca(monkeypatch):
    calls, options = mock_http(monkeypatch, lambda request: httpx.Response(200, content=RSS))
    catalog = enabled(eis_223_profile_feeds_enabled=True, ca_bundle_file=Path('verified-eis.pem'))
    report = asyncio.run(catalog.fetch(source_keys=['eis_223'], search_terms=['cable']))
    assert len(report.notices) == 1
    assert calls[0].url.params['searchString'] == 'cable'
    assert calls[0].url.params['fz223'] == 'on' and 'fz44' not in calls[0].url.params
    assert options[0]['verify'] == 'verified-eis.pem' and options[0]['timeout'] == 9


def ingest(s, catalog):
    service = ConnectorSyncService(JobService(s.jobs), catalog)
    job = service.enqueue('eis_223', now=datetime(2026, 10, 13, tzinfo=timezone.utc))
    handler = ConnectorSyncHandler(catalog, s.store)
    return handler(SimpleNamespace(job=job, should_stop=False), job.payload)


def test_full_offline_path(system, monkeypatch):
    s = system
    s.store.initialize()
    calls, _ = mock_http(monkeypatch, lambda request: httpx.Response(200, content=RSS))
    catalog = enabled(eis_223_profile_feeds_enabled=True)
    assert ingest(s, catalog)['inserted_count'] == 1
    assert ingest(s, catalog)['updated_count'] == 1
    assert len(calls) == 2
    snapshots = snapshot_catalog(catalog, s.store)
    report = asyncio.run(snapshots.fetch(source_keys=['eis_223'], search_terms=['aluminium']))
    assert report.notices[0].identity == ('eis_223', 'ru03-notice-1')
    with closing(s.database.connect()) as conn:
        encoded = conn.execute("SELECT notice_json FROM source_opportunities WHERE source_id='eis_223'").fetchone()[0]
        assert conn.execute("SELECT COUNT(*) FROM source_notice_observations WHERE source_id='eis_223'").fetchone()[0] == 1
    stored = json.loads(encoded)
    assert stored['requested_law'] == '223-FZ'
    assert stored['independently_verified_law'] is None
    assert stored['feed_url'] == URL and stored['raw_guid'] == 'ru03-notice-1'
    assert stored['procurement_signals']['okpd2_codes'] == ['24.42.11.110']
    assert stored['procurement_signals']['law'] == '223-FZ'
    s.service.catalog = catalog
    job = s.service.enqueue(scope=s.scope, sources=['eis_223'])
    assert run(s)
    view = s.service.view(job.id, scope=s.scope)
    assert view['complete'] and view['candidate_count'] == 1
    assert view['source_state'] == {'eis_223': 'available'}
    with closing(s.database.connect()) as conn:
        assert conn.execute("SELECT notice_json FROM source_opportunities WHERE source_id='eis_223'").fetchone()[0] == encoded


@pytest.mark.parametrize('error,expected', [
    (httpx.ReadTimeout('synthetic'), RetryableJobError),
    (ConnectorTransportError(retryable=True), RetryableJobError),
    (ConnectorTransportError(), PermanentJobError),
])
def test_transport_classification(system, monkeypatch, error, expected):
    def fail(request):
        raise error
    mock_http(monkeypatch, fail)
    with pytest.raises(expected):
        ingest(system, enabled())


@pytest.mark.parametrize('status,expected', [(429, RetryableJobError), (503, RetryableJobError), (403, PermanentJobError)])
def test_http_classification(system, monkeypatch, status, expected):
    mock_http(monkeypatch, lambda request: httpx.Response(status))
    with pytest.raises(expected):
        ingest(system, enabled())


def test_malformed_feed(system, monkeypatch):
    mock_http(monkeypatch, lambda request: httpx.Response(200, content=b'<rss>'))
    with pytest.raises(PermanentJobError):
        ingest(system, enabled())


def test_observation_changes_and_replay(system):
    s = system
    s.store.initialize()
    original = parse_eis_223_feed(RSS, feed_url=URL)[0]
    first = replace(original, initial_price=100, currency='RUB', deadline='2026-11-01')
    changed = replace(first, initial_price=120, deadline='2026-11-02', title='Revised aluminium supply')
    version = 'connector-sync-v1:eis_223:adapter-r1'
    for notice in [first, first, changed, changed, first]:
        s.store.upsert(notice, version)
    with closing(s.database.connect()) as conn:
        rows = conn.execute('SELECT comparison_json FROM source_notice_observations ORDER BY observed_at').fetchall()
    assert len(rows) == 2
    changes = json.loads(rows[1][0])
    assert changes['status'] == 'changed'
    assert {change['field'] for change in changes['changes']} == {'title', 'price', 'deadline'}
    # Equal external IDs from another source remain separate identities.
    s.store.upsert(replace(first, source='eis', enrichment=None), 'connector-sync-v1:eis:adapter-r1')
    assert s.store.read('eis')[0].identity != s.store.read('eis_223')[0].identity


def test_scoring_requires_configured_catalog(system):
    with pytest.raises(ScoringInputError):
        system.service.enqueue(scope=system.scope, sources=['eis_223'])
    system.service.catalog = build_source_catalog(settings())
    with pytest.raises(ScoringInputError):
        system.service.enqueue(scope=system.scope, sources=['eis_223'])


def test_profile_only_shared_ingestion_rejected(system):
    catalog = build_source_catalog(settings(eis_223_enabled=True, eis_223_profile_feeds_enabled=True))
    with pytest.raises(PermanentJobError):
        ConnectorSyncService(JobService(system.jobs), catalog).enqueue('eis_223')


def test_bounded_hosts_and_budget(system, monkeypatch):
    calls, _ = mock_http(monkeypatch, lambda request: httpx.Response(200, content=b'<rss/>'))
    catalog = build_source_catalog(settings(eis_223_enabled=True, eis_223_rss_urls=(URL,) * 8))
    assert ingest(system, catalog)['fetched_count'] == 0
    assert len(calls) == 5
    # Valid syntax for the adapter never broadens the worker host allowlist.
    from app.sources.http import FetchPolicy, bounded_fetch
    async def rejected():
        with bounded_fetch(FetchPolicy(frozenset({'zakupki.gov.ru'}), 1)):
            async with source_client(trust_env=False, transport=httpx.MockTransport(
                    lambda request: pytest.fail('Disallowed endpoint dispatched'))) as client:
                await client.get('https://evil.invalid/feed')
    with pytest.raises(ConnectorTransportError):
        asyncio.run(rejected())


def test_invalid_item_skipped(system, monkeypatch):
    mock_http(monkeypatch, lambda request: httpx.Response(200, content=b'''
        <rss><channel><item><title>Invalid</title><guid>bad</guid>
        <link>file:///private</link></item></channel></rss>'''))
    result = ingest(system, enabled())
    assert result['accepted_count'] == 0 and result['skipped_count'] == 1


def test_snapshot_terms_are_local_when_profile_feeds_off(system):
    s = system
    s.store.initialize()
    s.store.upsert(parse_eis_223_feed(RSS, feed_url=URL)[0], 'connector-sync-v1:eis_223:adapter-r1')
    catalog = snapshot_catalog(enabled(), s.store)
    report = asyncio.run(catalog.fetch(source_keys=['eis_223'], search_terms=['absent-term']))
    assert not report.notices


def test_observation_migration_idempotent_and_unknown_fields(system):
    s = system
    s.store.initialize()
    s.store.initialize()
    original = parse_eis_223_feed(RSS, feed_url=URL)[0]
    version = 'connector-sync-v1:eis_223:adapter-r1'
    s.store.upsert(original, version)
    s.store.upsert(replace(original, deadline='01.11.2026 12:00'), version)
    with closing(s.database.connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM app_schema_migrations WHERE domain='source_observations'").fetchone()[0] == 1
        rows = conn.execute('SELECT comparison_json FROM source_notice_observations').fetchall()
    assert len(rows) == 2
    assert all(not json.loads(row[0])['changes'] for row in rows)


def test_44_and_223_queries_stay_separate():
    from urllib.parse import parse_qs, urlsplit
    from app.sources.eis_rss import build_eis_rss_url
    query44 = parse_qs(urlsplit(build_eis_rss_url('aluminium')).query)
    query223 = parse_qs(urlsplit(URL).query)
    assert query44['fz44'] == ['on'] and 'fz223' not in query44
    assert query223['fz223'] == ['on'] and 'fz44' not in query223


@pytest.mark.parametrize('url', [
    'https://evil.invalid/rss?fz223=on',
    URL + '&fz44=on',
    URL.replace('https://', 'http://'),
    URL.replace('zakupki.gov.ru', 'zakupki.gov.ru:8443'),
])
def test_invalid_223_configuration_rejected(url):
    with pytest.raises(ValueError):
        build_source_catalog(settings(eis_223_enabled=True, eis_223_rss_urls=(url,)))


def test_sqlite_migration_14_upgrade_preserves_existing_data(system):
    from app.database.migrations import MIGRATIONS
    s = system
    assert [migration.version for migration in MIGRATIONS] == list(range(1, 15))
    assert MIGRATIONS[-1].domain == 'source_observations'
    # Only the synthetic fixture database: simulate an installation at version 13.
    with closing(s.database.connect()) as conn, conn:
        conn.execute('DROP TABLE IF EXISTS source_notice_observations')
        conn.execute('DELETE FROM app_schema_migrations WHERE version=14')
        notices = conn.execute('SELECT * FROM source_opportunities').fetchall()
        accounts = conn.execute('SELECT id,email FROM auth_accounts ORDER BY id').fetchall()
        ledger = conn.execute('SELECT version,domain,checksum FROM app_schema_migrations ORDER BY version').fetchall()
    s.database.migrate()
    s.database.migrate()
    with closing(s.database.connect()) as conn:
        assert conn.execute('SELECT * FROM source_opportunities').fetchall() == notices
        assert conn.execute('SELECT id,email FROM auth_accounts ORDER BY id').fetchall() == accounts
        assert conn.execute('SELECT version,domain,checksum FROM app_schema_migrations WHERE version<14 ORDER BY version').fetchall() == ledger
        migration = conn.execute('SELECT version,domain,checksum FROM app_schema_migrations WHERE version=14').fetchone()
        assert tuple(migration) == (14, 'source_observations', MIGRATIONS[-1].checksum)
        assert conn.execute('SELECT COUNT(*) FROM source_notice_observations').fetchone()[0] == 0
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()


def test_connector_rejects_customer_scope_without_fetch(system, monkeypatch):
    calls, _ = mock_http(monkeypatch, lambda request: pytest.fail('Customer scoped fetch'))
    catalog = enabled()
    job = ConnectorSyncService(JobService(system.jobs), catalog).enqueue('eis_223')
    with pytest.raises(PermanentJobError):
        ConnectorSyncHandler(catalog, system.store)(
            SimpleNamespace(job=replace(job, scope=system.scope), should_stop=False), job.payload)
    assert not calls
