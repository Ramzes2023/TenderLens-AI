"""Synthetic dependencies, real scoped APIs/services, disposable fixture database."""
from dataclasses import replace
from unittest.mock import AsyncMock, patch

from app.parsers.pdf import PdfSummary
from app.sources.models import TenderNotice
from app.sources.multi import MultiSourceFetchReport, SourceFailure

# Prevent default application import from reading dotenv/customer configuration.
with patch('dotenv.load_dotenv', return_value=False), patch('app.api.config.load_dotenv', return_value=False):
    import tests.test_company_profile_pdf as pdf_tests
    import tests.test_organization_workflows as workflows


class PartialCatalog(workflows.FakeCatalog):
    async def fetch(self, **kwargs):
        report = await super().fetch(**kwargs)
        return MultiSourceFetchReport(
            notices=report.notices,
            failures=(SourceFailure('uk_fts', 'SyntheticUnavailable', 'Synthetic failure'),),
            attempted_sources=('ted', 'uk_fts'), successful_sources=('ted',), statuses=(),
        )


def criteria(score):
    return {row['code']: row for row in score['criteria']}


def test_saved_pdf_profile_discovery_scoring_and_scoped_monitoring():
    w = workflows.OrganizationWorkflowTests()
    w.setUp()
    try:
        w.as_account(w.owner)
        response = w.client.post('/api/v1/organizations', json={'name': 'Phase24 synthetic scope'})
        assert response.status_code == 201, response.text
        org = response.json()['id']
        base = f'/api/v1/organizations/{org}'
        assert w.client.post(base + '/members', json={'account_id': w.viewer.id, 'role': 'viewer'}).status_code == 201
        profile = dict(w.profile('Protected pump supplier', 'legacy product'),
                       excluded_keywords=['used'], accepted_currencies=['EUR'],
                       min_contract_value=1000, max_contract_value=250000,
                       hard_stop_on_budget=True, hard_stop_on_currency=True)
        response = w.client.post(base + '/companies', json={'name': profile['company_name'], 'profile': profile})
        assert response.status_code == 201, response.text
        company = response.json()
        url = base + f"/companies/{company['id']}"
        original = company['profile']
        notices = [TenderNotice(source='ted', external_id=key, title=title, summary=title,
                                url=f'https://example.test/{key}', initial_price=amount, currency=currency)
                   for key, title, amount, currency in [
                       ('fit', 'Supply of industrial pumps', 10000, 'EUR'),
                       ('excluded', 'Supply of used industrial pumps', 10000, 'EUR'),
                       ('unrelated', 'Supply of office furniture', 10000, 'EUR'),
                       ('over-budget', 'Supply of industrial pumps', 300000, 'EUR'),
                       ('foreign', 'Supply of industrial pumps', 10000, 'USD')]]
        catalog = PartialCatalog(notices)
        w.client.app.state.runtime.source_catalog = catalog
        feed = workflows.DynamicSource([replace(n, source='eis') for n in notices[:4]])
        w.monitoring.source = feed
        provider = pdf_tests.FakeProvider(dict(
            industry='Industrial pumps', product_keywords=['industrial pumps'],
            search_keywords=['industrial pumps'], allowed_regions=[], allowed_countries=[],
            available_document_keywords=[]))
        w.client.app.state.runtime.provider = provider
        text = 'We manufacture industrial pumps and spare parts.'
        summary = AsyncMock(return_value=PdfSummary('ok', 1, len(text), 0, text, (text,)))
        fetch_feed = AsyncMock(wraps=feed.fetch)
        with patch('app.api.organization_company_routes.summarize_pdf', summary), patch.object(
                workflows.DynamicSource, 'fetch', fetch_feed):
            preview = w.client.post(url + '/profile-from-pdf/preview', files={
                'file': ('synthetic.pdf', b'%PDF-synthetic-summary', 'application/pdf')})
            assert preview.status_code == 200, preview.text
            draft = preview.json()['suggested_profile']
            assert draft['product_keywords'] == ['industrial pumps']
            assert w.client.get(url).json()['profile'] == original
            for account in (w.viewer, w.outsider):
                w.as_account(account)
                assert w.client.patch(url, json={'profile': draft}).status_code == 403
                assert w.client.post(base + '/monitoring/scan').status_code == 403
            w.as_account(w.owner)
            applied = w.client.patch(url, json={'profile': draft})
            assert applied.status_code == 200, applied.text
            protected = ('company_name', 'business_mode', 'excluded_keywords', 'accepted_currencies',
                         'min_contract_value', 'max_contract_value', 'hard_stop_on_region',
                         'hard_stop_on_budget', 'hard_stop_on_currency', 'hard_stop_on_bid_security',
                         'hard_stop_on_contract_security')
            for key in protected:
                assert draft[key] == original[key]
                assert applied.json()['profile'][key] == original[key]
            assert catalog.calls == []  # Neither preview nor explicit apply triggers discovery.
            assert fetch_feed.await_count == 0  # Nor does it trigger monitoring.

        discovered = w.client.post(base + '/discover/tenders')
        assert discovered.status_code == 200, discovered.text
        report = discovered.json()
        assert report['attempted_sources'] == ['ted', 'uk_fts']
        assert report['successful_sources'] == ['ted']
        assert report['failed_sources'] == ['uk_fts']
        assert report['partial_failure'] is True and report['total_failure'] is False
        items = {item['external_id']: item for item in report['items']}
        assert 'fit' in items
        assert not {'excluded', 'unrelated', 'over-budget'} & items.keys()
        item = items['fit']
        assert item['analysis_stage'] == 'metadata_preview' and item['full_ai_analyzed'] is False
        preliminary = item['preliminary_scoring']
        assert preliminary['profile_name'] == original['company_name']
        assert criteria(preliminary)['category']['status'] == 'matched'
        assert criteria(preliminary)['documents']['status'] == 'not_scored'
        assert 'industrial pumps' in catalog.calls[0]['search_terms']
        # Existing prefilter retains foreign-currency candidates; scorer must expose the stop.
        assert items['foreign']['initial_price'] == 10000 and items['foreign']['currency'] == 'USD'
        assert criteria(items['foreign']['preliminary_scoring'])['budget']['status'] == 'failed'
        assert items['foreign']['preliminary_scoring']['stop_factors']

        factual = dict(title='Supply of industrial pumps', procurement_object='industrial pumps',
                       initial_price=10000.0, currency='EUR', technical_requirements=['industrial pumps'],
                       required_documents=['ISO 9001 certificate'],
                       missing_information=['Delivery location absent from synthetic document'],
                       risks=['Synthetic certificate requirement needs review'])

        def evaluate(data, scope=base):
            response = w.client.post(scope + '/scoring/evaluate', json=data)
            assert response.status_code == 200, response.text
            return response.json()

        scored = evaluate(factual)
        rows = criteria(scored)
        assert scored['profile_name'] == original['company_name']
        assert rows['category']['evidence'] == ['industrial pumps']
        assert rows['budget']['status'] == 'matched'
        assert rows['documents']['status'] == 'not_scored'  # No declared company document inventory.
        assert rows['region']['status'] == 'not_scored'
        assert rows['bid_security']['status'] == 'not_scored'
        assert scored['missing_information'] == factual['missing_information']
        assert scored['document_risks'] == factual['risks']
        assert scored['completeness_percent'] > preliminary['completeness_percent']
        assert criteria(evaluate(dict(factual, title='Office furniture', procurement_object='chairs',
                                      technical_requirements=['chairs'])))['category']['status'] == 'failed'
        for changes in ({'initial_price': 300000.0}, {'currency': 'USD'}):
            rejected = evaluate(dict(factual, **changes))
            assert criteria(rejected)['budget']['status'] == 'failed'
            assert rejected['stop_factors']
        unknown = evaluate(dict(factual, currency=None))
        assert criteria(unknown)['budget']['status'] == 'not_scored'

        def scan(scope=base):
            response = w.client.post(scope + '/monitoring/scan')
            assert response.status_code == 200, response.text
            return response.json()

        first = scan()
        assert [n['external_id'] for n in first] == ['fit']
        assert first[0]['source'] == 'eis' and first[0]['reasons']
        assert scan() == []
        # Discovery does not consume monitoring seen-state, and remains repeatable.
        assert 'fit' in {n['external_id'] for n in w.client.post(base + '/discover/tenders').json()['items']}
        second = w.client.post(base + '/companies', json={'name': 'Other products',
                                                         'profile': w.profile('Other products', 'furniture')})
        assert second.status_code == 201, second.text
        assert second.json()['is_active'] is False
        assert evaluate(factual)['profile_name'] == original['company_name']
        assert w.client.post(base + f"/companies/{second.json()['id']}/activate").status_code == 200
        assert criteria(evaluate(factual))['category']['status'] == 'failed'
        assert [n['external_id'] for n in scan()] == ['unrelated']
        assert w.client.post(base + f"/companies/{company['id']}/activate").status_code == 200
        assert scan() == []
        # Separate organization, same offered product: dedup must be independently scoped.
        other_base = w.base('')
        assert w.client.get(other_base + f"/companies/{company['id']}").status_code == 404
        other = w.client.post(other_base + '/companies', json={'name': 'Other organization pumps',
                             'profile': dict(applied.json()['profile'], company_name='Other organization pumps')})
        assert other.status_code == 201, other.text
        assert [n['external_id'] for n in scan(other_base)] == ['fit']
        assert scan(other_base) == []
        assert w.client.get(url).json()['profile'] == applied.json()['profile']
        assert len(provider.calls) == 1
        before = len(catalog.calls)
        w.as_account(w.outsider)
        assert w.client.post(base + '/discover/tenders').status_code == 403
        assert w.client.post(base + '/scoring/evaluate', json=factual).status_code == 403
        assert w.client.post(base + '/monitoring/scan').status_code == 403
        assert len(catalog.calls) == before
    finally:
        w.doCleanups()
