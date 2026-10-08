"""Shared responsive structure contracts; no services or browser dependencies."""
from html.parser import HTMLParser
from pathlib import Path

import pytest

from app.api.auth_pages import (
    login_html, register_html, verify_email_html,
    forgot_password_html, reset_password_html,
)
from app.api.dashboard import dashboard_html
from app.api.invitation_page import invitation_page_html
from app.api.landing import landing_html
from app.api.main import create_app
from app.api.config import ApiSettings
from fastapi.testclient import TestClient
from types import SimpleNamespace


class Structure(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.nodes = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs)))

    def by_id(self, value):
        return next(attrs for _, attrs in self.nodes if attrs.get('id') == value)


@pytest.mark.parametrize('page', [
    dashboard_html, landing_html, login_html, register_html, verify_email_html,
    forgot_password_html, reset_password_html, lambda: invitation_page_html('test'),
])
def test_pages_share_responsive_styles_and_one_scalable_viewport(page):
    nodes = Structure(page()).nodes
    viewports = [a for t, a in nodes if t == 'meta' and a.get('name') == 'viewport']
    assert len(viewports) == 1
    assert 'width=device-width' in viewports[0]['content']
    assert 'user-scalable=no' not in viewports[0]['content']
    assert 'maximum-scale' not in viewports[0]['content']
    styles = [a['href'].split('?')[0] for t, a in nodes if t == 'link' and a.get('rel') == 'stylesheet']
    assert styles[-1] == '/assets/responsive.css'


def test_navigation_keeps_all_real_pages_reachable():
    structure = Structure(dashboard_html())
    toggle = structure.by_id('navToggle')
    assert toggle['aria-controls'] == 'appNav'
    assert toggle['aria-expanded'] == 'false'
    links = [a for t, a in structure.nodes if t == 'a' and 'data-nav' in a]
    for page in ('discover', 'saved', 'companies', 'documents', 'monitoring',
                 'search-history', 'source-health', 'support', 'team', 'settings'):
        assert any(a.get('href') == '#' + page for a in links)
    assert structure.by_id('pageHeading')['tabindex'] == '-1'


@pytest.mark.parametrize('control', [
    'discoverButton', 'filterKeyword', 'filterSource', 'filterValue', 'resetFilters',
    'refreshSaved', 'refreshHistory', 'companyName', 'createCompanyButton',
    'companyPdfFile', 'companyPdfAnalyzeButton', 'scanButton', 'inviteButton',
    'supportAssistantSubmit', 'supportTicketForm', 'refreshSourceHealth',
])
def test_customer_workflow_controls_survive_shared_shell(control):
    assert Structure(dashboard_html()).by_id(control)


@pytest.mark.parametrize('page,fields', [
    (login_html, ['email', 'password', 'submit']),
    (register_html, ['email', 'password', 'submit']),
    (verify_email_html, ['verifyEmail', 'resend']),
    (forgot_password_html, ['email', 'submit']),
    (reset_password_html, ['password', 'confirmPassword', 'submit']),
])
def test_auth_controls_and_labels_remain(page, fields):
    structure = Structure(page())
    labels = [a.get('for') for t, a in structure.nodes if t == 'label']
    for field in fields:
        attrs = structure.by_id(field)
        if field not in ('submit', 'resend'):
            assert field in labels
            assert attrs.get('autocomplete')


def test_tender_dialogs_keep_named_close_controls_and_pdf_actions():
    structure = Structure(dashboard_html())
    for dialog, close in [('tenderDetail', 'closeDetail'), ('savedDetail', 'closeSavedDetail'),
                          ('historyTenderDetail', 'closeHistoryTenderDetail'),
                          ('commandPalette', 'closeCommands')]:
        assert structure.by_id(dialog)['aria-labelledby']
        assert structure.by_id(close) is not None
    assert structure.by_id('companyPdfFile')['accept'] == '.pdf,application/pdf'
    script = (Path(__file__).parents[1] / 'app/api/static/discovery.js').read_text(encoding='utf-8')
    assert 'data-full-ai-file=' in script and 'data-full-ai=' in script
    assert 'aria-label="Tender PDF for full AI analysis"' in script


def test_responsive_asset_is_served_without_runtime_services():
    app = create_app(runtime=SimpleNamespace(auth_service=None),
                     settings=ApiSettings('127.0.0.1', 8000, False))
    with TestClient(app) as client:
        response = client.get('/assets/responsive.css')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/css')
    # Guard the small shared breakpoint strategy, not individual declaration strings.
    import re
    widths = re.findall(r'@media\s*\(max-width:(\d+)px\)', response.text)
    assert len(widths) <= 3
    assert sorted(map(int, widths)) == [420, 760, 1050]


def test_customer_lists_are_cards_rather_than_uncontained_tables():
    structure = Structure(dashboard_html())
    assert not any(t == 'table' for t, _ in structure.nodes)
    for region in ('discoveryResults', 'savedResults', 'historyRuns', 'sourceHealthResults'):
        assert structure.by_id(region)['aria-label']
