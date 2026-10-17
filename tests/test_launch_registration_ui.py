from app.api.auth_pages import register_html
from app.api.legal_routes import REQUIRED_SETTINGS

def test_registration_displays_three_separate_consents_when_approved(monkeypatch):
    for key in REQUIRED_SETTINGS:
        monkeypatch.setenv(key, "approved")
    monkeypatch.setenv("VALYQON_LEGAL_APPROVED", "true")
    page = register_html()
    assert 'id="acceptOffer" required' in page
    assert 'id="acceptPersonal" required' in page
    assert 'id="acceptMarketing"' in page
    assert 'id="acceptMarketing" required' not in page
    assert '/legal/privacy' in page
    assert 'marketing_consent:' in page

def test_commercial_registration_disabled_when_documents_pending(monkeypatch):
    monkeypatch.setenv("VALYQON_LEGAL_REQUIRED", "true")
    monkeypatch.delenv("VALYQON_LEGAL_APPROVED", raising=False)
    page = register_html()
    assert "Commercial legal documents are awaiting publication" in page
    assert 'id="submit" type="submit" disabled' in page
