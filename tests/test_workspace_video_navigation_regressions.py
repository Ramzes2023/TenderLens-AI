"""Video-observed workspace defects: independent scroll and degraded-service truth."""
from pathlib import Path

from app.api.dashboard import dashboard_html

ROOT = Path(__file__).resolve().parents[1]


def test_long_navigation_scrolls_without_covering_sidebar_footer():
    css = (ROOT / "app/api/static/workspace_luxe.css").read_text(encoding="utf-8")
    assert 'body.saas .app-nav > nav' in css
    assert 'overflow-y:auto' in css
    assert 'body.saas .app-nav > .sidebar-context' in css
    assert 'flex:0 0 auto' in css
    assert 'position:static' in css
    html = dashboard_html()
    assert '<div class="sidebar-context">' in html
    assert 'id="vqSidebarCompact"' in html
    assert 'href="#notifications"' in html
    assert 'href="#billing"' in html


def test_unavailable_optional_capabilities_are_scoped_not_fake():
    js = (ROOT / "app/api/organization_ui.py").read_text(encoding="utf-8")
    dashboard = (ROOT / "app/api/dashboard.py").read_text(encoding="utf-8")
    assert 'await loadCompanies();' in js
    assert 'Promise.allSettled([' in js
    assert "unavailable.push('monitoring')" in js
    assert "unavailable.push('PDF tender history')" in js
    assert "Some workspace services could not be loaded:" in js
    assert "Your account and organization are still available." in js
    assert "const health = loadHealth().catch" in dashboard
    assert "await Promise.all([health,loadWorkspaceData()]);" in dashboard
    # Critical account and organization loading must still fail truthfully.
    assert "await loadAccount();" in dashboard
    assert "await loadOrganizations();" in dashboard
    assert "Workspace unavailable. Check your connection" in dashboard
    assert "fake" not in js[js.index("async function loadWorkspaceData"):js.index("async function loadOrganizations")]


def test_rendered_dashboard_inline_js_parses_when_node_is_available(tmp_path):
    import shutil
    import subprocess
    import re
    node = shutil.which("node")
    if not node:
        return
    html = dashboard_html()
    scripts = re.findall(r"<script(?:\s[^>]*)?>([\s\S]*?)</script>", html)
    assert scripts, "Dashboard should include inline organization code"
    js = "\n".join(scripts)
    output = tmp_path / "dashboard-inline.js"
    output.write_text(js, encoding="utf-8")
    result = subprocess.run([node, "--check", str(output)],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
