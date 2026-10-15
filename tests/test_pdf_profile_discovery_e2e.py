"""Isolated existing API chain; no live PDF parser, LLM or source claims."""
from unittest.mock import AsyncMock, patch

from app.parsers.pdf import PdfSummary
from app.sources.models import TenderNotice
# The existing app module constructs its default settings at import time.
# Suppress dotenv file I/O before importing the existing fixture helpers.
with patch('dotenv.load_dotenv', return_value=False), patch('app.api.config.load_dotenv', return_value=False):
    import tests.test_company_profile_pdf as pdf_tests
    import tests.test_organization_workflows as workflow_tests


def test_pdf_profile_explicit_apply_to_discovery():
    w = workflow_tests.OrganizationWorkflowTests()
    w.setUp()
    try:
        w.as_account(w.owner)
        created_org = w.client.post('/api/v1/organizations', json={'name': 'Catalog proof'})
        assert created_org.status_code == 201, created_org.text
        org = created_org.json()['id']
        base = f'/api/v1/organizations/{org}'
        assert created_org.json()['personal'] is False
        member = w.client.post(base + '/members', json={'account_id': w.viewer.id, 'role': 'viewer'})
        assert member.status_code == 201, member.text
        profile = dict(w.profile('Pump supplier'), excluded_keywords=['used'],
                       accepted_currencies=['EUR'], min_contract_value=1000,
                       max_contract_value=250000, hard_stop_on_budget=True,
                       hard_stop_on_currency=True)
        created = w.client.post(base + '/companies', json={'name': 'Pump supplier', 'profile': profile})
        assert created.status_code == 201, created.text
        company = created.json()
        url = base + f"/companies/{company['id']}"
        original = company['profile']
        text = 'We manufacture industrial pumps. Supply of industrial pumps and spare parts.'
        provider = pdf_tests.FakeProvider(dict(industry='Industrial pumps', product_keywords=['industrial pumps'],
                                     search_keywords=['industrial pumps'], allowed_regions=[],
                                     allowed_countries=[], available_document_keywords=[]))
        w.client.app.state.runtime.provider = provider
        summary = AsyncMock(return_value=PdfSummary('ok', 1, len(text), 0, text, (text,)))
        upload = {'file': ('synthetic-catalog.pdf', b'%PDF-synthetic-bounded-summary', 'application/pdf')}
        with patch('app.api.organization_company_routes.summarize_pdf', summary):
            preview = w.client.post(url + '/profile-from-pdf/preview', files=upload)
            assert preview.status_code == 200, preview.text
            assert len(provider.calls) == 1
            assert text in provider.calls[0][0]
            draft = preview.json()['suggested_profile']
            assert draft['product_keywords'] == ['industrial pumps']
            assert w.client.get(url).json()['profile'] == original
            w.as_account(w.viewer)
            assert w.client.get(url).status_code == 200
            assert w.client.post(url + '/profile-from-pdf/preview', files=upload).status_code == 403
            assert w.client.patch(url, json={'profile': draft}).status_code == 403
            w.as_account(w.outsider)
            assert w.client.post(url + '/profile-from-pdf/preview', files=upload).status_code == 403
            assert w.client.patch(url, json={'profile': draft}).status_code == 403
            assert summary.await_count == 1
            assert len(provider.calls) == 1
        w.as_account(w.owner)
        applied = w.client.patch(url, json={'profile': draft})
        assert applied.status_code == 200, applied.text
        for key in ('company_name', 'business_mode', 'excluded_keywords', 'accepted_currencies',
                    'min_contract_value', 'max_contract_value', 'hard_stop_on_budget', 'hard_stop_on_currency'):
            assert applied.json()['profile'][key] == original[key]
        notices = [TenderNotice(source='ted', external_id=identity, title=title,
                                summary=title, url=f'https://example.test/{identity}',
                                initial_price=10000, currency='EUR') for identity, title in
                   [('fit', 'Supply of industrial pumps'), ('excluded', 'Supply of used industrial pumps'),
                    ('unrelated', 'Supply of office furniture')]]
        catalog = workflow_tests.FakeCatalog(notices)
        w.client.app.state.runtime.source_catalog = catalog
        discovery = w.client.post(base + '/discover/tenders')
        assert discovery.status_code == 200, discovery.text
        items = discovery.json()['items']
        assert [item['external_id'] for item in items] == ['fit']
        assert items[0]['preliminary_scoring']['fit_score'] >= 65
        assert items[0]['analysis_stage'] == 'metadata_preview'
        assert items[0]['full_ai_analyzed'] is False
        assert 'industrial pumps' in catalog.calls[0]['search_terms']
        assert len(provider.calls) == 1  # Discovery does not regenerate the profile.
        assert w.client.get(url).json()['profile'] == applied.json()['profile']
        # Same owner, different shared organization: company ID cannot cross scope.
        assert w.client.get(w.base(f"/companies/{company['id']}")).status_code == 404
        w.as_account(w.outsider)
        assert w.client.post(base + '/discover/tenders').status_code == 403
        assert len(catalog.calls) == 1
    finally:
        w.doCleanups()
