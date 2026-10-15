"""P3.9 offline release gates. All databases are disposable pytest fixtures."""
from contextlib import closing
import json
import sqlite3
import time
from unittest.mock import patch

import pytest

from app.database.analytics_read import AnalyticsReadLimits, bounded_read
from app.database.backend import Database, StorageError
from app.database.config import DatabaseSettings
from app.database.migrations import MIGRATIONS
from app.database.repository import DatabaseAuthorizationError, DatabaseError
from tests.test_discovery_history_repository import _prepare_scope, _record
from tests.test_analytics_api import analytics, get
from tests.test_discovery_history_api_behavior import workspace


def limits(**overrides):
    values = dict(deadline=time.monotonic() + 10, events=500, bytes=16 * 1024 * 1024,
                  snapshot_bytes=8 * 1024 * 1024)
    values.update(overrides)
    return AnalyticsReadLimits(**values)


@pytest.mark.parametrize('old_version', ['unledgered-v1', 'ledger-11'])
def test_upgrade_preserves_raw_h_s_p_and_revision_json(tmp_path, old_version):
    from app.database import migrations
    from app.api.schemas import TenderDiscoveryItem
    from app.database.repository import TenderRepository
    from app.analytics.fit import VerifiedFitContext, classify_discovery_fit
    from tests.test_analytics_service import item
    from dataclasses import asdict
    from app.sources.models import TenderNotice
    database = Database(DatabaseSettings('', tmp_path / 'upgrade.db'))
    if old_version == 'unledgered-v1':
        with closing(database.connect()) as conn, conn:
            conn.executescript(next(m.sql for m in MIGRATIONS if m.domain == 'tenders'))
            conn.execute("INSERT INTO schema_meta VALUES('schema_version','1')")
    else:
        # Genuine preceding migration ledger/schema, without the later domains.
        with patch.object(migrations, 'MIGRATIONS', MIGRATIONS[:11]):
            database.migrate()
    old_item = item('old', 65)
    for field in ('enrichment', 'preliminary_provenance', 'analysis_stage'):
        old_item.pop(field)
    legacy_saved = json.dumps(old_item, ensure_ascii=False)
    legacy = json.dumps(dict(items=[old_item], legacy_unknown={'raw': 'unchanged'}))
    old_notice = asdict(TenderNotice('ted', 'old', 'Legacy notice', 'https://example.test/old'))
    old_notice.pop('enrichment')
    legacy_revision = json.dumps(old_notice)
    with closing(database.connect()) as conn, conn:
        conn.execute('INSERT INTO discovery_search_history VALUES(1,7,33,101,1,1,?,?,?,0,0,?,?)',
                     ('[]', '[]', '[]', legacy, '2026-01-01T00:00:00+00:00'))
        conn.execute('INSERT INTO saved_opportunities VALUES(1,7,33,?,?,?,?,?)',
                     ('ted', 'old', legacy_saved, '2026-01-01', '2026-01-01'))
        conn.execute('INSERT INTO tenders VALUES(1,101,101,?,?,2,10,?,NULL,0,?,?)',
                     ('a' * 64, 'old.pdf', '{"title":"legacy"}', '2026-01-01', '2026-01-01'))
        if old_version == 'ledger-11':
            conn.execute('INSERT INTO scoring_public_revisions VALUES(?,?,?,?,?)',
                         ('b' * 64, 'ted', 'old', legacy_revision, 'legacy-adapter'))
        tables = ['discovery_search_history', 'saved_opportunities', 'tenders']
        if old_version == 'ledger-11':
            tables.append('scoring_public_revisions')
        before = {t: conn.execute('SELECT * FROM ' + t).fetchall() for t in tables}
    database.migrate()
    database.migrate()  # Idempotent existing-version bootstrap.
    with closing(database.connect()) as conn:
        assert {t: conn.execute('SELECT * FROM ' + t).fetchall() for t in tables} == before
        assert [tuple(row) for row in conn.execute('SELECT version,domain,checksum FROM app_schema_migrations ORDER BY version')] == [
            (m.version, m.domain, m.checksum) for m in MIGRATIONS]
        assert conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0] == '1'
        decoded = TenderDiscoveryItem.model_validate_json(conn.execute('SELECT snapshot_json FROM saved_opportunities').fetchone()[0])
        assert decoded.enrichment is None and decoded.preliminary_provenance is None
        assert 'analysis_stage' not in decoded.model_fields_set
        assert not classify_discovery_fit(decoded, context=VerifiedFitContext(7, 33, 'a' * 64, True), historical=True).eligible
        assert TenderDiscoveryItem.model_validate(json.loads(legacy)['items'][0]) == decoded
        new_body = item('new', 65)
        encoded = json.dumps(dict(items=[new_body]))
        conn.execute('INSERT INTO discovery_search_history VALUES(2,7,33,101,1,1,?,?,?,0,0,?,?)',
                     ('["ted"]', '["ted"]', '[]', encoded, '2026-10-01T00:00:00+00:00'))
        new_decoded = TenderDiscoveryItem.model_validate(json.loads(conn.execute(
            'SELECT snapshot_json FROM discovery_search_history WHERE id=2').fetchone()[0])['items'][0])
        assert new_decoded.enrichment.model_dump() == new_body['enrichment']
        assert new_decoded.preliminary_provenance.model_dump() == new_body['preliminary_provenance']
        conn.commit()
    assert TenderRepository(database).find_by_id(101, 1).analysis.title == 'legacy'
    database.close()


