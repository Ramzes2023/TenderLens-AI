"""Team decision desk must render actual protected API interactions, never client-side fake approvals."""
from pathlib import Path
import shutil
import subprocess
from app.api.dashboard import dashboard_html

ROOT=Path(__file__).resolve().parents[1]


def test_team_panel_is_in_real_saved_detail_and_assets_loaded():
    html=dashboard_html()
    for token in (
        'id="savedTenderTeamPanel"', 'id="savedTenderAssignee"',
        'id="saveTenderAssignee"', 'id="requestTenderApproval"',
        'id="approveTenderParticipation"', 'id="rejectTenderParticipation"',
        'id="withdrawTenderApproval"', 'id="savedTenderTeamEvents"',
        '/assets/tender_team.js', '/assets/tender_team.css',
        'Internal approval does not submit a bid',
    ):
        assert token in html,token
    assert html.index('/assets/tender_team.js')>html.index('/assets/saved.js')


def test_only_real_team_endpoints_and_no_unverified_approval():
    js=(ROOT/'app/api/static/tender_team.js').read_text(encoding="utf-8")
    for token in (
        "'valyqon-saved-detail-open'", "event.detail",
        "expected_revision:revision", "credentials:'same-origin'",
        "data.requested_by_account_id!==currentId",
        "data.your_role", "state.activeCompanyId",
        "method:'PATCH'", "reload(epoch,scope)",
        "item.organizationId!==state.organizationId" if False else "selection.organizationId===state.organizationId",
        "'/events'", "state.accountId",
    ):
        assert token in js,token
    for bad in ("localStorage", "Math.random(", "fakeAccount", "token_urlsafe",
                "innerHTML", "document.cookie"):
        assert bad not in js


def test_team_js_syntax_if_node_exists():
    node=shutil.which('node')
    if node:
        for name in ("tender_team.js","saved.js"):
            p=ROOT/"app/api/static"/name
            check=subprocess.run([node,"--check",str(p)],
                                 capture_output=True,text=True,timeout=15)
            assert check.returncode==0,check.stderr


def test_buyer_insights_are_authenticated_saved_only():
    html=dashboard_html()
    assert 'id="vqPlannerBuyersTab"' in html
    assert 'id="vqPlannerBuyers"' in html
    assert 'id="vqBuyerChart"' in html
    js=(ROOT/'app/api/static/planner.js').read_text(encoding="utf-8")
    assert "records.slice(0,MAX_ITEMS)" in js
    assert "record.opportunity?.customer" in js
    assert "view==='buyers'" in js
    assert "seen.set(key,(seen.get(key)||0)+1)" in js
    assert "infer competitors or winners" in html
