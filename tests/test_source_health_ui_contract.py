from pathlib import Path

from app.api.dashboard import (
    dashboard_html,
)


ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)


def test_source_health_is_real_workspace():
    html = dashboard_html()

    assert (
        'id="sourceHealthWorkspace"'
        in html
    )

    assert (
        'data-page="source-health"'
        in html
    )

    assert (
        'href="#source-health"'
        in html
    )

    assert (
        "Source Health"
        in html
    )

    assert (
        "/assets/source_health.js?"
        "v=phase24r"
        in html
    )


def test_source_health_ui_is_read_only():
    js = (
        ROOT
        / "app"
        / "api"
        / "static"
        / "source_health.js"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "/discovery/source-health"
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
        'method:"POST"'
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
        "does not trigger a new source check"
        in js
    )


def test_source_health_ui_exposes_all_states():
    js = (
        ROOT
        / "app"
        / "api"
        / "static"
        / "source_health.js"
    ).read_text(
        encoding="utf-8"
    )

    for label in (
        "Healthy",
        "Failed",
        "Disabled",
        "Not checked",
    ):
        assert label in js

    assert "Response time:" in js
    assert "Results returned:" in js
    assert "Open official source" in js


def test_source_health_hides_raw_backend_messages():
    js = (
        ROOT
        / "app"
        / "api"
        / "static"
        / "source_health.js"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "Source could not be reached "
        "during the latest Discovery."
        in js
    )

    assert (
        "${escape(source.message)}"
        not in js
    )
