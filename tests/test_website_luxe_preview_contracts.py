"""New product visuals must be well-formed, locally testable and never fake public data."""
from pathlib import Path
import shutil
import subprocess
from fastapi.testclient import TestClient
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.landing import landing_html

ROOT = Path(__file__).resolve().parents[1]


def test_live_public_version_does_not_activate_preview_chart_fixtures(monkeypatch):
    monkeypatch.delenv("VALYQON_WEBSITE_REVIEW_ONLY", raising=False)
    html = landing_html()
    assert 'data-review-charts="true"' not in html
    assert 'id="vqxReviewTools" hidden' in html
    assert 'id="vqxToggleDemo"' in html
    # No fake market stats are printed in the live HTML.
    assert "186" not in html.split("vqxHeroTotal")[1].split("vqxHeroFresh")[0]


def test_only_isolated_review_can_expose_illustrative_toggle(monkeypatch):
    monkeypatch.setenv("VALYQON_WEBSITE_REVIEW_ONLY", "1")
    html = landing_html()
    assert 'data-review-charts="true"' in html
    compose = (ROOT / "ops/website_preview/compose.yaml").read_text(encoding="utf-8")
    assert 'VALYQON_WEBSITE_REVIEW_ONLY: "1"' in compose
    assert 'VALYQON_RESTRICT_PAID_SOURCE_DETAILS: "true"' in compose
    assert 'VALYQON_PUBLIC_AI_ENABLED: "false"' in compose
    assert '127.0.0.1:18865:8000' in compose


def test_public_chart_endpoint_not_seeded_and_no_tender_identity_fields():
    with TestClient(create_app(runtime=ApiRuntime())) as client:
        response = client.get("/api/v1/public/market-intelligence")
        assert response.status_code == 503
    js = (ROOT / "app/api/static/public_intelligence.js").read_text(encoding="utf-8")
    assert "dataset.reviewCharts!=='true'" in js
    assert "ILLUSTRATIVE DESIGN DATA ONLY" in js
    assert "getReport();" in js
    assert "textContent" in js
    assert "innerHTML" not in js


def test_new_chart_javascript_parses_in_existing_node_environment():
    node = shutil.which("node")
    if not node:
        return
    for name in ("public_intelligence.js", "public_showcase.js", "guest_search.js"):
        path = ROOT / "app/api/static" / name
        result = subprocess.run([node, "--check", str(path)],
                                capture_output=True, text=True, timeout=12)
        assert result.returncode == 0, (name, result.stderr)
