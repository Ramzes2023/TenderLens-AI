"""New premium workbench UI must be functional, context-truthful and safe.

No fake company counts, tender rows, API calls, claim that a search attempt
proves source connectivity, or disconnected decorative interaction.
"""
from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess

from app.api.dashboard import dashboard_html

ROOT = Path(__file__).resolve().parents[1]


def test_workbench_renders_in_original_authenticated_dashboard():
    html = dashboard_html()
    for element in (
        'id="vqWorkbench"', 'id="vqWbOrg"', 'id="vqWbCompany"',
        'id="vqWbDiscovered"', 'id="vqWbSaved"', 'id="vqWorkbenchState"',
        'id="vqProgressSteps"', 'id="vqProgressFill"', 'id="vqProgressCount"',
        'id="vqNextLink"', 'id="vqPinnedPages"', 'id="vqRecentPages"',
        'id="vqPinCurrent"', 'id="vqCurrentSection"',
        'id="vqShortcutHelp"', 'id="vqShortcutDialog"',
        'id="vqShortcutClose"', 'id="vqUtilityBar"',
        '/assets/workspace_home.css', '/assets/workspace_home.js',
    ):
        assert element in html, element
    assert '{WORKSPACE_HOME_HTML}' not in html
    assert '{WORKSPACE_UTILITIES_HTML}' not in html
    assert html.count('id="vqWorkbench"') == 1
    assert html.count('id="vqUtilityBar"') == 1
    assert 'href="#team"' in html
    assert 'href="#companies"' in html
    assert 'href="#discover"' in html
    assert 'href="#saved"' in html
    assert html.index('/assets/workspace_home.css') < html.index('/assets/responsive.css')
    assert html.index('/assets/workspace_home.js') > html.index('/assets/workspace_luxe.js')


def test_workbench_contains_no_fake_tender_values_or_live_source_promises():
    html = dashboard_html()
    start = html.index('id="vqWorkbench"')
    end = html.index('id="firstRunPreview"', start)
    part = html[start:end]
    for invented in ('186', '12500', '89%', '50,000', '23.4%', 'market share'):
        assert invented not in part
    assert "A search attempt is not proof that sources work" in part
    assert "Only page navigation is saved in this browser" in part
    js = (ROOT / 'app/api/static/workspace_home.js').read_text(encoding='utf-8')
    for forbidden in ("fetch(", "XMLHttpRequest", "sendBeacon", "innerHTML",
                      "Math.random(", "window.open(", "/api/v1/"):
        assert forbidden not in js
    assert 'Number.isInteger(state.activeCompanyId)' in js
    assert 'Number.isInteger(state.accountId)' in js
    assert 'count(' in js
    assert 'No scans, alerts or AI tasks run automatically' in part


def test_pins_and_recent_paths_are_whitelisted_and_stored_only_locally():
    js = (ROOT / 'app/api/static/workspace_home.js').read_text(encoding='utf-8')
    assert "routeLinks.has(item)" in js
    assert "routeLinks.has(hash)" in js
    assert "new Set(" in js
    assert "localStorage" in js
    assert "sessionStorage" in js
    assert "pinnedKey" in js and "recentKey" in js
    assert "aria-pressed" in js
    assert "aria-valuenow" in js
    assert "closest('input, textarea, select" in js
    assert "showModal()" in js


def test_workbench_javascript_syntax_using_node_if_present(tmp_path):
    node=shutil.which('node')
    if not node:
        return
    js=ROOT/'app/api/static/workspace_home.js'
    result=subprocess.run([node,'--check',str(js)],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    html=dashboard_html()
    inline=re.findall(r'<script(?:\s[^>]*)?>([\s\S]*?)</script>',html)
    assert inline
    out=tmp_path/'auth-dashboard-inline.js'
    out.write_text('\n'.join(inline),encoding='utf-8')
    result=subprocess.run([node,'--check',str(out)],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr


def test_no_unprotected_extra_api_routes_or_new_authority():
    from app.api.main import create_app
    from app.api.runtime import ApiRuntime
    app=create_app(runtime=ApiRuntime())
    assert not any('/workbench' in getattr(route,'path','') for route in app.routes)
