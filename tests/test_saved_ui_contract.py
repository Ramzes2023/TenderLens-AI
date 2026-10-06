from pathlib import Path

from app.api.dashboard import dashboard_html


ROOT = Path(__file__).resolve().parents[1]


def test_saved_opportunities_is_real_workspace_page():
    html = dashboard_html()

    assert 'id="savedWorkspace"' in html
    assert 'data-page="saved"' in html
    assert 'Saved opportunities' in html
    assert '/assets/saved.js?v=phase24-saved-ui-v1-20261006' in html
    assert 'The Saved Opportunities page is coming next.' not in html


def test_saved_ui_uses_existing_company_scoped_shortlist_api():
    js = (
        ROOT
        / "app"
        / "api"
        / "static"
        / "saved.js"
    ).read_text(
        encoding="utf-8"
    )

    assert "/shortlist" in js
    assert "method:'DELETE'" in js
    assert "credentials:'same-origin'" in js
    assert "cache:'no-store'" in js
    assert "ValyqonDiscovery" in js
    assert "activeCompanyId" in js


def test_discover_refreshes_saved_state_when_reopened():
    js = (
        ROOT
        / "app"
        / "api"
        / "static"
        / "discovery.js"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "location.hash.slice(1)||'overview'"
        in js
    )
    assert (
        "==='discover')loadShortlist()"
        in js
    )
