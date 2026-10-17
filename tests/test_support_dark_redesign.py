"""Supplemental dark conversation polish respects concurrent support landing design."""
from pathlib import Path
from app.api.dashboard import dashboard_html
from app.api.support_ui import SUPPORT_HTML

CSS=(Path(__file__).resolve().parents[1]/"app/api/static/support.css").read_text(encoding="utf-8")
TRANSLATIONS=(Path(__file__).resolve().parents[1]/"app/api/static/workspace_locale.js").read_text(encoding="utf-8")

def test_thread_dark_skin_no_broken_ticket_controls():
    page=dashboard_html()
    for expected in ("VALYQON SUPPORT CENTER","Provider-dependent",
                     'id="supportAssistantForm"','id="supportTicketForm"',
                     'id="supportRequests"','support-knowledge-links'):
        assert expected in page
    assert "/assets/support.css?v=thread-dark-20261017" in page
    assert "body.saas #supportCenter .support-thread-detail" in CSS
    assert "body.saas #supportCenter .support-thread-message.support" in CSS

def test_english_and_russian_copy_contract():
    for text in ("Support that stays with your workflow.",
                 "Requests awaiting a resolution", "Provider-dependent",
                 "No requests yet", "Scoring methodology ↗"):
        assert text in TRANSLATIONS
