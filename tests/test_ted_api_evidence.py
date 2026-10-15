"""Real public capture proof; fabricated mutations below are negative cases only."""
import asyncio
import copy
import json
from pathlib import Path

import pytest

from app.analytics.cpv import validate_cpv
from app.sources.enrichment import validate_enrichment
from app.sources.ted_api import TED_FIELDS, TED_SEARCH_URL, TedApiSource, parse_ted_search_response
from scripts.verify_ted_api_sample import CONTEXT_FIELDS, inspect


FIXTURE = Path(__file__).with_name('fixtures') / 'ted_public_search_sample.json'


def sample():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def test_pinned_capture_equals_sanitized_fixture():
    """Verify immutable committed evidence, and full raw provenance when available.

    The three raw TED captures are NOT in Git: a fresh CI runner cannot
    independently attest those upstream bytes. Do not silently substitute
    fabricated raw API replies or imply full original-source verification.
    """
    import hashlib
    import warnings
    raw_fixture = FIXTURE.read_bytes()
    blob = b'blob ' + str(len(raw_fixture)).encode('ascii') + b'\0' + raw_fixture
    assert hashlib.sha1(blob).hexdigest() == '448b008588086cd03bf2ff50c8fa375e6d6ae5a8'
    data = json.loads(raw_fixture)
    assert data == sample()
    assert data['openapi_sha256'] == 'e0cfe4e84123c3b62118ca99e07e8b9a09467494846280b8c7e60d700fbd2ff8'
    assert data['response_sha256'] == '8246a105bea0e0603a2669bbc99a2098df704870449060c827bf7973c6585b81'
    assert data['request_sha256'] == '5a9f4cbd84cf8d2a5d384a858fdcfe03ac563738868073a26e4831abc69d8c0f'
    assert data['extraction_status'] == 'blocked_entity_scope'
    assert data['context_binding'] == 'unproven; aggregate across Procedure/Part/Lot'
    assert data['removed_fields'] == ['notices[].links']
    tampered = raw_fixture.replace(b'392803-2016', b'392803-2017', 1)
    assert tampered != raw_fixture
    assert hashlib.sha1(b'blob ' + str(len(tampered)).encode('ascii') + b'\0' + tampered).hexdigest() != '448b008588086cd03bf2ff50c8fa375e6d6ae5a8'

    directory = Path('.cache/phase24p33-ted-evidence')
    names = ('ted-api-v3.yaml', 'request.json', 'public-search-response.json')
    if directory.is_dir():
        raw = [directory.joinpath(name).read_bytes() for name in names]
        assert inspect(*raw) == data
        for index in (0, 2):
            changed = raw.copy()
            changed[index] += b'changed'
            with pytest.raises(ValueError, match='checksum'):
                inspect(*changed)
    else:
        warnings.warn(
            'Raw TED capture not present: committed sanitized fixture verified, '
            'but original upstream bytes need independent provenance review before merge.',
            RuntimeWarning, stacklevel=2,
        )


def test_nonempty_actual_values_prove_only_aggregate_shape():
    data = sample()
    assert data['request']['query'] == 'classification-cpv = 45000000'
    assert data['request']['scope'] == 'ACTIVE'
    assert data['response']['totalNoticeCount'] == 108760
    assert data['response']['iterationNextToken'] is None
    assert data['response']['timedOut'] is False
    assert [(row['publication-number'], row['classification-cpv']) for row in data['response']['notices']] == [
        ('392803-2016', ['45000000', '45200000', '45440000']),
        ('392804-2016', ['45000000', '45200000', '45310000']),
        ('392805-2016', ['45000000', '45200000', '45261000']),
    ]
    assert len({code for row in data['response']['notices'] for code in row['classification-cpv']}) == 5
    for row in data['response']['notices']:
        assert all(validate_cpv(code) == 'verified' for code in row['classification-cpv'])
        assert all(field not in row for field in CONTEXT_FIELDS)


def test_real_old_notices_parse_without_promoting_aggregate_to_tender_claim():
    payload = sample()['response']
    original = copy.deepcopy(payload)
    notices = parse_ted_search_response(payload)
    assert payload == original
    assert [notice.external_id for notice in notices] == [row['publication-number'] for row in payload['notices']]
    for notice in notices:
        assert notice.title == f'TED notice {notice.external_id}'
        assert notice.published_at is notice.deadline is notice.currency is None
        assert notice.enrichment['country']['codes'] == []
        assert notice.enrichment['classification']['entries'] == []
        assert notice.enrichment['classification']['memberships'] == []
        validate_enrichment(notice.enrichment, notice.source, notice.external_id)


