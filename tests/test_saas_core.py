from types import SimpleNamespace
from fastapi.testclient import TestClient
from app.api.main import create_app
from app.api.config import ApiSettings
from app.api.landing import landing_html
from app.api.dashboard import dashboard_html


def test_landing_session_cta_and_no_fabricated_metrics():
    assert 'Sign In' in landing_html(False)
    assert 'Open Dashboard' in landing_html(True)
    assert 'Global Procurement Intelligence powered by AI' in landing_html()
    assert 'Find Opportunities' in landing_html()
    assert 'Multi-country procurement coverage' in landing_html()


def test_shell_navigation_and_accessibility():
    html = dashboard_html()
    for name in ['Overview', 'Discover', 'Companies', 'Team', 'Billing', 'Saved']:
        assert name in html
    assert 'aria-controls="appNav"' in html
    assert 'Skip to content' in html
    assert '/assets/shell.js' in html
    assert 'Create a company → Add products' in html


def test_public_assets_and_private_dashboard():
    app = create_app(runtime=SimpleNamespace(auth_service=None), settings=ApiSettings('127.0.0.1', 8000, False))
    with TestClient(app) as client:
        response = client.get('/')
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        assert 'VALYQON AI' in response.text
        assert client.get('/dashboard', follow_redirects=False).status_code == 303
        for path in ['/assets/saas.css', '/assets/shell.js']:
            assert client.get(path).status_code == 200
        assert client.get('/assets/../config.py').status_code == 404
