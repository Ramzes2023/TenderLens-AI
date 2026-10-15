"""Public branding must not invalidate existing configuration or browser identity."""
from unittest.mock import patch

from app.api.auth_pages import login_html, register_html
from app.api.dashboard import dashboard_html
from app.api.invitation_page import invitation_page_html
from app.api.config import load_api_settings
from app.api.security import SESSION_COOKIE


def test_branding_on_all_browser_entry_points():
    for html in (login_html(), register_html(), dashboard_html(), invitation_page_html('demo-only')):
        assert 'VALYQON AI' in html
        assert 'TenderLens AI' not in html
    assert 'Find. Analyze. Score. Win.' in login_html()
    assert 'Global Procurement Intelligence powered by AI' in dashboard_html()


def test_legacy_configuration_and_session_identity_remain_supported(tmp_path):
    with patch.dict('os.environ', {'TENDERLENS_API_KEY': 'synthetic-test-only',
                                   'TENDERLENS_TRUSTED_PROXY_IPS': '172.30.19.2'}, clear=True):
        settings = load_api_settings(tmp_path / 'missing.env')
    assert settings.api_key == 'synthetic-test-only'
    assert settings.forwarded_allow_ips == '172.30.19.2'
    assert SESSION_COOKIE == 'tenderlens_session'
