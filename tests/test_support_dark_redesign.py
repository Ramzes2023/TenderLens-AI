"""Contrast-safe support cockpit redesign without changes to its API contract."""
from app.api.dashboard import dashboard_html
from app.api.support_ui import SUPPORT_HTML
from pathlib import Path

CSS=(Path(__file__).resolve().parents[1]/"app/api/static/support.css").read_text(encoding="utf-8")
JS=(Path(__file__).resolve().parents[1]/"app/api/static/support.js").read_text(encoding="utf-8")


def test_customer_support_keeps_ticket_and_assistant_controls():
    for field in ("supportCenter","supportChat","supportAssistantForm","supportTicketForm",
                  "supportFirstName","supportEmail","supportSubject","supportDescription",
                  "supportPriority","supportRequests","supportOpenCount","supportLatestTicket",
                  "supportRequestCard","supportRefresh","supportCreateRequest"):
        assert f'id="{field}"' in SUPPORT_HTML
    assert "Scoring methodology" in SUPPORT_HTML
    assert "No requests yet" in JS
    assert "Product guide" in SUPPORT_HTML


def test_support_dark_style_scoped_and_mobile_compatible():
    assert "#supportCenter .support-hero" in CSS
    assert "#supportCenter .support-chat" in CSS
    assert "#supportCenter .support-summary" in CSS
    assert "#supportCenter .support-ticket-body" in CSS
    assert "@media(max-width:680px)" in CSS
    assert "prefers-reduced-motion" in CSS
    assert "/assets/support.css?v=dark-20261017" in dashboard_html()
