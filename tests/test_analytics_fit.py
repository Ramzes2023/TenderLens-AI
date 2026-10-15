"""Offline eligibility, immutable evidence and authorized snapshot regressions."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.analytics.fit import (
    FIT_POLICY_VERSION, PREVIEW_ENGINE_VERSION, PreviewProvenance,
    VerifiedFitContext, classify_discovery_fit, classify_preliminary_fit,
)
from app.api.organization_workflow_routes import _discovery_item
from app.api.schemas import TenderDiscoveryItem
from app.scoring.models import CompanyProfile
from app.scoring.runs import profile_digest
from app.sources.models import TenderNotice


def profile():
    return CompanyProfile(profile_version='fixture-v1', company_name='Same name',
                          product_keywords=['pumps'])


def item():
    return _discovery_item(SimpleNamespace(notice=TenderNotice(
        source='ted', external_id='fit-1', title='Supply of pumps',
        url='https://example.test/fit'), reasons=[]), profile(),
        organization_id=1, company_id=2)


def context(**updates):
    values = dict(organization_id=1, company_id=2,
        current_profile_digest=profile_digest(profile()), trusted_snapshot=True)
    values.update(updates)
    return VerifiedFitContext(**values)


def classify(score, **kwargs):
    values = dict(stage='metadata_preview', provenance=item().preliminary_provenance,
                  context=context())
    values.update(kwargs)
    return classify_preliminary_fit(score, **values)


@pytest.mark.parametrize('score,band,matched,high', [
    (0, 'low', False, False), (34.9, 'low', False, False),
    (35, 'medium', True, False), (64.9, 'medium', True, False),
    (65, 'high', True, True), (90, 'high', True, True),
])
def test_exact_boundaries(score, band, matched, high):
    result = classify(score)
    assert result.eligible and result.raw_score == score
    assert (result.band, result.matched, result.high_fit) == (band, matched, high)
    assert result.policy_version == FIT_POLICY_VERSION


@pytest.mark.parametrize('score', [-1, 90.01, None, float('nan'), float('inf'),
    float('-inf'), True, False, '65', '', [], {}, Decimal('65'), complex(65), 10**400],
    ids=['negative', 'over90', 'missing', 'nan', 'inf', 'minusinf', 'true', 'false',
         'string', 'empty', 'list', 'dict', 'decimal', 'complex', 'hugeint'])
def test_invalid_scores_are_unknown_never_zero(score):
    result = classify(score)
    assert result.raw_score is score
    assert not result.eligible and result.band == 'unknown'
    assert result.matched is None and result.high_fit is None


@pytest.mark.parametrize('field,value', [
    ('engine_version', 'scoring-engine-v1'), ('scoring_policy_version', 'future-v2'),
    ('scoring_stage', 'full_document'), ('organization_id', 9), ('company_id', 9),
    ('profile_digest', ''), ('profile_digest', 'a'*64), ('scored_at', ''),
    ('scored_at', '2026-10-11T10:00:00'),
])
def test_current_provenance_conflicts(field, value):
    provenance = item().preliminary_provenance.model_copy(update={field: value})
    assert not classify(65, provenance=provenance).eligible


@pytest.mark.parametrize('stage', [None, '', 'full_document', 'unknown'])
def test_stage_mixing(stage):
    assert not classify(65, stage=stage).eligible


def test_digest_is_existing_canonical_digest_and_changes_with_profile():
    original = profile()
    reordered = CompanyProfile.model_validate(dict(reversed(list(original.model_dump().items()))))
    assert profile_digest(original) == profile_digest(reordered)
    for field, value in [('product_keywords', ['valves']), ('profile_version', 'v2'),
                         ('max_contract_value', 100), ('hard_stop_on_currency', False)]:
        assert profile_digest(original.model_copy(update={field: value})) != profile_digest(original)


def test_legacy_snapshot_and_full_document_are_separate():
    current = item()
    raw = current.model_dump(mode='json')
    del raw['preliminary_provenance']
    legacy = TenderDiscoveryItem.model_validate(raw)
    assert legacy.preliminary_provenance is None
    assert not classify_discovery_fit(legacy, context=context()).eligible
    historical = classify_discovery_fit(legacy, context=context(), historical=True)
    assert historical.eligible and historical.basis == 'historical preview at search time'
    del raw['analysis_stage']
    assert not classify_discovery_fit(TenderDiscoveryItem.model_validate(raw),
                                      context=context(), historical=True).eligible
    current.full_scoring = current.preliminary_scoring.model_copy(update={'fit_score': 100})
    current.full_ai_analyzed = True
    current.preliminary_scoring = current.preliminary_scoring.model_copy(update={'fit_score': 0})
    current.preliminary_scoring.stop_factors = ['Currency mismatch']
    assert classify_discovery_fit(current, context=context()).band == 'low'
    assert current.full_scoring.fit_score == 100
    assert current.preliminary_scoring.stop_factors == ['Currency mismatch']
    current.preliminary_scoring = current.preliminary_scoring.model_copy(update={'fit_score': 90})
    assert classify_discovery_fit(current, context=context()).high_fit is True
    assert current.preliminary_scoring.stop_factors == ['Currency mismatch']


def test_historical_stale_digest_and_versions_and_saved_trust():
    old = item().preliminary_provenance.model_copy(update={'profile_digest': 'a'*64})
    assert classify(65, provenance=old, historical=True).eligible
    assert not classify(65, provenance=None).eligible
    assert not classify(65, context=context(current_profile_digest='')).eligible
    assert not classify(65, provenance=item().preliminary_provenance.model_dump()).eligible
    assert not classify(65, historical=True, context=None).eligible
    assert not classify(65, context=VerifiedFitContext(1, 2, profile_digest(profile()))).eligible
    assert not classify(65, provenance=old.model_copy(update={
        'scoring_policy_version': 'future'}), historical=True).eligible
    evidence = item().preliminary_provenance
    with pytest.raises(ValidationError):
        evidence.profile_digest = 'b'*64
    raw = evidence.model_dump()
    raw['future_field'] = 'retained'
    assert PreviewProvenance.model_validate(raw).model_dump()['future_field'] == 'retained'


def test_new_discovery_history_roles_scope_and_read_stability():
    from app.database.repository import TenderRepository
    from tests.test_organization_workflows import OrganizationWorkflowTests
    helper = OrganizationWorkflowTests()
    helper.setUp()
    try:
        helper.as_account(helper.owner)
        first = helper.create_company('Same name', 'aluminium')
        repository = TenderRepository(helper.path)
        repository.initialize()
        helper.client.app.state.runtime.tender_repository = repository
        before = datetime.now(timezone.utc)
        response = helper.client.post(helper.base('/discover/tenders'))
        assert response.status_code == 200, response.text
        body = response.json()
        discovery_item = TenderDiscoveryItem.model_validate(body['items'][0])
        p = discovery_item.preliminary_provenance
        assert before <= datetime.fromisoformat(p.scored_at) <= datetime.now(timezone.utc)
        assert p.profile_digest == profile_digest(CompanyProfile.model_validate(first['profile']))
        assert p.engine_version == PREVIEW_ENGINE_VERSION
        authorized = VerifiedFitContext(helper.organization.id, first['id'], p.profile_digest, True)
        assert classify_discovery_fit(discovery_item, context=authorized).eligible
        url = helper.base(f"/discovery/history/{body['history_id']}")
        calls = len(helper.catalog.calls)
        for account in (helper.owner, helper.member, helper.viewer):
            helper.as_account(account)
            one = helper.client.get(url)
            two = helper.client.get(url)
            assert one.status_code == two.status_code == 200
            assert one.json() == two.json()
            assert one.json()['discovery']['items'] == body['items']
            assert len(helper.client.get(helper.base('/discovery/history')).json()) == 1
        helper.as_account(helper.owner)
        saved = helper.client.post(helper.base('/shortlist'), json=body['items'][0])
        assert saved.status_code in (200, 201)
        assert helper.client.get(helper.base('/shortlist')).json()[0]['opportunity'] == body['items'][0]
        second = helper.create_company('Other workspace', 'aluminium')
        # Same serialized profile cannot bind a result to a different company ID.
        assert helper.client.patch(helper.base(f"/companies/{second['id']}"),
            json={'profile': first['profile']}).status_code == 200
        helper.client.post(helper.base(f"/companies/{second['id']}/activate"))
        assert helper.client.get(url).status_code == 404
        assert helper.client.get(helper.base('/discovery/history')).json() == []
        assert helper.client.get(helper.base('/shortlist')).json() == []
        switched = VerifiedFitContext(helper.organization.id, second['id'], p.profile_digest, True)
        assert not classify_discovery_fit(discovery_item, context=switched).eligible
        helper.client.post(helper.base(f"/companies/{first['id']}/activate"))
        changed = dict(first['profile'], product_keywords=['valves'])
        patch = helper.client.patch(helper.base(f"/companies/{first['id']}"), json={'profile': changed})
        assert patch.status_code == 200, patch.text
        stale = VerifiedFitContext(helper.organization.id, first['id'],
            profile_digest(CompanyProfile.model_validate(patch.json()['profile'])), True)
        assert not classify_discovery_fit(discovery_item, context=stale).eligible
        assert classify_discovery_fit(discovery_item, context=stale, historical=True).eligible
        assert helper.client.get(url).json()['discovery']['items'] == body['items']
        helper.as_account(helper.outsider)
        assert helper.client.get(url).status_code == 403
        assert helper.client.post(helper.base('/discover/tenders')).status_code == 403
        other_org = helper.organizations.repository.create('Other tenant', helper.outsider.id)
        other_url = f"/api/v1/organizations/{other_org.id}/discovery/history/{body['history_id']}"
        # Authorized membership in another tenant grants no access to this snapshot.
        other_company = helper.client.post(f"/api/v1/organizations/{other_org.id}/companies",
            json={'name': 'Same name', 'profile': first['profile']})
        assert other_company.status_code == 201, other_company.text
        assert helper.client.get(other_url).status_code == 404
        helper.client.cookies.clear()
        assert helper.client.get(url).status_code == 401
        assert len(helper.catalog.calls) == calls
    finally:
        helper.doCleanups()
