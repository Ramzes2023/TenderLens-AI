"""Public routes and explicit bindings, without application secrets or real accounts."""
import os
from html.parser import HTMLParser
from unittest.mock import patch
import pytest

with patch.dict(os.environ, {'PYTHON_DOTENV_DISABLED': '1'}, clear=True):
    from app.api.landing import landing_html
    from app.api.public_help import help_html, GUIDE
    from app.api.public_locale import COPY
    from app.api.auth_pages import login_html, register_html, verify_email_html, forgot_password_html, reset_password_html
    from app.api.main import create_app
    from app.api.runtime import ApiRuntime
    from app.api.config import ApiSettings
from fastapi.testclient import TestClient


@pytest.mark.parametrize('render', [landing_html, login_html, register_html, verify_email_html, forgot_password_html, reset_password_html, lambda: help_html('guide'), lambda: help_html('guidelines')])
def test_public_pages_share_explicit_locale_bindings(render):
    html = render()
    assert 'id="public-dictionary"' in html
    assert '/assets/public_locale.js' in html
    assert 'data-public-locale="en"' in html and 'data-public-locale="ru"' in html
    assert 'aria-hidden="true"' in html
    assert '/how-it-works' in html and '/usage-guidelines' in html
    assert '<meta name="description"' in html


@pytest.mark.parametrize('path', ['/how-it-works', '/usage-guidelines', '/assets/public_locale.js', '/assets/public.css'])
def test_real_public_routes_are_reachable_without_auth(path):
    app = create_app(runtime=ApiRuntime(), settings=ApiSettings(host='127.0.0.1', port=8000, reload=False, api_key=None))
    with TestClient(app) as client:
        response = client.get(path)
        assert response.status_code == 200
        if not path.startswith('/assets/'):
            assert response.headers['cache-control'] == 'no-store'


def test_guide_has_full_translations_and_honest_feature_boundaries():
    for heading, badge, text, _, label in GUIDE:
        for value in (heading, badge, text, label):
            assert COPY[value] != value
            assert any('а' <= character.lower() <= 'я' for character in COPY[value])
            assert '???' not in COPY[value]
    html = help_html('guide')
    assert 'not the probability of winning' in html
    assert 'Requires configuration' in html
    assert 'Mailpit is not a public inbox' in html
    assert 'read-only' in html
    assert 'not contractual Terms of Service' in help_html('guidelines')
    assert 'Billing is not enabled' in landing_html()


def test_auth_security_requests_and_generic_messages_remain():
    html = register_html()
    assert "'/api/v1/auth/register'" in html
    assert "credentials:'same-origin'" in html
    assert "data.detail==='Email verification required.'" in login_html()
    assert 'If an eligible account exists for this email' in forgot_password_html()
    assert 'history.replaceState' in reset_password_html()