@pytest.mark.parametrize('value', [None, [], '45000000', 45000000, True,
    ['45000000', '45000000'], ['45000000', '45200000'],
    ['00000000', '45000000-7'], [['45000000']],
    {'LOT-0001': ['45000000'], 'LOT-0002': ['03111100']}])
def test_missing_malformed_duplicates_and_unproven_lot_bindings_not_guessed(value):
    raw = {'publication-number': 'negative-only', 'classification-cpv': value,
           **{field: value for field in CONTEXT_FIELDS},
           'internal-identifier-lot': ['LOT-0001', 'LOT-0002']}
    notice = parse_ted_search_response({'notices': [raw]})[0]
    assert notice.enrichment['classification']['memberships'] == []
    assert notice.enrichment['classification']['entries'] == []
    raw.pop('classification-cpv')
    assert parse_ted_search_response({'notices': [raw]})[0].enrichment['classification']['status'] == 'missing'


def test_capture_fetch_uses_one_existing_request_and_never_follows_links(monkeypatch):
    calls = []
    class Response:
        content = b'{}'
        def raise_for_status(self):
            pass
        def json(self):
            # Exercise the pinned public sample without requiring local-only .cache.
            return sample()['response']
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, *, json):
            calls.append((url, json))
            return Response()
    monkeypatch.setattr('app.sources.ted_api.source_client', Client)
    assert len(asyncio.run(TedApiSource().fetch(limit=3))) == 3
    assert len(calls) == 1 and calls[0][0] == TED_SEARCH_URL
    assert calls[0][1]['fields'] == list(TED_FIELDS)
    assert not set(('classification-cpv', *CONTEXT_FIELDS)).intersection(TED_FIELDS)


def test_real_capture_history_saved_auth_and_workspace_isolation():
    from app.database.repository import TenderRepository
    from tests.test_organization_workflows import OrganizationWorkflowTests
    helper = OrganizationWorkflowTests()
    helper.setUp()
    try:
        helper.as_account(helper.owner)
        first = helper.create_company('TED Supplier', 'TED')
        repository = TenderRepository(helper.path)
        repository.initialize()
        helper.client.app.state.runtime.tender_repository = repository
        helper.catalog.notices = tuple(parse_ted_search_response(sample()['response']))
        response = helper.client.post(helper.base('/discover/tenders'))
        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body['items']) == 3
        item = body['items'][0]
        assert item['enrichment']['classification']['memberships'] == []
        history = helper.base(f"/discovery/history/{body['history_id']}")
        calls = len(helper.catalog.calls)
        assert helper.client.get(history).json()['discovery']['items'] == body['items']
        saved = helper.client.post(helper.base('/shortlist'), json=item)
        assert saved.status_code in (200, 201), saved.text
        assert helper.client.get(helper.base('/shortlist')).json()[0]['opportunity'] == item
        second = helper.create_company('Other TED Supplier', 'TED')
        assert helper.client.post(helper.base(f"/companies/{second['id']}/activate")).status_code == 200
        assert helper.client.get(history).status_code == 404
        assert helper.client.get(helper.base('/discovery/history')).json() == []
        assert helper.client.get(helper.base('/shortlist')).json() == []
        assert helper.client.post(helper.base(f"/companies/{first['id']}/activate")).status_code == 200
        assert helper.client.get(history).status_code == 200
        helper.as_account(helper.viewer)
        assert helper.client.get(history).status_code == 200
        assert helper.client.post(helper.base('/shortlist'), json=item).status_code == 403
        helper.as_account(helper.outsider)
        assert helper.client.get(history).status_code == 403
        assert helper.client.get(helper.base('/shortlist')).status_code == 403
        assert helper.client.post(helper.base('/discover/tenders')).status_code == 403
        helper.client.cookies.clear()
        assert helper.client.get(history).status_code == 401
        assert helper.client.get(helper.base('/shortlist')).status_code == 401
        assert len(helper.catalog.calls) == calls
    finally:
        helper.doCleanups()
