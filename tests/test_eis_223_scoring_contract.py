"""Offline scoring compatibility, not end-to-end eis_223 activation.

Use authorized ted notices with synthetic subclass provenance and the existing
real SQLite/auth/queue fixture. No adapter or source registration is changed.
"""
import json
from contextlib import closing
from dataclasses import asdict

import pytest

from app.jobs import JobScope
from app.jobs.worker import PermanentJobError
from app.scoring.runs import SOURCE_IDS, ScoringAccessError, ScoringInputError, digest
from app.scoring.preview import score_metadata_preview
from app.services.tender_analysis import analysis_from_notice
from test_scoring_workers import offline, system, enqueue, run, claim, context, count, notice


EXTRAS = {'requested_law': '223-FZ', 'observed_law': '223-FZ',
          'feed_url': 'https://example.test/synthetic-feed', 'raw_guid': 'synthetic'}


def stored(s, table):
    assert table in {'source_opportunities', 'scoring_public_revisions'}
    with closing(s.database.connect()) as conn:
        return conn.execute(f'SELECT notice_json FROM {table}').fetchone()[0]


def write_notice(s, table, encoded):
    assert table in {'source_opportunities', 'scoring_public_revisions'}
    with closing(s.database.connect()) as conn, conn:
        conn.execute(f'UPDATE {table} SET notice_json=?', (encoded,))


@pytest.mark.parametrize('table', ['source_opportunities', 'scoring_public_revisions'])
def test_extra_fields_real_scoring_paths_preserve_identity_and_storage(system, table):
    s = system
    baseline = enqueue(s)
    original = stored(s, table)
    augmented = json.dumps({**json.loads(original), **EXTRAS})
    write_notice(s, table, augmented)
    # Enqueue exercises source reconstruction; worker exercises revision reconstruction.
    assert enqueue(s).id == baseline.id
    with closing(s.database.connect()) as conn:
        revision = conn.execute('SELECT revision FROM scoring_public_revisions').fetchone()[0]
    assert revision == digest([asdict(notice()), 'connector-sync-v1:ted:adapter-r1'])
    assert run(s)
    view = s.service.view(baseline.id, scope=s.scope)
    assert view['complete'] and view['result_count'] == 1 and count(s) == 1
    expected = score_metadata_preview(analysis_from_notice(notice()), s.profile)
    assert view['items'][0]['scoring'] == expected.model_dump(
        mode='json', exclude={'profile_name', 'profile_version'})
    assert stored(s, table) == augmented
    assert enqueue(s).id == baseline.id
    assert not any(key in json.dumps(view) for key in EXTRAS)
    for scope in (JobScope(s.accounts[4].id, s.other_org.id, s.other_company.id),
                  JobScope(s.accounts[0].id, s.org.id, s.second_company.id),
                  JobScope(s.accounts[1].id, s.org.id, s.company.id)):
        with pytest.raises(ScoringAccessError):
            s.service.view(baseline.id, scope=scope)


@pytest.mark.parametrize('table', ['source_opportunities', 'scoring_public_revisions'])
@pytest.mark.parametrize('corruption', ['missing_source', 'missing_external_id', 'missing_title',
                                      'missing_url', 'invalid_title', 'wrong_source',
                                      'invalid_url', 'changed_title', 'bad_json', 'array', 'null'])
def test_corrupt_base_fields_still_rejected(system, table, corruption):
    s = system
    job = enqueue(s)
    payload = {**json.loads(stored(s, table)), **EXTRAS}
    if corruption.startswith('missing_'):
        del payload[corruption.removeprefix('missing_')]
    elif corruption == 'invalid_title':
        payload['title'] = None
    elif corruption == 'wrong_source':
        payload['source'] = 'eis'
    elif corruption == 'invalid_url':
        payload['url'] = 'file:///invalid'
    elif corruption == 'changed_title':
        payload['title'] = 'Supply of aluminium revised'
    encoded = {'bad_json': '{', 'array': '[]', 'null': 'null'}.get(corruption, json.dumps(payload))
    write_notice(s, table, encoded)
    if table == 'source_opportunities':
        if corruption == 'changed_title':
            # Valid changed base fields must create a new snapshot/revision.
            assert enqueue(s).id != job.id
        else:
            with pytest.raises((TypeError, ValueError)):
                enqueue(s)
    else:
        leased = claim(s)
        with pytest.raises(PermanentJobError):
            s.handler(context(s, leased), job.payload)
    assert count(s) == 0
    assert stored(s, table) == encoded


def test_eis_223_remains_unregistered(system):
    assert 'eis_223' not in SOURCE_IDS
    with pytest.raises(ScoringInputError):
        enqueue(system, sources=['eis_223'])
