"""Chromium team controls -> authenticated ASGI routes -> disposable SQLite.

Only the page transport is intercepted; API responses come from actual handlers.
The tender is explicitly OFFLINE_FIXTURE, never a customer or live source record.
"""
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

import pytest


def test_team_assignment_approval_refresh_and_viewer_in_chromium():
    playwright = pytest.importorskip('playwright.sync_api')
    from scripts import phase24_v6_customer_browser_acceptance as factory
    from app.api.saved_ui import SAVED_HTML
    from app.api.security import SESSION_COOKIE
    from app.database.backend import Database
    from app.database.config import DatabaseSettings

    with factory.isolated_customer() as customer, playwright.sync_playwright() as p:
        db = Database(DatabaseSettings('', customer.path))
        db.migrate()
        customer.client.app.state.runtime.database = db
        try:
            factory.login(customer, customer.owner)
            company = factory.create_company(customer)
            org = customer.organization.id
            with closing(db.connect()) as conn, conn:
                conn.execute('INSERT INTO saved_opportunities '
                    '(organization_id,company_id,source,external_id,snapshot_json,created_at,updated_at) '
                    'VALUES (?,?,?,?,?,?,?)',
                    (org, company['id'], 'eis', 'OFFLINE_FIXTURE-browser-team', '{}', 'now', 'now'))
                saved = conn.execute('SELECT id FROM saved_opportunities WHERE organization_id=?',
                                     (org,)).fetchone()[0]
                conn.execute("UPDATE organization_members SET role='admin' WHERE organization_id=? AND account_id=?",
                             (org, customer.member.id))
            browser = p.chromium.launch()
            try:
                context = browser.new_context()
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))

                def dispatch(route):
                    request = route.request
                    if request.url == 'http://testserver/fixture':
                        route.fulfill(content_type='text/html', body=SAVED_HTML)
                        return
                    if urlsplit(request.url).netloc != 'testserver':
                        route.abort()
                        return
                    customer.client.cookies.clear()
                    response = customer.client.request(request.method, request.url,
                        headers=request.headers, content=request.post_data_buffer, follow_redirects=False)
                    route.fulfill(status=response.status_code,
                        content_type='application/json', body=response.content)

                page.route('**/*', dispatch)

                def open_as(account):
                    factory.login(customer, account)
                    context.clear_cookies()
                    context.add_cookies([dict(name=SESSION_COOKIE,
                        value=customer.client.cookies.get(SESSION_COOKIE), url='http://testserver')])
                    page.goto('http://testserver/fixture')
                    page.evaluate('(s) => {window.state=s; document.querySelector("#savedDetail").showModal()}',
                                  dict(accountId=account.id, organizationId=org, activeCompanyId=company['id']))
                    page.add_script_tag(content=Path('app/api/static/tender_team.js').read_text(encoding='utf-8'))
                    page.evaluate('(s) => window.dispatchEvent(new CustomEvent("valyqon-saved-detail-open", {detail:s}))',
                                  dict(id=saved, organizationId=org, companyId=company['id']))
                    page.wait_for_function('document.querySelector("#savedTenderTeamApproval").textContent !== "—"')

                open_as(customer.owner)
                page.select_option('#savedTenderAssignee', str(customer.member.id))
                page.click('#saveTenderAssignee')
                page.wait_for_function('document.querySelectorAll("#savedTenderTeamEvents li").length === 1 && '
                                       'document.querySelector("#savedTenderTeamEvents").textContent.includes("assign")')
                page.click('#requestTenderApproval')
                page.wait_for_function('document.querySelector("#savedTenderTeamApproval").textContent === "Awaiting review"')
                assert page.locator('#approveTenderParticipation').is_disabled()
                open_as(customer.member)
                page.click('#approveTenderParticipation')
                page.wait_for_function('document.querySelector("#savedTenderTeamApproval").textContent === "Approved internally"')
                open_as(customer.viewer)
                assert page.locator('#savedTenderTeamApproval').inner_text() == 'Approved internally'
                assert page.locator('#saveTenderAssignee').is_disabled()
                assert page.locator('#requestTenderApproval').is_disabled()
                with closing(db.connect()) as conn:
                    persisted = conn.execute('SELECT revision,approval_state,assignee_account_id '
                        'FROM saved_tender_team_decisions WHERE saved_opportunity_id=?', (saved,)).fetchone()
                    assert tuple(persisted) == (3, 'approved', customer.member.id)
                    assert conn.execute('SELECT count(*) FROM saved_tender_team_decision_events '
                        'WHERE saved_opportunity_id=?', (saved,)).fetchone()[0] == 3
                assert errors == []
            finally:
                browser.close()
        finally:
            db.close()
