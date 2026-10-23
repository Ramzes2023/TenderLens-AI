"""Tender Planner competitor-gap feature acceptance: real saved + stage API.

Reject fake notice injection, silently coercing timezone-naive timestamps,
unauthorized updates and any implication that an internal workflow is a bid.
"""
import shutil
import subprocess
from pathlib import Path

from app.api.dashboard import dashboard_html
from app.api.saas_shell import PAGES

ROOT = Path(__file__).resolve().parents[1]


def test_planner_visible_in_authenticated_navigation_with_real_controls():
    html = dashboard_html()
    assert "Tender Planner" in PAGES
    for needle in (
        'href="#tender-planner"', 'data-nav="tender-planner"',
        'id="plannerWorkspace"', 'data-page="tender-planner"',
        'id="vqPlannerBoard"', 'id="vqPlannerCalendar"',
        'id="vqPlannerCalendarExport"', 'id="vqPlannerMore"',
        'id="vqPlannerMonthTab"', 'id="vqPlannerRefresh"',
        'id="vqPlannerQuery"', 'id="vqPlannerStatus"',
        'id="vqPlannerSoon"', 'id="vqPlannerLate"',
        '/assets/planner.css', '/assets/planner.js',
        'Always verify deadlines', 'not evidence',
    ):
        assert needle in html, needle
    assert html.count('id="plannerWorkspace"') == 1
    assert html.index('/assets/planner.css') < html.index('/assets/responsive.css')


def test_planner_only_reads_role_scoped_saved_and_workflow_endpoints():
    js = (ROOT / 'app/api/static/planner.js').read_text(encoding='utf-8')
    for token in (
        "usingSharedOrganization()", "canWriteWorkspace()",
        "Number.isInteger(state.organizationId)",
        "Number.isInteger(state.activeCompanyId)",
        "'/shortlist'", "'/workflow'",
        "method:'PATCH'", "expected_revision:previous.revision",
        "note:previous.note", "credentials:'same-origin'",
        "Array.from({length:Math.min(4,items.length)}",
        "ticket!==epoch", "scope()",
        "response.status===401", "state.organizationId",
        "loadError", "record.workflowError",
        "PAGE_SIZE=30,MAX_ITEMS=300",
        "records.slice(0,MAX_ITEMS)",
        "window.addEventListener('workspace-context'",
    ):
        assert token in js, token
    for forbidden in (
        "Math.random(", "fakeTender", "demoTender", "/api/v1/public/opportunities",
        "XMLHttpRequest", "innerHTML", "fetch('/api/v1/public",
        "'/submit-bid'", "'/award'", "stage:'won'",
    ):
        assert forbidden not in js
    assert "not evidence" in (ROOT/'app/api/planner_ui.py').read_text(encoding='utf-8')


def test_timezones_and_calendar_export_are_explicit():
    js=(ROOT/'app/api/static/planner.js').read_text(encoding='utf-8')
    for term in (
        "kind:'date'", "kind:'instant'",
        "date.kind==='date'", "new Date(value+'T12:00:00')",
        "value.trim()", "new Blob(",
        "'text/calendar;charset=utf-8'", "'BEGIN:VCALENDAR'",
        "'VERSION:2.0'", "'DTSTART;VALUE=DATE:'",
        "'DTSTART:'", "URL.revokeObjectURL(url)", "icsEscape",
        "deadlineInfo(date)", "time not provided",
        "Date-only notices have no verified",
    ):
        assert term in (js + (ROOT/'app/api/planner_ui.py').read_text(encoding='utf-8')),term


def test_planner_javascript_is_valid_when_node_available():
    node=shutil.which('node')
    if not node:
        return
    path=ROOT/'app/api/static/planner.js'
    p=subprocess.run([node,'--check',str(path)],capture_output=True,text=True,timeout=15)
    assert p.returncode==0,p.stderr


def test_existing_workflow_roles_and_conflict_detection_not_changed():
    from app.workspaces.lifecycle import WRITE_ROLES, STAGES
    assert {'owner','admin','member'} == WRITE_ROLES
    assert {'new','reviewing','preparing','submitted','won','lost','archived'} == STAGES
    from app.api.shortlist_workflow_routes import router
    paths=[r.path for r in router.routes]
    assert any('/{saved_id}/workflow' in p for p in paths)
    assert any('/{saved_id}/workflow/events' in p for p in paths)
