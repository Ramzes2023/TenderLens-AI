"""Exact offline identity proofs for company-search aggregates, no live sources."""
from dataclasses import replace
from datetime import datetime, timezone
import copy
import json
import sqlite3
from types import SimpleNamespace

import pytest

from app.analytics.service import (HistoryEvent, HistoryPopulation, aggregate_history,
                                   load_history, metadata_groups, GROUPS)
from app.analytics.deadlines import DeadlineWindow, DeadlinePopulation, DeadlineRow, filter_deadlines
from app.analytics.dates import stored_date
from app.analytics.fit import VerifiedFitContext
from app.api.organization_workflow_routes import _discovery_item
from app.database.repository import DatabaseAuthorizationError, DatabaseError
from app.models.tender import TenderAnalysis
from app.scoring.engine import _completeness
from app.scoring.models import CompanyProfile
from app.scoring.runs import profile_digest
from app.sources.enrichment import enrichment
from app.sources.models import TenderNotice
from tests.test_discovery_history_repository import _prepare_scope

AS_OF = datetime(2026, 3, 27, 12, tzinfo=timezone.utc)
PROFILE = CompanyProfile(profile_version='v1', company_name='Fixture', product_keywords=['pumps'])
DIGEST = profile_digest(PROFILE)
WINDOW = DeadlineWindow(AS_OF, 'Europe/Rome')


def item(external='one', score=65, *, deadline='2026-03-28T12:00:00Z', countries=('IT',), categories=()):
    value = _discovery_item(SimpleNamespace(notice=TenderNotice(source='ted', external_id=external,
        title='Supply pumps', url='https://example.test/' + external), reasons=[]), PROFILE,
        organization_id=7, company_id=33).model_dump(mode='json')
    value['preliminary_scoring']['fit_score'] = score
    value['preliminary_provenance']['scored_at'] = '2026-03-26T12:00:00Z'
    value['enrichment'] = enrichment('ted', external,
        locations=tuple([{'value': code, 'path': 'place.country'}] for code in countries),
        classifications=tuple({'scheme': 'cpv-2008', 'code': code, 'path': 'classification-cpv', 'role': 'reported'} for code in categories),
        dates={'deadline': {'value': deadline, 'path': 'deadline'},
               'publication': {'value': '2026-03-01', 'path': 'publication-date'}})
    return value


def event(identity, items=(), *, stamp='2026-03-26T12:00:00+00:00', attempted=('ted',), success=('ted',), failed=(), statuses=()):
    body = dict(items=list(items), attempted_sources=list(attempted), successful_sources=list(success),
        failed_sources=list(failed), partial_failure=bool(success and failed), total_failure=bool(failed and not success),
        source_statuses=list(statuses))
    return HistoryEvent(identity, 7, 33, stamp, len(items), json.dumps(body), json.dumps(attempted),
        json.dumps(success), json.dumps(failed), body['partial_failure'], body['total_failure'])


def population(*events, coverage='complete_observed_storage'):
    return HistoryPopulation(7, 33, tuple(events), max((e.id for e in events), default=0),
                             '2026-03-27T12:00:00+00:00', len(events), coverage)


def aggregate(p, **kw):
    return aggregate_history(p, window=kw.pop('window', WINDOW), current_profile_digest=kw.pop('digest', DIGEST), **kw)


def persist(repo, e):
    record = repo.record_discovery_search_for_organization(account_id=101, organization_id=7,
        company_id=33, result_count=e.result_count, scored_count=e.result_count,
        snapshot_json=e.snapshot_json, attempted_sources_json=e.attempted_sources_json,
        successful_sources_json=e.successful_sources_json, failed_sources_json=e.failed_sources_json,
        partial_failure=e.partial_failure, total_failure=e.total_failure)
    with sqlite3.connect(repo.path) as conn:
        conn.execute('UPDATE discovery_search_history SET created_at=? WHERE id=?', (e.created_at, record.id))
    return record.id


