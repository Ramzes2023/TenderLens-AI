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
