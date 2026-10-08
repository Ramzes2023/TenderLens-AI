"""Customer HTML contracts; fixtures and internal identifiers are not copy."""
from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from app.api.auth_pages import (
    login_html, register_html, verify_email_html, forgot_password_html,
    reset_password_html,
)
from app.api.dashboard import dashboard_html
from app.api.invitation_page import invitation_page_html
from app.api.landing import landing_html
from app.api.saas_shell import PAGES

ROOT = Path(__file__).resolve().parents[1]


class CustomerHTML(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.nodes = []
        self.copy = []
        self.script_depth = 0
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.nodes.append((tag, attrs))
        if tag in ('script', 'style'):
            self.script_depth += 1
        for name in ('placeholder', 'title', 'aria-label', 'alt'):
            if name in attrs:
                self.copy.append(attrs[name])

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.script_depth -= 1

    def handle_data(self, data):
        if not self.script_depth:
            self.copy.append(data)


PAGES_HTML = [landing_html, dashboard_html, login_html, register_html,
              verify_email_html, forgot_password_html, reset_password_html,
              lambda: invitation_page_html('audit-token')]


@pytest.mark.parametrize('page', PAGES_HTML)
def test_customer_copy_and_links_are_professional(page):
    parsed = CustomerHTML(page())
    copy = ' '.join(parsed.copy)
    assert 'VALYQON' in copy and 'AI' in copy
    assert not re.search(r'TenderLens|\b(?:TODO|FIXME|TBD|lorem ipsum)\b', copy, re.I)
    for forbidden in ('AluTrade', 'Municipal Infrastructure Authority',
                      'Industrial Pumping Equipment Supply', '€2.4M',
                      'legacy account namespace', 'raw token', 'next phase'):
        assert forbidden not in copy
    assert not re.search('[\u0400-\u04ff]', copy)
    for tag, attrs in parsed.nodes:
        if tag == 'a' and 'href' in attrs:
            assert attrs['href'] != '#'
            assert not attrs['href'].lower().startswith('javascript:')


def test_all_navigation_targets_and_palette_destinations_are_mapped():
    html = dashboard_html()
    parsed = CustomerHTML(html)
    nav = {a['data-nav'] for tag, a in parsed.nodes if 'data-nav' in a}
    assert nav == {label.lower().replace(' ', '-') for label in PAGES}
    static = {a['data-page'] for _, a in parsed.nodes if 'data-page' in a}
    shell = (ROOT / 'app/api/static/shell.js').read_text(encoding='utf-8')
    # Existing articles assigned by the shell plus explicitly honest future pages.
    assigned = {'companies', 'documents', 'monitoring', 'team', 'settings'}
    future = {'recommended', 'ai-analysis', 'notifications', 'billing'}
    assert nav == static | assigned | future
    for key in future:
        assert re.search(r"(?:'" + key + r"'|" + key + r"):'.*?not available", shell)
    ids = {a['id'] for _, a in parsed.nodes if 'id' in a}
    for tag, attrs in parsed.nodes:
        if tag == 'a' and attrs.get('href', '').startswith('#'):
            assert attrs['href'][1:] in nav | ids
    premium = (ROOT / 'app/api/static/premium.js').read_text(encoding='utf-8')
    palette = premium.split('/* VALYQON OVERVIEW V2 */')[0]
    assert "querySelectorAll('[data-nav]')" in palette
    assert 'location.hash=link.dataset.nav' in palette
    assert 'fetch(' not in palette


def test_unloaded_counts_and_future_pages_do_not_fabricate_results():
    html = dashboard_html()
    for ident in ('savedCount', 'historyCount', 'sourceHealthyCount',
                  'sourceFailedCount', 'sourceDisabledCount', 'sourceUncheckedCount'):
        assert re.search(r'id="' + ident + r'"[^>]*>\s*Not loaded\s*</strong>', html)
    shell = (ROOT / 'app/api/static/shell.js').read_text(encoding='utf-8')
    assert "billing:'Billing and paid plans are not available yet.'" in shell
    assert 'Configured personal Telegram alerts remain available' in shell
    assert 'Use Discover to inspect preliminary company fit' in shell
    for forbidden in ('Upgrade now', 'Checkout', 'unreadCount', 'recommendation-card'):
        assert forbidden not in html
    assert 'No search has been run here' in landing_html()
    assert '84<span>%' not in landing_html()


def test_modified_javascript_has_consistent_cache_versions():
    html = dashboard_html()
    for asset in ('shell', 'discovery', 'saved', 'history', 'source_health', 'support'):
        assert f'/assets/{asset}.js?v=phase24r' in html
    assert '/assets/responsive.css?v=phase24q' in html


def test_source_health_and_support_avoid_internal_error_copy():
    source = (ROOT / 'app/api/static/source_health.js').read_text(encoding='utf-8')
    assert 'escape(source.error_type)' not in source
    support = (ROOT / 'app/api/static/support.js').read_text(encoding='utf-8')
    assert 'AI assistant unavailable. General product guidance:' in support
    assert 'String(\n              payload.detail' not in support
    assert 'Connection unavailable. Please retry.' in support


def test_invitation_and_auth_errors_do_not_render_arbitrary_server_details():
    invitation = invitation_page_html('audit-token')
    assert 'JSON.stringify(data.detail)' not in invitation
    assert 'response.statusText' not in invitation
    assert 'data.detail||' not in login_html()
    assert "typeof data.detail==='string'?data.detail" not in reset_password_html()
    assert 'Sign in with the invited email address' in invitation


def test_phase24r_browser_behavior(tmp_path):
    node = shutil.which('node')
    if not node:
        pytest.skip('Existing Node runtime is required for browser regression tests')
    html = tmp_path / 'dashboard.html'
    html.write_text(dashboard_html(), encoding='utf-8')
    result = subprocess.run([node, 'tests/js/phase24r.test.cjs', str(html)],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