def test_exact_six_slots_memberships_bands_top_and_dates():
    a = item('a', 0, categories=('45000000', '45200000'))
    b = item('b', 35, countries=('IT', 'FR'), deadline='2026-03-29')
    c = item('c', 65, deadline='2026-04-03T12:00:00Z')  # exact 7-day end
    d = item('d', 90, countries=(), deadline='2026-03-28T12:00:00')
    e = item('e', None, deadline=None)
    result = aggregate(population(event(1, (a, b, c, d, e))))
    ids = tuple(('ted', x) for x in 'abcde')
    assert result['U'] == ids
    assert {k: v.value for k, v in result['kpis'].items()} == {
        'Discovered': 5, 'Matched': 3, 'High Fit': 2, 'Active Sources': 1, 'Countries': 2, 'Closing Soon': 1}
    assert result['fit_bands']['low'].identities == (ids[0],)
    assert result['fit_bands']['medium'].identities == (ids[1],)
    assert result['fit_bands']['high'].identities == (ids[2], ids[3])
    assert result['unknown_fit'] == {'missing_or_malformed_score': (ids[4],)}
    assert {v.denominator for v in result['fit_bands'].values()} == {4}
    assert result['countries']['IT'].identities == (ids[0], ids[1], ids[2], ids[4])
    assert result['countries']['FR'].identities == (ids[1],)
    assert result['membership_overlap'] == {'country': 1, 'category': 1}
    assert {k: v.identities for k, v in result['categories'].items()} == {
        ('cpv-2008', '45000000'): (ids[0],), ('cpv-2008', '45200000'): (ids[0],)}
    assert result['closing_soon_date_only'].identities == (ids[1],)
    assert result['kpis']['Closing Soon'].identities == (ids[0],)
    assert result['deadline_grouping'].selected == (ids[0], ids[1])
    assert result['date_distributions'][('published_at', 'date_only_source_calendar', '2026-03-01')].identities == ids
    assert result['search_activity']['2026-03-26']['identities'] == ids
    assert result['search_activity']['2026-03-26']['row_occurrences'] == 5
    assert [r['identity'] for r in result['top_opportunities']] == [ids[3], ids[2], ids[1], ids[0]]
    for row in result['top_opportunities']:
        assert row['event_id'] == 1 and row['item']['external_id'] == row['identity'][1]
        assert row['snapshot_sha256'] == result['selected_events'][0][2]
        assert row['ordinal'] == 'abcde'.index(row['identity'][1])
    assert result['industry']['value'] is None
    assert result['lifetime_total'] is None


def test_latest_timestamp_id_first_occurrence_and_conflict_exclusion():
    old, new = item('a', 0), item('a', 90)
    b = item('b', 65)
    result = aggregate(population(event(5, (old,), stamp='2026-03-25T12:00:00+00:00'),
        event(2, (new, new, b)), event(3, (item('b', 35),))))
    assert result['U'] == (('ted', 'a'), ('ted', 'b'))
    assert [(r['identity'], r['event_id'], r['ordinal']) for r in result['rows']] == [
        (('ted', 'a'), 2, 0), (('ted', 'b'), 3, 0)]
    assert result['diagnostics']['duplicate_within_event'] == 1
    assert result['diagnostics']['duplicate_revisions'] == 2
    assert result['revision_conflicts'] == (('ted', 'a'), ('ted', 'b'))
    conflict = aggregate(population(event(1, (old, new, b))))
    assert conflict['U'] == (('ted', 'b'),)
    assert conflict['conflicting_identities'] == (('ted', 'a'),)
    assert conflict['kpis']['Discovered'].value is None
    assert conflict['kpis']['Discovered'].numerator == 1


@pytest.mark.parametrize('score,band', [(0,'low'), (34.999,'low'), (35,'medium'), (64.999,'medium'), (65,'high'), (90,'high'),
    (-1,None),(91,None),(True,None),('65',None),(None,None)])
def test_service_exact_fit_boundaries(score, band):
    result = aggregate(population(event(1, (item(score=score),))))
    assert {b: v.numerator for b, v in result['fit_bands'].items()} == {
        b: int(b == band) for b in ('low', 'medium', 'high')}
    assert sum(map(len, result['unknown_fit'].values())) == int(band is None)


