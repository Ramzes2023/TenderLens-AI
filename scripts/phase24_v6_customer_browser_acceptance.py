"""Bounded OFFLINE_FIXTURE acceptance; never starts the production composition root.

The layered fallback uses existing disposable SQLite test factories and REAL login,
verification, session, RBAC and scoped routes. Saved is explicitly a storage double.
It cannot award PostgreSQL API_E2E or authenticated-browser PASS.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def require(condition, label):
    if not condition:
        raise AssertionError(label)


def profiles():
    common = dict(profile_version='phase24-v6-OFFLINE_FIXTURE', business_mode='sell',
                  max_contract_value=1000000, hard_stop_on_currency=True)
    return [dict(common, company_name='SYNTHETIC industrial cable supplier',
                 product_keywords=['cables'], search_keywords=['cables'],
                 accepted_currencies=['RON', 'EUR']),
            dict(common, company_name='SYNTHETIC SaaS accounting vendor',
                 product_keywords=['accounting'], search_keywords=['accounting'],
                 accepted_currencies=['EUR'])]


def payload():
    # Official-shaped schema and URL format only. These IDs are NOT observed notices.
    rows = [
        {'publication-number': '240001-2099', 'notice-title': {'eng': 'OFFLINE_FIXTURE industrial cables'},
         'total-value': 10000, 'total-value-cur': 'EUR', 'deadline-receipt-tender-date-lot': '2099-01-01'},
        {'publication-number': '240002-2099', 'notice-title': {'eng': 'OFFLINE_FIXTURE accounting SaaS subscription'},
         'total-value': 20000, 'total-value-cur': 'EUR'},
        {'publication-number': '240003-2099', 'notice-title': {'eng': 'OFFLINE_FIXTURE industrial cables'}},
        {'publication-number': '240004-2099', 'notice-title': {'eng': 'OFFLINE_FIXTURE industrial cables'},
         'total-value': 5000, 'total-value-cur': 'USD'},
        {'publication-number': '240005-2099', 'notice-title': {'eng': 'OFFLINE_FIXTURE office furniture'}},
    ]
    return {'notices': rows + [dict(rows[0])]}


def deny_network(*args, **kwargs):
    raise RuntimeError('OFFLINE_FIXTURE prohibits network connections')


@contextmanager
def isolated_customer():
    """Existing factory hook, unique accounts, finally cleanup, no forged cookies.

    Suppress dotenv and the module-level settings loader BEFORE importing main.
    Explicit runtime injection keeps build_runtime (DATABASE_URL) unreachable.
    """
    with ExitStack() as stack:
        # Block real HTTP transports, not socketpair used internally by Windows asyncio.
        # TestClient's ASGI transport and explicitly installed MockTransport remain usable.
        stack.enter_context(patch('httpx.HTTPTransport.handle_request', deny_network))
        stack.enter_context(patch('httpx.AsyncHTTPTransport.handle_async_request', deny_network))
        stack.enter_context(patch('dotenv.load_dotenv', return_value=False))
        from app.api.config import ApiSettings, load_api_settings
        stack.enter_context(patch('app.api.config.load_dotenv', return_value=False))
        stack.enter_context(patch('app.api.config.load_api_settings',
                                  return_value=ApiSettings('127.0.0.1', 0, False, None)))
        from tests import test_organization_workflows as factories
        # main imports the loader by value. Restore that alias after its safe import
        # so later regression tests in the same process don't retain this test stub.
        import app.api.main as main_module
        main_module.load_api_settings = load_api_settings
        stack.enter_context(patch('app.api.main.build_runtime', side_effect=RuntimeError('Production runtime prohibited')))
        from app.auth import AuthService
        from app.organizations import OrganizationRepository
        original_register = AuthService.register
        original_create = OrganizationRepository.create
        run_id = uuid.uuid4().hex
        password = secrets.token_urlsafe(24)

        def register(service, email, ignored_password):
            local = email.split('@')[0]
            return original_register(service, f'{local}-{run_id}@example.invalid', password)

        def create(repository, name, owner_id):
            return original_create(repository, f'SYNTHETIC {name} {run_id}', owner_id)

        customer = factories.OrganizationWorkflowTests()
        try:
            with patch.object(AuthService, 'register', register), patch.object(OrganizationRepository, 'create', create):
                customer.setUp()
            customer.run_id = run_id
            customer.password = password
            customer.client.cookies.clear()
            yield customer
        finally:
            customer.doCleanups()


def login(customer, account):
    customer.client.cookies.clear()
    account, _ = customer.auth.repository.find_account_by_email(account.email)
    if not account.email_verified:
        # Existing service hook issues a token in this disposable DB; actual route consumes it.
        token, _ = customer.auth.issue_email_verification(account)
        response = customer.client.post('/api/v1/auth/verify-email', json={'token': token})
        require(response.status_code == 200, 'synthetic email verification route')
    response = customer.client.post('/api/v1/auth/login',
                                   json={'email': account.email, 'password': customer.password})
    require(response.status_code == 200, 'actual login route')
    require('httponly' in response.headers.get('set-cookie', '').lower(), 'session HttpOnly')
    return response


def create_company(customer, index=0):
    profile = profiles()[index]
    response = customer.client.post(customer.base('/companies'),
        json={'name': profile['company_name'] + ' ' + customer.run_id, 'profile': profile})
    require(response.status_code == 201, 'create synthetic scoped company')
    return response.json()


@contextmanager
def offline_sources(customer, *, ted_status=200, after_fetch=None):
    import httpx
    from app.sources.http import source_client
    from app.sources.catalog import SourceCatalog
    from app.sources.multi import MultiSourceFetcher
    from app.sources.registry import SourceRegistration, SourceRegistry
    from app.sources.ted_api import TedApiSource
    from app.sources.uk_fts_api import UkFindTenderApiSource
    calls = []

    def respond(request):
        calls.append((request.method, request.url.host))
        if request.url.host == 'api.ted.europa.eu':
            require(request.method == 'POST', 'TED adapter request method')
            if after_fetch:
                after_fetch()
            return httpx.Response(ted_status, json=payload())
        require(request.url.host == 'www.find-tender.service.gov.uk', 'fixture transport host')
        return httpx.Response(503, json={'OFFLINE_FIXTURE': 'deliberate partial failure'})

    def client(**kwargs):
        return source_client(**kwargs, transport=httpx.MockTransport(respond))

    registry = SourceRegistry([
        SourceRegistration('ted', 'TED OFFLINE_FIXTURE', TedApiSource(timeout=1), jurisdictions=('EU',)),
        SourceRegistration('uk_fts', 'UK FTS OFFLINE_FIXTURE', UkFindTenderApiSource(timeout=1), jurisdictions=('UK',)),
    ])
    customer.client.app.state.runtime.source_catalog = SourceCatalog(registry, MultiSourceFetcher(registry, concurrency=1))
    with patch('app.sources.ted_api.source_client', client), patch('app.sources.uk_fts_api.source_client', client):
        yield calls


def evaluation_matrix():
    from app.monitoring.service import prefilter_notice
    from app.scoring.models import CompanyProfile
    from app.scoring.preview import score_metadata_preview
    from app.services.tender_analysis import analysis_from_notice
    from app.sources.ted_api import parse_ted_search_response
    notices = parse_ted_search_response(payload())
    rows = []
    for data in profiles():
        profile = CompanyProfile(**data)
        for notice in notices:
            score = score_metadata_preview(analysis_from_notice(notice), profile)
            rows.append(dict(company=data['company_name'], external_id=notice.external_id,
                             title=notice.title, prefilter_matched=prefilter_notice(notice, profile) is not None,
                             scoring=score.model_dump(mode='json'), evidence='OFFLINE_FIXTURE'))
    return rows


def journey(customer):
    from tests.test_phase24_customer_acceptance import ScopedMemorySaved
    login(customer, customer.owner)
    cable = create_company(customer)
    saas = create_company(customer, 1)
    with offline_sources(customer) as calls:
        require(not calls, 'no retrieval before explicit Find')
        response = customer.client.post(customer.base('/discover/tenders'))
        require(response.status_code == 200, 'explicit Find')
        report = response.json()
        require(report['partial_failure'] and not report['total_failure'], 'partial transport failure')
        require(report['failed_sources'] == ['uk_fts'], 'UK fixture failure recorded')
        items = report['items']
        require(len({(i['source'], i['external_id']) for i in items}) == len(items), 'deduplicated opportunity identities')
        require('240001-2099' in {i['external_id'] for i in items}, 'actual positive cable prefilter')
        require('240002-2099' not in {i['external_id'] for i in items}, 'actual negative accounting prefilter')
        for item in items:
            require(item['analysis_stage'] == 'metadata_preview' and not item['full_ai_analyzed'], 'metadata semantics')
        customer.client.app.state.runtime.tender_repository = ScopedMemorySaved(customer)
        item = next(i for i in items if i['external_id'] == '240001-2099')
        saved = customer.client.post(customer.base('/shortlist'), json=item)
        require(saved.status_code == 200, 'scoped Save with labelled storage double')
        require(customer.client.post(customer.base('/shortlist'), json=item).json()['id'] == saved.json()['id'], 'Save dedup')
        require(len(customer.client.get(customer.base('/shortlist')).json()) == 1, 'Saved scoped list')
        require(customer.client.post(customer.base(f"/companies/{saas['id']}/activate")).status_code == 200, 'company switch')
        require(customer.client.get(customer.base('/shortlist')).json() == [], 'Saved company isolation')
        require(customer.client.post(customer.base('/shortlist'), json=item).status_code == 409, 'stale Save conflict')
        customer.client.app.state.runtime.tender_repository = None
        other = customer.client.post(customer.base('/discover/tenders')).json()
        require({i['external_id'] for i in other['items']} == {'240002-2099'}, 'accounting company result isolation')
        customer.client.app.state.runtime.tender_repository = ScopedMemorySaved(customer)
        forged = dict(item, preliminary_provenance=dict(item['preliminary_provenance'], organization_id=999999))
        require(customer.client.post(customer.base('/shortlist'), json=forged).status_code == 409, 'forged organization provenance')
        login(customer, customer.viewer)
        require(customer.client.post(customer.base('/shortlist'), json=other['items'][0]).status_code == 403, 'viewer Save forbidden')
        login(customer, customer.outsider)
        before = len(calls)
        require(customer.client.post(customer.base('/discover/tenders')).status_code == 403, 'cross tenant Find denied')
        require(customer.client.get(customer.base('/shortlist')).status_code == 403, 'cross tenant Saved denied')
        require(len(calls) == before, 'denied user causes no procurement transport')
        customer.client.cookies.clear()
        require(customer.client.post(customer.base('/discover/tenders')).status_code == 401, 'anonymous Find denied')
        return dict(items=len(items), second_company_items=len(other['items']), transport_calls=len(calls),
                    cable_company_id=cable['id'], storage='SCOPED_MEMORY_DOUBLE_NOT_POSTGRESQL')


def stdout_status(report):
    for key, value in dict(V6_CODE_CHANGES='YES', V6_AUTHENTICATED_API=report['API_E2E'],
                          V6_AUTHENTICATED_BROWSER=report['BROWSER_AUTHENTICATED'],
                          V6_REAL_TED_IN_THIS_RUN='NO', V6_LIVE_PRIOR_EVIDENCE='5_NOT_REPROBED',
                          V6_PRODUCTION_GATE='BLOCKED',
                          V6_REPORT='docs/PHASE24_AUTHENTICATED_CUSTOMER_V6.md').items():
        print(f'{key}={value}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true', required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    # Refuse overwriting source/config/secret files through the report argument.
    if args.report.suffix.lower() != '.json':
        parser.error('--report must be a JSON output path')
    report = dict(evidence='OFFLINE_FIXTURE', timestamp=datetime.now(timezone.utc).isoformat(),
                  API_E2E='NOT_VERIFIED', BROWSER_AUTHENTICATED='NOT_VERIFIED',
                  layered_api='NOT_VERIFIED', dom_script='NOT_VERIFIED', real_results_count=0,
                  outbound_calls=0, LIVE_TED_PRIOR='5_NOT_REPROBED', prior_matching_count=0,
                  production_gate='BLOCKED', blockers=[
                      'PostgreSQL Saved persistence is not exercised by the layered fallback.',
                      'No authenticated Chromium session is executed; DOM script is not a browser.',
                      'Prior live TED had 0/5 matches; no fresh HTTP request in V6.'])
    code = 0
    try:
        with isolated_customer() as customer:
            report['matrix'] = evaluation_matrix()
            require(len(report['matrix']) == 10, 'five deduplicated fixtures evaluated against two profiles')
            for profile in profiles():
                rows = [r for r in report['matrix'] if r['company'] == profile['company_name']]
                require(any(r['prefilter_matched'] for r in rows), 'positive prefilter evidence for each company')
                require(any(not r['prefilter_matched'] for r in rows), 'negative prefilter evidence for each company')
            report['journey'] = journey(customer)
        report['layered_api'] = 'PASS'
    except Exception as error:
        # No exception text, URLs, passwords or cookies are serialized.
        report['layered_api'] = 'FAIL'
        report['failure_type'] = type(error).__name__
        if isinstance(error, ModuleNotFoundError):
            report['layered_api'] = 'NOT_VERIFIED'
            report['blockers'].append('Required Python module unavailable: ' + str(error.name))
        elif isinstance(error, AssertionError):
            report['failed_check'] = str(error)[:160]
        code = 1
    node = shutil.which('node')
    if node:
        try:
            result = subprocess.run([node, str(ROOT / 'tests/js/main_phase24_v6_customer_journey.test.cjs')],
                                    cwd=ROOT, capture_output=True, text=True, timeout=60)
            report['dom_script'] = 'PASS' if result.returncode == 0 else 'FAIL'
            code = max(code, int(result.returncode != 0))
        except (OSError, subprocess.TimeoutExpired):
            report['dom_script'] = 'FAIL'
            code = 1
    else:
        report['blockers'].append('Node unavailable; DOM script not executed.')
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
    stdout_status(report)
    print('V6_LAYERED_API=' + report['layered_api'])
    return code


if __name__ == '__main__':
    raise SystemExit(main())