def test_fresh_schema_and_unknown_upgrade_fail_without_mutation(tmp_path):
    database = Database(DatabaseSettings('', tmp_path / 'fresh.db'))
    database.migrate()
    with closing(database.connect()) as conn, conn:
        assert conn.execute('SELECT COUNT(*) FROM app_schema_migrations').fetchone()[0] == 14
        conn.execute("UPDATE schema_meta SET value='future' WHERE key='schema_version'")
        before = conn.execute('SELECT * FROM app_schema_migrations').fetchall()
    with pytest.raises(StorageError, match='Unsupported legacy'):
        database.migrate()
    with closing(database.connect()) as conn, conn:
        assert conn.execute('SELECT * FROM app_schema_migrations').fetchall() == before
        conn.execute("UPDATE schema_meta SET value='1' WHERE key='schema_version'")
        conn.execute("UPDATE app_schema_migrations SET checksum='changed' WHERE version=4")
        before = conn.execute('SELECT * FROM app_schema_migrations').fetchall()
    with pytest.raises(StorageError, match='Unsupported or changed'):
        database.migrate()
    with closing(database.connect()) as conn:
        assert conn.execute('SELECT * FROM app_schema_migrations').fetchall() == before
    database.close()


@pytest.mark.parametrize('field,value,cap', [
    ('snapshot_json', 'x' * 1025, dict(snapshot_bytes=1024)),
    ('snapshot_json', 'é' * 513, dict(snapshot_bytes=1024)),
    ('snapshot_json', 'x\0' + 'x' * 1024, dict(snapshot_bytes=1024)),
    ('failed_sources_json', 'x' * 1025, dict(bytes=1024)),
])
def test_size_preflight_rejects_before_deserialization(tmp_path, field, value, cap):
    repo = _prepare_scope(tmp_path / 'sizes.db')
    record = _record(repo, company_id=33, result_count=0, snapshot='{}')
    with sqlite3.connect(repo.path) as conn:
        conn.execute('UPDATE discovery_search_history SET ' + field + '=? WHERE id=?', (value, record.id))
    with patch.object(repo, '_deserialize_discovery_search_history', side_effect=AssertionError('body materialized')):
        with pytest.raises(DatabaseError):
            repo.page_discovery_history(101, 7, 33, read_limits=limits(**cap))
        with pytest.raises(DatabaseAuthorizationError):
            repo.page_discovery_history(999, 7, 33, read_limits=limits(**cap))
    # Original retrieval continues to return the exact stored bytes.
    assert getattr(repo.page_discovery_history(101, 7, 33)['records'][0], field) == value


def test_population_byte_and_event_caps_and_existing_index(tmp_path):
    repo = _prepare_scope(tmp_path / 'population.db')
    for _ in range(3):
        _record(repo, company_id=33, result_count=0, snapshot='x' * 500)
    for cap in (dict(events=2), dict(bytes=1200, snapshot_bytes=1000)):
        with patch.object(repo, '_deserialize_discovery_search_history', side_effect=AssertionError('body materialized')):
            with pytest.raises(DatabaseError):
                repo.page_discovery_history(101, 7, 33, read_limits=limits(**cap))
    assert len(repo.page_discovery_history(101, 7, 33, read_limits=limits())['records']) == 3
    with sqlite3.connect(repo.path) as conn:
        plan = conn.execute('EXPLAIN QUERY PLAN SELECT * FROM discovery_search_history '
            'WHERE organization_id=? AND company_id=? AND id<=? AND created_at<=? '
            'ORDER BY created_at DESC,id DESC LIMIT ?', (7, 33, 100, '2027', 21)).fetchall()
    assert any('idx_discovery_search_history_scope' in row[3] for row in plan)
    assert not any('TEMP B-TREE' in row[3] for row in plan)