def test_historical_current_stale_and_full_ai_are_distinct():
    a, b = item('a'), item('b')
    b['analysis_stage'] = 'full_document'
    b['full_scoring'] = {'fit_score': 100}
    result = aggregate(population(event(1, (a, b))), digest='a' * 64)
    assert result['fit_bands']['high'].identities == (('ted', 'a'),)
    assert result['current_fit_unknown']['stale_profile_digest'] == (('ted', 'a'),)
    assert result['unknown_fit']['unknown_or_nonpreview_stage'] == (('ted', 'b'),)
    a.pop('analysis_stage')
    assert aggregate(population(event(1, (a,))))['unknown_fit'] == {'unknown_or_nonpreview_stage': (('ted','a'),)}


@pytest.mark.parametrize('raw', ['', '{broken', '{}', '[]', '{"items":[],"items":[]}', '{"items": [NaN]}'])
def test_corrupt_json_not_fake_empty(raw):
    result = aggregate(population(replace(event(1), snapshot_json=raw)))
    assert result['coverage'] == 'partial_observed_storage'
    assert result['kpis']['Discovered'].value is None
    assert result['snapshot_errors']


@pytest.mark.parametrize('field,value', [('source',None),('source',[]),('source','TED'),('external_id',None),('external_id',''),('external_id',' a ')])
def test_invalid_identity_diagnostics(field, value):
    a = item()
    a[field] = value
    result = aggregate(population(event(1, (a,))))
    assert result['U'] == () and result['kpis']['Discovered'].value is None
    assert result['diagnostics'].get('invalid_identity',0) + result['diagnostics'].get('missing_identity',0) == 1


def test_complete_successful_empty_is_zero_and_unknown_country_is_unavailable():
    result = aggregate(population(event(1)))
    assert result['kpis']['Discovered'].value == 0
    assert result['kpis']['Active Sources'].value == 1
    assert result['kpis']['Countries'].value == 0
    assert result['source_health']['ted']['successful_zero'] == 0  # no persisted notice_count
    a = item(countries=())
    a.pop('enrichment')
    result = aggregate(population(event(1,(a,))))
    assert result['kpis']['Countries'].value is None
    assert result['kpis']['Closing Soon'].value is None
    assert result['unresolved_evidence']['country:unavailable'] == (('ted','one'),)


def test_source_observations_success_zero_failed_partial_duration_and_unobserved():
    result = aggregate(population(
        event(1, attempted=('ted','eis'), success=('ted',), failed=('eis',), statuses=(
            {'source':'ted','state':'healthy','notice_count':0,'duration_ms':0},
            {'source':'eis','state':'failed','duration_ms':200})),
        event(2, statuses=({'source':'ted','state':'healthy','notice_count':2,'duration_ms':100},)),
        event(3, success=(), failed=('ted',))))
    ted, eis = result['source_health']['ted'], result['source_health']['eis']
    assert (ted['attempted'], ted['successful'], ted['failed'], ted['successful_zero']) == (3,2,1,1)
    assert ted['duration_sample_count'] == 2 and ted['missing_duration'] == 1
    assert ted['mean_recorded_duration_ms'] == 50
    assert (eis['attempted'], eis['successful'], eis['failed']) == (1,0,1)
    assert eis['samples'][0][-2:] == (True,False)
    assert result['source_health']['sam_gov']['state'] == 'unobserved'
    assert result['source_health']['sam_gov']['mean_recorded_duration_ms'] is None
    missing = aggregate(population(event(1)))['source_health']['ted']
    assert missing['duration_reason'] == 'no_recorded_durations'


def test_source_conflicts_do_not_become_success():
    e = event(1)
    e = replace(e, failed_sources_json='["ted"]')
    result = aggregate(population(e))
    assert result['source_health']['ted']['state'] == 'unobserved'
    assert result['coverage'] == 'partial_observed_storage'


