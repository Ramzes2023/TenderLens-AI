"""Support visual refresh remains design-only; all existing sensitive flows intact."""
from app.api.dashboard import dashboard_html
from app.api.support_ui import SUPPORT_HTML
from pathlib import Path


def test_support_page_readable_dark_sections_and_live_ids():
    html=dashboard_html()
    styles=(Path(__file__).resolve().parents[1]/"app/api/static/support.css").read_text(encoding="utf-8")
    assert 'id="supportCenter"' in html
    assert 'id="supportAssistantForm"' in SUPPORT_HTML
    assert 'id="supportTicketForm"' in SUPPORT_HTML
    assert 'id="supportRequests"' in SUPPORT_HTML
    assert 'support-knowledge-links' in SUPPORT_HTML
    assert 'href="/scoring-methodology"' in SUPPORT_HTML
    assert 'Provider-dependent' in SUPPORT_HTML
    assert "body.saas .support-page .support-card" in styles
    assert "--support-panel:#162740" in styles
    assert "outline:3px solid #8fbfff" in styles
    assert "display:none!important" in styles


def test_support_summary_has_no_raw_none_placeholder():
    text=(Path(__file__).resolve().parents[1]/"app/api/static/support.js").read_text(encoding="utf-8")
    assert ': "No requests yet";' in text
    assert 'supportLatestTicket' in text
    assert "supportSubmit" in text
    assert "supportAssistantSubmit" in text