def test_sql_execution_interruption_and_connection_read_only(tmp_path):
    with closing(sqlite3.connect(tmp_path / 'interrupt.db')) as conn:
        conn.execute('CREATE TABLE intact(id INTEGER)')
        conn.commit()
        with bounded_read(conn, limits()):
            with pytest.raises(sqlite3.OperationalError, match='readonly'):
                conn.execute('INSERT INTO intact VALUES(1)')
        # Deterministic progress clock, actual SQLite VM cancellation, no sleep.
        read_limits = limits(deadline=1)
        with patch('app.database.analytics_read.time.monotonic', side_effect=[0, 2]):
            with bounded_read(conn, read_limits):
                with pytest.raises(sqlite3.OperationalError, match='interrupted'):
                    conn.execute('WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<1000000) '
                                 'SELECT SUM(x) FROM n').fetchone()
        assert conn.execute('SELECT COUNT(*) FROM intact').fetchone()[0] == 0


def test_unverified_backend_is_explicitly_blocked_without_sql():
    from unittest.mock import Mock
    conn = Mock()
    with pytest.raises(StorageError, match='not verified'):
        with bounded_read(conn, limits()):
            raise AssertionError('Unsupported backend accepted')
    assert conn.mock_calls == []


@pytest.mark.parametrize('body', ['{bad', '{"items":[],"items":[]}', '{"items":[NaN]}',
                                  '{"items":null}', '[1]', '{"items":' + '[' * 1100 + '0' + ']' * 1100 + '}'],
                         ids=['syntax', 'duplicate-keys', 'nonfinite', 'null-items', 'root-list', 'deep-json'])
def test_malformed_legacy_api_payload_is_503_and_redacted(analytics, body):
    w, repo, company, base, persist, record = analytics
    with sqlite3.connect(repo.path) as conn:
        conn.execute('UPDATE discovery_search_history SET snapshot_json=? WHERE id=?', (body, record.id))
    response = get(w, base)
    assert response.status_code == 503
    assert w.client.app.state.api_settings.api_key not in response.text
    assert body not in response.text


def test_mixed_policy_legacy_and_new_rows_do_not_invent_current_proof(analytics):
    from tests.test_analytics_service import item
    w, repo, company, base, persist, record = analytics
    legacy, future, current = item('legacy', 65), item('future', 65), item('current', 65)
    legacy.pop('preliminary_provenance')
    legacy.pop('analysis_stage')
    legacy.pop('enrichment')
    future['preliminary_provenance']['scoring_policy_version'] = 'future-policy'
    future['enrichment']['classification']['version'] = 'future-taxonomy'
    for entry in (future, current):
        entry['preliminary_provenance']['organization_id'] = w.organization.id
        entry['preliminary_provenance']['company_id'] = company
    persist([legacy, future, current])
    result = get(w, base)
    assert result.status_code == 200, result.text
    rows = {r['identity'][1]: r for r in result.json()['rows']}
    assert rows['legacy']['historical_fit_band'] == rows['future']['historical_fit_band'] == 'unknown'
    assert rows['current']['historical_fit_band'] == 'high'
    assert all(rows[name]['current_fit_band'] == 'unknown' for name in ('legacy', 'future', 'current'))
    assert ['ted', 'legacy'] not in result.json()['drilldowns']['Countries']
    assert ['ted', 'future'] not in result.json()['drilldowns']['Countries']


def test_token_invalidation_on_signing_rotation_and_session_logout(analytics):
    from dataclasses import replace
    w, repo, company, base, persist, record = analytics
    token = get(w, base).json()['population_token']
    settings = w.client.app.state.api_settings
    w.client.app.state.api_settings = replace(settings, api_key='synthetic-rotated-key')
    try:
        assert get(w, base, population_token=token).status_code == 422
    finally:
        w.client.app.state.api_settings = settings
    assert w.client.post('/api/v1/auth/logout').status_code in (200, 204)
    assert get(w, base, population_token=token).status_code == 401


def test_api_size_gate_precedes_body_materialization(analytics):
    w, repo, company, base, persist, record = analytics
    with patch('app.api.analytics_routes.MAX_BYTES', 1), patch.object(
            repo, '_deserialize_discovery_search_history', side_effect=AssertionError('body materialized')):
        response = get(w, base)
    assert response.status_code == 503
    assert 'snapshot_json' not in response.text


def test_stored_source_errors_and_future_extras_never_escape_allowlist(analytics):
    import base64
    w, repo, company, base, persist, record = analytics
    marker = 'synthetic-credential-payload-must-not-escape'
    with sqlite3.connect(repo.path) as conn:
        body = json.loads(record.snapshot_json)
        body['source_statuses'] = [{'source': 'ted', 'state': 'healthy', 'error': marker}]
        body['items'][0]['preliminary_provenance']['future_extra'] = marker
        conn.execute('UPDATE discovery_search_history SET snapshot_json=? WHERE id=?', (json.dumps(body), record.id))
    response = get(w, base)
    assert response.status_code == 200, response.text
    assert marker not in response.text
    token = response.json()['population_token']
    assert marker.encode() not in base64.urlsafe_b64decode(token + '=' * (-len(token) % 4))