def test_metadata_ten_groups_known_zero_missing_analysis_and_gaps():
    a, b, c = item('a'), item('b'), item('c')
    analysis = dict(title='Known', initial_price=0, submission_deadline='date', contract_term='term',
        delivery_region='region', bid_security_amount=0, procurement_object='object',
        participant_requirements=['req'], required_documents=['doc'], technical_requirements=['tech'])
    a['metadata_analysis'] = analysis
    b['metadata_analysis'] = {}
    c.pop('metadata_analysis')
    result = aggregate(population(event(1,(a,b,c))))['metadata_completeness']
    assert len(GROUPS) == 10
    assert (result['known_analyzed_U'],result['all_U'],result['present_groups'],result['known_required_groups'],result['all_required_groups']) == (2,3,10,20,30)
    assert result['known_percent'] == 50 and result['all_U_percent'] is None
    assert result['unknown'] == (('ted','c'),)
    assert all(g['present'] == 1 and g['missing'] == (('ted','b'),) and g['unknown'] == (('ted','c'),) for g in result['groups'].values())
    parsed = TenderAnalysis.model_validate(analysis)
    assert metadata_groups(parsed) == (True,)*10 and _completeness(parsed) == 100


def test_over_100_paginated_events_fence_concurrent_insert_and_no_cap(tmp_path):
    repo = _prepare_scope(tmp_path/'history.db')
    ids = [persist(repo,event(i+1,(item(str(i)),))) for i in range(123)]
    original = repo.page_discovery_history
    calls = []
    def wrapped(*args, **kw):
        page = original(*args,**kw)
        calls.append(kw)
        if len(calls) == 1:
            persist(repo,event(999,(item('concurrent'),)))
        return page
    repo.page_discovery_history = wrapped
    p = load_history(repo,account_id=101,organization_id=7,company_id=33,batch_size=7)
    result = aggregate(p)
    assert p.watermark == max(ids) and p.observed_count == 123
    assert result['U'] == tuple(sorted(('ted',str(i)) for i in range(123)))
    assert result['kpis']['Discovered'].value == 123
    assert len(calls) == 37 and all(c['page_size'] == 7 for c in calls)
    assert result['diagnostics']['row_occurrences'] == 123


@pytest.mark.parametrize('delete_read', [True,False])
def test_deletion_during_reads_invalidates_complete_total(tmp_path, delete_read):
    repo = _prepare_scope(tmp_path/'delete.db')
    ids = [persist(repo,event(i+1,(item(str(i)),))) for i in range(4)]
    original = repo.page_discovery_history
    calls = 0
    def wrapped(*args,**kw):
        nonlocal calls
        page = original(*args,**kw)
        calls += 1
        if calls == 1:
            with sqlite3.connect(repo.path) as conn:
                conn.execute('DELETE FROM discovery_search_history WHERE id=?',(ids[-1] if delete_read else ids[0],))
        return page
    repo.page_discovery_history = wrapped
    p = load_history(repo,account_id=101,organization_id=7,company_id=33,batch_size=2)
    result = aggregate(p)
    assert result['kpis']['Discovered'].value is None
    assert result['coverage'] == 'partial_observed_storage'
    expected = range(4) if delete_read else range(1,4)
    assert result['U'] == tuple(('ted',str(i)) for i in expected)


@pytest.mark.parametrize('role',['owner','admin','member','viewer'])
def test_loader_roles_revocation_and_scope_errors(tmp_path, role):
    repo = _prepare_scope(tmp_path/'auth.db')
    with sqlite3.connect(repo.path) as conn:
        conn.execute('UPDATE organization_members SET role=?',(role,))
    persist(repo,event(1))
    assert load_history(repo,account_id=101,organization_id=7,company_id=33).observed_count == 1
    for args in [(999,7,33),(101,8,33),(101,7,999)]:
        with pytest.raises(DatabaseAuthorizationError):
            load_history(repo,account_id=args[0],organization_id=args[1],company_id=args[2])
    original = repo.page_discovery_history
    def revoke(*args,**kw):
        page = original(*args,**kw)
        with sqlite3.connect(repo.path) as conn:
            conn.execute('DELETE FROM organization_members')
        return page
    repo.page_discovery_history = revoke
    with pytest.raises(DatabaseAuthorizationError):
        load_history(repo,account_id=101,organization_id=7,company_id=33)


