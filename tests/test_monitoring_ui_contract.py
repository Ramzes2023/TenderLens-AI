from pathlib import Path

from app.api.dashboard import dashboard_html


ROOT = Path(__file__).resolve().parents[1]


def test_monitoring_center_explains_new_only_semantics():
    html = dashboard_html()

    assert "Monitoring center" in html

    assert (
        "Scan for new matches"
        in html
    )

    assert (
        "returns only matching notices"
        in html
    )

    assert (
        "Previously seen notices are"
        in html
    )

    assert (
        "intentionally suppressed"
        in html
    )


def test_monitoring_center_renders_status_dimensions():
    html = dashboard_html()

    for value in (
        'id="monitoringCompany"',
        'id="monitoringMode"',
        'id="monitoringFeeds"',
        'id="monitoringBackground"',
        'id="monitoringNotifications"',
        'id="monitoringAccess"',
        'id="monitoringExplanation"',
        'id="monitoringScanSummary"',
        'id="scanResults"',
    ):
        assert value in html


def test_monitoring_uses_existing_endpoints_only():
    html = dashboard_html()

    assert (
        "/monitoring/status"
        in html
    )

    assert (
        "/monitoring/scan"
        in html
    )

    assert (
        "monitoringContextKey"
        in html
    )

    assert (
        "canWriteWorkspace()"
        in html
    )


def test_monitoring_scan_has_stale_workspace_guard():
    html = dashboard_html()

    start = html.index(
        "async function scanEis()"
    )

    end = html.index(
        "async function refreshAll()",
        start,
    )

    script = html[
        start:end
    ]

    assert (
        "const context="
        in script
    )

    assert (
        "monitoringContextKey()"
        in script
    )

    assert (
        "const epoch="
        in script
    )

    assert (
        "state.uiEpoch"
        in script
    )

    assert (
        "context!==monitoringContextKey()"
        in script
    )


def test_monitoring_scan_is_clear_about_dedup_result():
    html = dashboard_html()

    start = html.index(
        "async function scanEis()"
    )

    end = html.index(
        "async function refreshAll()",
        start,
    )

    script = html[
        start:end
    ]

    assert (
        "These notices are now recorded as seen"
        in script
    )

    assert (
        "Previously seen matches are intentionally suppressed"
        in script
    )

    assert (
        "No new matching notices"
        in script
    )


def test_monitoring_ux_does_not_modify_matcher_module_contract():
    source = (
        ROOT
        / "app"
        / "monitoring"
        / "service.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "def _term_match("
        in source
    )

    assert (
        "def prefilter_notice("
        in source
    )


def test_monitoring_page_remains_shell_navigation_compatible():
    shell = (
        ROOT
        / "app"
        / "api"
        / "static"
        / "shell.js"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "monitoring:['monitoringCenter']"
        in shell
    )


def test_monitoring_center_is_dedicated_navigation_page():
    html = dashboard_html()

    assert (
        'id="monitoringCenter"'
        in html
    )

    assert (
        'data-page="monitoring"'
        in html
    )

    shell = (
        ROOT
        / "app"
        / "api"
        / "static"
        / "shell.js"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "monitoring:['monitoringCenter']"
        in shell
    )


def test_workspace_transition_resets_monitoring_ui():
    shell = (
        ROOT
        / "app"
        / "api"
        / "static"
        / "shell.js"
    ).read_text(
        encoding="utf-8"
    )

    required = [
        "function resetMonitoringUi()",
        "state.monitoringStatus=null",
        "monitoringCompany",
        "monitoringMode",
        "monitoringFeeds",
        "monitoringBackground",
        "monitoringNotifications",
        "monitoringAccess",
        "monitoringExplanation",
        "monitoringScanSummary",
        "scanResults",
        "scanButton",
        "resetMonitoringUi();",
        "state.uiEpoch++",
        "state.hasActiveCompany=false",
    ]

    for value in required:
        assert value in shell, value


def test_old_scan_results_are_cleared_on_workspace_switch():
    shell = (
        ROOT
        / "app"
        / "api"
        / "static"
        / "shell.js"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "Load a workspace to scan for new matching notices."
        in shell
    )

    assert (
        "results.innerHTML="
        in shell
    )


def test_responsive_shell_asset_cache_version():
    html = dashboard_html()

    assert (
        "/assets/shell.js?"
        "v=phase24r"
        in html
    )