def test_guarded_runner_blocks_network_variants_and_dotenv_before_io():
    """Assert audit enforcement in its own interpreter, without real network I/O.

    Production offline workers install an audit hook in their child process.
    A regular CI pytest process does not, so external socket connects here
    would be both unsafe and slow. Exercise the real guard after installing it
    in a disposable child interpreter, including actual socket construction.
    """
    import subprocess
    import sys
    from pathlib import Path

    child = r"""
import socket
import sys
from app.analytics.offline_worker import guard

sys.addaudithook(guard)
try:
    socket.socket()
except RuntimeError as exc:
    assert str(exc) == "forbidden"
else:
    raise AssertionError("socket construction was allowed")

for event, args in [
    ("socket.connect", (None, ("192.0.2.1", 9))),
    ("socket.connect_ex", (None, ("192.0.2.1", 9))),
    ("socket.sendto", (None, ("192.0.2.1", 9))),
    ("socket.getaddrinfo", ("external.invalid", 443, 0, 0, 0)),
    ("socket.gethostbyname", ("external.invalid",)),
    ("socket.gethostbyaddr", ("192.0.2.1",)),
    ("subprocess.Popen", ("forbidden", [], None, {})),
]:
    try:
        sys.audit(event, *args)
    except RuntimeError as exc:
        assert str(exc) == "forbidden"
    else:
        raise AssertionError("audit event unexpectedly allowed: " + event)

for path in ("C:/synthetic/.env", "C:/synthetic/.env.test",
             "C:/synthetic/.ENV", "C:/synthetic/.env.",
             "C:/synthetic/.env ", "C:/synthetic/.env:stream"):
    try:
        sys.audit("open", path, "r", 0)
    except RuntimeError as exc:
        assert str(exc) == "forbidden"
    else:
        raise AssertionError("dotenv audit event unexpectedly allowed")
"""
    result = subprocess.run(
        [sys.executable, "-c", child],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, "Isolated audit-guard enforcement failed"


def test_existing_source_fixtures_reach_authorized_api_and_exact_replay(analytics):
    from types import SimpleNamespace
    from app.api.organization_workflow_routes import _discovery_item
    from app.scoring.models import CompanyProfile
    from app.sources.austender_rss import parse_austender_detail_page, AUSTENDER_ATM_BASE_URL
    from tests.test_austender_source import _detail_html, UUID_1
    from tests.test_analytics_normalization import sam
    w, repo, company, base, persist, record = analytics
    notices = [sam(), parse_austender_detail_page(_detail_html(), external_id=UUID_1,
        url=AUSTENDER_ATM_BASE_URL + UUID_1, rss_title='ISO 9001 Certification Services')]
    profile = CompanyProfile.model_validate(w.profile('Analytics'))
    entries = [_discovery_item(SimpleNamespace(notice=n, reasons=[]), profile,
        organization_id=w.organization.id, company_id=company).model_dump(mode='json') for n in notices]
    with sqlite3.connect(repo.path) as conn:
        conn.execute('DELETE FROM discovery_search_history')
    persist(entries, attempted_sources_json='["sam_gov","austender"]',
            successful_sources_json='["sam_gov","austender"]')
    data = get(w, base).json()
    assert data['kpis']['Discovered']['value'] == 2
    assert data['kpis']['Active Sources']['value'] == 2
    assert data['kpis']['Countries']['value'] == 1
    assert data['drilldowns']['Countries'] == [['sam_gov', 'abc123def456']]
    for filters, identity in [(dict(country='US'), ['sam_gov', 'abc123def456']),
                              (dict(category='austender-category/80100000'), ['austender', UUID_1])]:
        response = get(w, base, **filters)
        assert response.status_code == 200, response.text
        selected = response.json()
        assert selected['kpis']['Discovered']['value'] == selected['total'] == 1
        assert selected['drilldowns']['Discovered'] == [identity]
        replay = get(w, base, 'history/replay', population_token=selected['population_token'], **filters)
        assert replay.status_code == 200, replay.text
        assert replay.json()['population'] == selected['population']
        assert replay.json()['rows'] == selected['rows']
        assert replay.json()['kpis'] == selected['kpis']


def test_unsigned_deep_tokens_and_utc_overflow_are_422(analytics):
    import base64
    w, repo, company, base, persist, record = analytics
    hostile = b'x' * 32 + b'[' * 12000 + b'0' + b']' * 12000
    token = base64.urlsafe_b64encode(hostile).decode().rstrip('=')
    assert get(w, base, population_token=token).status_code == 422
    for instant in ('9999-12-31T23:59:59-23:59', '0001-01-01T00:00:00+23:59'):
        assert get(w, base, start=instant).status_code == 422
        assert get(w, base, end=instant).status_code == 422