def test_missing_storage_is_error_not_zero(tmp_path):
    repo = _prepare_scope(tmp_path/'missing.db')
    with sqlite3.connect(repo.path) as conn:
        conn.execute('DROP TABLE discovery_search_history')
    with pytest.raises(DatabaseError):
        load_history(repo,account_id=101,organization_id=7,company_id=33)


@pytest.mark.parametrize('update',[{'company_id':44},{'organization_id':8},{'id':1000},{'created_at':'2026-03-28T00:00:00Z'},{'created_at':'2026-03-26T00:00:00'}])
def test_forged_population_integrity(update):
    with pytest.raises(ValueError):
        HistoryPopulation(7,33,(replace(event(1),**update),),1,'2026-03-27T12:00:00Z',1,'complete_observed_storage')
    with pytest.raises(ValueError):
        replace(population(event(1)), origin='R')


def test_heatmap_exact_identity_replay_dst_and_no_zone():
    items = (item('a',deadline='2026-03-29T01:30:00Z'),item('b',deadline='2026-03-29'),
        item('c',deadline='2026-04-03T12:00:00Z'),item('d',deadline='2026-03-26T12:00:00Z'))
    p = population(event(1,items))
    result = aggregate(p)
    dp = DeadlinePopulation(7,33,result['population_id'],tuple(DeadlineRow(7,33,('ted',v['external_id']),
        stored_date(v['enrichment']['dates']['deadline'],source='ted',path='deadline',field='deadline')) for v in items))
    assert filter_deadlines(dp,WINDOW) == (('ted','a'),('ted','b'))
    for kind,day,ids in result['deadline_grouping'].buckets:
        assert ids == filter_deadlines(dp,WINDOW,bucket=day,kind=kind)
    assert aggregate(p,window=DeadlineWindow(AS_OF,'Missing/Zone'))['kpis']['Closing Soon'].identities == (('ted','a'),)
    assert aggregate(p,window=DeadlineWindow(AS_OF,'Missing/Zone'))['closing_soon_date_only'].value is None


def test_pure_aggregate_no_network_scoring_mutation(monkeypatch):
    import socket
    import app.scoring.engine
    p = population(event(1,(item(),)))
    before = copy.deepcopy(p)
    def forbidden(*a,**kw):
        raise AssertionError('Forbidden aggregate side effect')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(app.scoring.engine,'score_tender',forbidden)
    assert aggregate(p) == aggregate(p)
    assert p == before


def test_existing_sam_and_austender_source_fixture_pipeline():
    from tests.test_analytics_normalization import sam
    from tests.test_austender_source import _detail_html, UUID_1
    from app.sources.austender_rss import parse_austender_detail_page, AUSTENDER_ATM_BASE_URL
    notices = [sam(), parse_austender_detail_page(_detail_html(), external_id=UUID_1,
        url=AUSTENDER_ATM_BASE_URL+UUID_1, rss_title='ISO 9001 Certification Services')]
    values = tuple(_discovery_item(SimpleNamespace(notice=notice,reasons=[]),PROFILE,
        organization_id=7,company_id=33).model_dump(mode='json') for notice in notices)
    e = event(1,values,stamp='2026-10-10T12:00:00Z',attempted=('sam_gov','austender'),success=('sam_gov','austender'))
    p = HistoryPopulation(7,33,(e,),1,'2026-10-11T12:00:00Z',1,'complete_observed_storage')
    result = aggregate(p,window=DeadlineWindow(datetime(2026,10,11,12,tzinfo=timezone.utc),'Europe/Rome'))
    assert result['U'] == (('austender',UUID_1),('sam_gov','abc123def456'))
    assert result['countries']['US'].identities == (('sam_gov','abc123def456'),)
    assert result['categories'][('austender-category','80100000')].identities == (('austender',UUID_1),)
    assert result['kpis']['Countries'].value == 1
    assert result['kpis']['Active Sources'].value == 2
    assert result['unresolved_evidence']['deadline:ambiguous'] == (('austender',UUID_1),)
    assert result['enrichment_coverage'] == {'country_known_U':1,'category_known_U':1,
        'publication_known_U':2,'deadline_known_U':1,'denominator':2}


