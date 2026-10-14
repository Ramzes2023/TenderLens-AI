"""Offline HTTP contracts: guest onboarding and disabled commercial checkout."""
from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime


def test_guest_routes_and_commercial_gate_without_services():
    # Explicit empty runtime: do not initialize databases, providers or adapters.
    app = create_app(runtime=ApiRuntime(), settings=ApiSettings('127.0.0.1', 8000, False))
    with TestClient(app) as client:
        landing = client.get('/')
        assert landing.status_code == 200
        assert 'Billing is not enabled' in landing.text
        assert landing.headers['Cache-Control'] == 'no-store'
        for route in ('/login', '/register'):
            response = client.get(route)
            assert response.status_code == 200
            assert response.headers['Cache-Control'] == 'no-store'
        guest = client.get('/dashboard', follow_redirects=False)
        assert guest.status_code == 303
        assert guest.headers['location'].startswith('/login')
        for route in ('/api/v1/billing/checkout', '/api/v1/checkout'):
            assert client.post(route, json={'plan': 'pilot'}).status_code == 404
        # The configured-status endpoint itself is a tenant boundary.
        assert client.get('/api/v1/organizations/1/companies/1/rag/capabilities').status_code == 401
