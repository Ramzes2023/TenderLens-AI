"""Declared synthetic HTTP/PDF fixtures; real adapter, catalog, profile and scoring code."""
import asyncio
from unittest.mock import AsyncMock, patch
import httpx
import pytest
from app.parsers.pdf import PdfSummary
from app.sources.http import source_client
from scripts.phase24_public_sources_live_probe import probe, benchmark_notices
from tests.test_phase24_live_discovery_contract import workflows, ted_record, public_catalog
with patch('dotenv.load_dotenv', return_value=False), patch('app.api.config.load_dotenv', return_value=False):
    import tests.test_company_profile_pdf as pdf_tests


def responses(request):
    if request.url.host == 'api.ted.europa.eu':
        known = ted_record('100001-2026', 'Supply of industrial cables')
        unknown = ted_record('100002-2026', 'Supply of industrial cables')
        for key in ('total-value', 'total-value-cur', 'deadline-receipt-tender-date-lot'):
            unknown.pop(key)
        return httpx.Response(200, json={'notices':[known, unknown,
            ted_record('100003-2026', 'Office furniture')]})
    assert request.url.host == 'www.find-tender.service.gov.uk'
    assert request.url.path == '/api/1.0/ocdsReleasePackages'
    assert request.url.params['stages'] == 'tender'
    assert request.url.params['limit'] == '5'
    assert 'publishedFrom' in request.url.params
    return httpx.Response(503)


def client(**kwargs):
    return source_client(**kwargs, transport=httpx.MockTransport(responses))


def rows(score):
    return {r['code']:r for r in score['criteria']}


def test_profile_review_apply_real_adapter_partial_discovery_scoring_and_scope():
    w=workflows.OrganizationWorkflowTests(); w.setUp()
    try:
        w.as_account(w.owner)
        company=w.create_company('SYNTHETIC cable supplier', 'legacy')
        url=w.base(f"/companies/{company['id']}")
        original=w.client.get(url).json()['profile']
        provider=pdf_tests.FakeProvider(dict(industry='Industrial cables',
            product_keywords=['cables'],search_keywords=['cables'],allowed_regions=[],
            allowed_countries=[],available_document_keywords=[]))
        w.client.app.state.runtime.provider=provider
        text='SYNTHETIC supplier of industrial cables.'
        with patch('app.api.organization_company_routes.summarize_pdf',
                   AsyncMock(return_value=PdfSummary('ok',1,len(text),0,text,(text,)))):
            preview=w.client.post(url+'/profile-from-pdf/preview',files={
                'file':('synthetic.pdf',b'%PDF-synthetic','application/pdf')})
        assert preview.status_code==200, preview.text
        draft=preview.json()['suggested_profile']
        assert draft['product_keywords']==['cables']
        assert w.client.get(url).json()['profile']==original
        # Explicit user review may set business constraints before apply.
        draft.update(accepted_currencies=['EUR'],max_contract_value=1000000)
        assert w.client.patch(url,json={'profile':draft}).status_code==200
        w.client.app.state.runtime.source_catalog=public_catalog()
        with patch('app.sources.ted_api.source_client',client), patch('app.sources.uk_fts_api.source_client',client):
            result=w.client.post(w.base('/discover/tenders'))
            assert result.status_code==200,result.text
            report=result.json()
            assert report['partial_failure'] and not report['total_failure']
            assert report['failed_sources']==['uk_fts']
            items={i['external_id']:i for i in report['items']}
            assert set(items)=={'100001-2026','100002-2026'}
            for i in items.values():
                assert i['analysis_stage']=='metadata_preview' and not i['full_ai_analyzed']
                assert rows(i['preliminary_scoring'])['category']['status']=='matched'
                assert rows(i['preliminary_scoring'])['documents']['status']=='not_scored'
                assert i['url']==f"https://ted.europa.eu/en/notice/{i['external_id']}/html"
            known,unknown=items['100001-2026'],items['100002-2026']
            assert rows(known['preliminary_scoring'])['budget']['status']=='matched'
            assert rows(unknown['preliminary_scoring'])['budget']['status']=='not_scored'
            assert unknown['initial_price'] is None and unknown['currency'] is None and unknown['deadline'] is None
            assert known['preliminary_scoring']['completeness_percent']>unknown['preliminary_scoring']['completeness_percent']
            other=w.create_company('SYNTHETIC furniture supplier','furniture')
            assert w.client.post(w.base(f"/companies/{other['id']}/activate")).status_code==200
            switched=w.client.post(w.base('/discover/tenders')).json()
            assert [i['external_id'] for i in switched['items']]==['100003-2026']
            assert switched['items'][0]['preliminary_scoring']['profile_name']=='SYNTHETIC furniture supplier'
            other_org=w.client.post('/api/v1/organizations',json={'name':'Synthetic isolated tenant'})
            assert other_org.status_code==201
            isolated=f"/api/v1/organizations/{other_org.json()['id']}"
            assert w.client.get(isolated+f"/companies/{company['id']}").status_code==404
            w.as_account(w.outsider)
            with patch('app.sources.ted_api.source_client',side_effect=AssertionError('unauthorized fetch')):
                assert w.client.post(w.base('/discover/tenders')).status_code==403
        assert len(provider.calls)==1
    finally:
        w.doCleanups()


def test_bounded_probe_benchmark_scores_even_unmatched_and_preserves_failure():
    with patch('app.sources.ted_api.source_client',client),patch('app.sources.uk_fts_api.source_client',client):
        report,code=asyncio.run(probe(live=True))
    assert code==0 and report['outbound_calls']==2
    score=report['live_scoring']
    assert score['evaluated_notice_count']==3 and score['profile_is_synthetic']
    assert not score['full_pdf_analysis'] and not score['llm_used']
    examples={e['public_notice_id']:e for e in score['examples']}
    assert examples['100003-2026']['fit_status']=='FILTERED_OUT'
    assert not examples['100003-2026']['prefilter_matched']
    assert rows(examples['100003-2026'])['category']['status']=='failed'
    assert examples['100002-2026']['unknown_reason']
    uk=report['sources']['uk_fts']
    assert uk['status']=='UNAVAILABLE' and uk['transport']['error_type']=='ConnectorTransportError'
    assert uk['live_scoring']['evaluated_notice_count']==0
    assert uk['live_scoring']['status']=='NOT_EVALUATED'
    assert 'not independently established' in uk['failure_cause']
    assert benchmark_notices([])['status']=='NOT_EVALUATED'


@pytest.mark.parametrize('kwargs',[{'limit':6},{'timeout':13},{'limit':0}])
def test_probe_rejects_unbounded_programmatic_arguments(kwargs):
    with pytest.raises(ValueError):
        asyncio.run(probe(live=True,**kwargs))