def test_partial_total_failure_not_fake_successful_zero():
    result = aggregate(population(event(1,success=(),failed=('ted',))))
    assert result['kpis']['Discovered'].value is None
    assert result['kpis']['Discovered'].reason == 'partially_failed_observed_searches_only'
    assert result['source_health']['ted']['failed'] == 1
    assert result['source_health']['ted']['successful_zero'] == 0
    assert result['source_search_coverage'] == 'partial_failed_searches'


def test_metadata_conflict_and_distinct_currencies_are_disclosed():
    a,b = item('a'),item('b')
    a['initial_price'],a['currency'] = 0,'EUR'
    a['metadata_analysis']['initial_price'] = 10
    a['metadata_analysis']['currency'] = 'EUR'
    b['initial_price'],b['currency'] = 100,'USD'
    result = aggregate(population(event(1,(a,b))))
    assert result['metadata_conflicts'] == ((('ted','a'),'initial_price',0,10.0),)
    assert result['monetary_aggregate']['value'] is None
    assert result['rows'][0]['item']['initial_price'] == 0


def test_tied_scores_top_limit_identity_and_all_drilldowns():
    values = tuple(item(x,65) for x in 'cba')
    result = aggregate(population(event(1,values)),top_limit=2)
    assert [r['identity'] for r in result['top_opportunities']] == [('ted','a'),('ted','b')]
    assert result['top_total'] == 3
    expected = tuple(('ted',x) for x in 'abc')
    assert result['kpi_drilldown_identities'] == {k:expected for k in
        ('Discovered','Matched','High Fit','Active Sources','Countries','Closing Soon')}
    assert all(m.denominator == 3 for m in result['fit_bands'].values())
    assert sum(m.share for m in result['fit_bands'].values()) == 1


def test_ten_group_all_u_known_denominator_and_zero_fields():
    a=item()
    a['metadata_analysis']={'initial_price':0,'bid_security_percent':0}
    result=aggregate(population(event(1,(a,))))['metadata_completeness']
    assert (result['present_groups'],result['known_required_groups'],result['all_required_groups']) == (2,10,10)
    assert result['all_U_percent'] == result['known_percent'] == 20
    assert result['groups']['price']['present'] == result['groups']['security']['present'] == 1


def test_unsupported_classifications_conflicting_country_and_evidence_identity():
    a=item()
    a['enrichment']=enrichment('ted','one',locations=([{'path':'country.code','value':'USA'},
        {'path':'country.name','value':'Canada'}],), classifications=(
        {'scheme':'CPV','code':'45000000','path':'classification','role':'reported'},))
    result=aggregate(population(event(1,(a,))))
    assert result['countries'] == result['categories'] == {}
    assert result['unresolved_evidence']['country:conflicting'] == (('ted','one'),)
    assert result['unresolved_evidence']['category:unsupported'] == (('ted','one'),)
    a['enrichment']['external_id']='forged'
    result=aggregate(population(event(1,(a,))))
    assert result['unresolved_evidence']['country:unavailable'] == (('ted','one'),)


def test_release_date_and_source_update_never_become_publication():
    from app.analytics.dates import normalize_date
    a=item()
    entry=a['enrichment']['dates']['publication']
    entry['semantics']='source_update'
    entry['normalized']=normalize_date(entry['value'],source='ted',path=entry['path'],
        field='published_at',semantics='source_update').model_dump(mode='json')
    result=aggregate(population(event(1,(a,))))
    assert ('source_update','date_only_source_calendar','2026-03-01') in result['date_distributions']
    assert not any(key[0]=='published_at' for key in result['date_distributions'])
    assert result['enrichment_coverage']['publication_known_U'] == 0


