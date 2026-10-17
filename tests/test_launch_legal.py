import pytest
from fastapi import HTTPException
from app.api import legal_routes

def test_legal_publication_defaults_closed(monkeypatch):
    monkeypatch.delenv("VALYQON_LEGAL_APPROVED", raising=False)
    assert not legal_routes.legal_ready()
    with pytest.raises(HTTPException) as error:
        legal_routes.legal_page("offer")
    assert error.value.status_code == 503

def test_legal_four_distinct_pages_and_escaped_operator(monkeypatch):
    for setting in legal_routes.REQUIRED_SETTINGS:
        monkeypatch.setenv(setting, "Company & Partners")
    monkeypatch.setenv("VALYQON_LEGAL_APPROVED", "true")
    original_revision = legal_routes.legal_version()
    monkeypatch.setenv("VALYQON_LEGAL_ENTITY", "Other & Company")
    assert original_revision != legal_routes.legal_version()
    monkeypatch.setenv("VALYQON_LEGAL_ENTITY", "Company & Partners")
    for name in ("offer", "privacy", "personal-data", "marketing"):
        html = legal_routes.legal_page(name)
        assert html.status_code == 200
        assert b"Company &amp; Partners" in html.body
        assert legal_routes.VERSION.encode() in html.body
