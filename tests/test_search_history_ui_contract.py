from pathlib import Path

from app.api.dashboard import (
    dashboard_html,
)


ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)


def test_search_history_is_real_workspace_page():
    html = dashboard_html()

    assert (
        'id="historyWorkspace"'
        in html
    )

    assert (
        'data-page="search-history"'
        in html
    )

    assert (
        "Search history"
        in html
    )

    assert (
        "/assets/history.js?"
        "v=phase24-search-history-v2-20261006"
        in html
    )

    assert (
        'href="#search-history"'
        in html
    )


def test_search_history_ui_uses_snapshot_api_only():
    js = (
        ROOT
        / "app"
        / "api"
        / "static"
        / "history.js"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "/discovery/history"
        in js
    )

    assert (
        "/discover/tenders"
        not in js
    )

    assert (
        "method:'POST'"
        not in js
    )

    assert (
        "credentials:'same-origin'"
        in js
    )

    assert (
        "cache:'no-store'"
        in js
    )

    assert (
        "ValyqonDiscovery"
        in js
    )

    assert (
        "activeCompanyId"
        in js
    )

    assert (
        "No procurement sources were queried."
        in js
    )


def test_search_history_snapshot_is_read_only():
    js = (
        ROOT
        / "app"
        / "api"
        / "static"
        / "history.js"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "renderer.card("
        in js
    )

    assert (
        "renderer.detail(item)"
        in js
    )

    assert (
        "/shortlist"
        not in js
    )


def test_search_history_uses_ascii_separators():
    js = (
        ROOT
        / "app"
        / "api"
        / "static"
        / "history.js"
    ).read_text(
        encoding="utf-8"
    )

    assert " | " in js
    assert "Discovery #${id} - " in js