def test_count_mismatch_and_nonfinite_corrupt_snapshot():
    e=replace(event(1,(item(),)),result_count=2)
    result=aggregate(population(e))
    assert result['kpis']['Discovered'].value is None and result['kpis']['Discovered'].numerator == 1
    assert result['diagnostics']['snapshot_count_mismatch'] == 1
    e=replace(e,snapshot_json=e.snapshot_json.replace('65','NaN'))
    assert aggregate(population(e))['snapshot_errors'] == ((1,'corrupt_snapshot'),)


def test_sample_range_half_open_excludes_other_company_and_unchanged_storage(tmp_path):
    repo=_prepare_scope(tmp_path/'range.db')
    persist(repo,event(1,(item('a'),),stamp='2026-03-25T12:00:00Z'))
    persist(repo,event(2,(item('b'),),stamp='2026-03-26T12:00:00Z'))
    persist(repo,event(3,(item('c'),),stamp='2026-03-27T12:00:00Z'))
    with sqlite3.connect(repo.path) as conn:
        before=conn.execute('SELECT * FROM discovery_search_history ORDER BY id').fetchall()
    p=load_history(repo,account_id=101,organization_id=7,company_id=33,
        start='2026-03-26T12:00:00Z',end='2026-03-27T12:00:00Z')
    assert aggregate(p)['U'] == (('ted','b'),)
    assert load_history(repo,account_id=101,organization_id=7,company_id=44).events == ()
    with sqlite3.connect(repo.path) as conn:
        assert conn.execute('SELECT * FROM discovery_search_history ORDER BY id').fetchall() == before
    with pytest.raises(TypeError):
        load_history(repo,account_id=101,organization_id=7,company_id=33,state={'fence':999})


def test_fall_dst_utc_seven_day_end_and_calendar_distinct():
    as_of=datetime(2026,10,23,12,tzinfo=timezone.utc)
    values=(item('a',deadline='2026-10-25T02:30:00+02:00'),
        item('b',deadline='2026-10-25T02:30:00+01:00'),
        item('c',deadline='2026-10-30T12:00:00Z'),item('d',deadline='2026-10-30'))
    p=population(event(1,values))
    result=aggregate(p,window=DeadlineWindow(as_of,'Europe/Rome'))
    assert result['kpis']['Closing Soon'].identities == (('ted','a'),('ted','b'))
    assert result['closing_soon_date_only'].identities == ()


@pytest.mark.parametrize('change',[{'engine_version':'future'}, {'company_id':44}, {'scoring_policy_version':'future'}])
def test_untrusted_ineligible_fit_never_full_scoring_fallback(change):
    a=item()
    a['preliminary_provenance'].update(change)
    a['full_scoring']={'fit_score':100}
    result=aggregate(population(event(1,(a,))))
    assert sum(m.numerator for m in result['fit_bands'].values()) == 0
    assert sum(map(len,result['unknown_fit'].values())) == 1


@pytest.mark.parametrize('already_read',[False,True])
def test_snapshot_body_deletion_at_constant_count_is_disclosed(tmp_path,already_read):
    repo=_prepare_scope(tmp_path/'body-delete.db')
    ids=[persist(repo,event(i+1,(item(str(i)),))) for i in range(4)]
    original=repo.page_discovery_history
    calls=0
    target=ids[-1] if already_read else ids[0]
    def wrapped(*args,**kw):
        nonlocal calls
        page=original(*args,**kw)
        calls+=1
        if calls==1:
            with sqlite3.connect(repo.path) as conn:
                conn.execute("UPDATE discovery_search_history SET snapshot_json='' WHERE id=?",(target,))
        return page
    repo.page_discovery_history=wrapped
    p=load_history(repo,account_id=101,organization_id=7,company_id=33,batch_size=2)
    result=aggregate(p)
    assert result['kpis']['Discovered'].value is None
    assert result['observed_events'] == result['read_events'] == 4
    if already_read:
        assert result['storage_changed_event_ids'] == (target,)
        assert result['U'] == tuple(('ted',str(i)) for i in range(4))
    else:
        assert result['snapshot_errors'] == ((target,'missing_snapshot'),)
        assert result['U'] == tuple(('ted',str(i)) for i in range(1,4))
