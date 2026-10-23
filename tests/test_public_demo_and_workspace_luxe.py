"""Public charts are labelled demonstrations until source data is accepted.

The demonstration is only client-side decoration; the real public search and
aggregated endpoints must remain database-backed and cannot return fake rows.
"""
from fastapi.testclient import TestClient
from app.api.landing import landing_html
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.dashboard import dashboard_html


def test_demo_marketing_mode_explicitly_enabled_and_labelled(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_ANALYTICS_MODE", "demo")
    monkeypatch.delenv("VALYQON_WEBSITE_REVIEW_ONLY", raising=False)
    html = landing_html()
    assert 'data-public-analytics-mode="demo"' in html
    assert 'data-review-charts="true"' not in html
    assert 'id="vqxReviewTools" hidden' in html
    assert 'id="vqPulseDemoDisclosure"' in html
    assert '/assets/public_intelligence.js' in html
    assert 'id="guestSearchForm"' in html


def test_real_mode_default_never_auto_invents_charts(monkeypatch):
    monkeypatch.delenv("VALYQON_PUBLIC_ANALYTICS_MODE", raising=False)
    html = landing_html()
    assert 'data-public-analytics-mode="demo"' not in html
    assert 'data-review-charts="true"' not in html


def test_demonstration_cannot_modify_real_guest_api_without_database(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_ANALYTICS_MODE", "demo")
    with TestClient(create_app(runtime=ApiRuntime())) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/v1/public/opportunities").status_code == 503
        assert client.get("/api/v1/public/market-intelligence").status_code == 503
        assert client.get("/api/v1/public/market-pulse").status_code == 503


def test_public_compose_opt_in_does_not_enable_paid_access():
    from pathlib import Path
    yaml = (Path(__file__).resolve().parents[1] / 'compose.public.yaml').read_text()
    assert 'VALYQON_PUBLIC_ANALYTICS_MODE: "demo"' in yaml
    assert 'VALYQON_RESTRICT_PAID_SOURCE_DETAILS: "true"' in yaml
    assert 'VALYQON_PUBLIC_AI_ENABLED: "true"' not in yaml


def test_real_workspace_has_navigation_without_synthetic_metrics():
    html = dashboard_html()
    for marker in (
        'id="vqSidebarCompact"',
        'class="vq-workspace-shortcuts"',
        'class="vq-action-center"',
        'id="vqActionHeading"',
        'id="vqActionCommand"',
        'href="#saved"',
        'href="#monitoring"',
        '/assets/workspace_luxe.css',
        '/assets/workspace_luxe.js',
    ):
        assert marker in html
    # Existing permissions and route names are not replaced by an example UI.
    assert 'data-nav="discover"' in html
    assert 'data-nav="source-health"' in html
    assert 'data-nav="support"' in html
    assert 'id="savedCount"' in html
    assert 'id="sourceHealthyCount"' in html


def test_workspace_interactions_are_navigation_only_and_js_parses():
    from pathlib import Path
    import shutil
    import subprocess
    root = Path(__file__).resolve().parents[1]
    js = root / "app/api/static/workspace_luxe.js"
    text = js.read_text(encoding="utf-8")
    for token in (
        "nav-group-toggle", "nav-group-links", "aria-expanded",
        "aria-current", "vqSidebarCompact", "vqActionCommand",
        "localStorage", "addEventListener('hashchange'",
    ):
        assert token in text
    for forbidden in ("fetch(", "innerHTML", "/api/v1/", "Math.random()"):
        assert forbidden not in text
    node = shutil.which("node")
    if node:
        for filename in ("workspace_luxe.js", "public_showcase.js", "public_intelligence.js"):
            path = root / "app/api/static" / filename
            result = subprocess.run([node, "--check", str(path)],
                                    capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, result.stderr


def test_both_pulse_and_dashboard_respond_to_explicit_demo_mode():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "app/api/static"
    charts = (root / "public_intelligence.js").read_text(encoding="utf-8")
    pulse = (root / "public_showcase.js").read_text(encoding="utf-8")
    assert "dataset.publicAnalyticsMode==='demo'" in charts
    assert "dataset.publicAnalyticsMode==='demo'" in pulse
    assert "valyqon-demo-chart-mode" in charts
    assert "valyqon-demo-chart-mode" in pulse
    assert "ILLUSTRATIVE FIGURES ONLY" in charts
    assert "all numbers in this chart are invented" in pulse
    # Neither script can write to the opportunity store or fabricate result cards.
    assert "/api/v1/public/opportunities" not in charts
    assert "/api/v1/public/opportunities" not in pulse
