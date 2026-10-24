"""Read-only recommendation panel: real-history API only, no mock production notices."""
import shutil
import subprocess
from pathlib import Path
from app.api.dashboard import dashboard_html
ROOT=Path(__file__).resolve().parents[1]


def test_recommended_route_is_real_archived_company_workspace():
    html=dashboard_html()
    for needle in (
        'data-page="recommended"', 'id="vqRecommendations"',
        'id="vqRecommendationsResults"', 'id="vqRecommendedCount"',
        'id="vqRecommendedRuns"', 'id="vqRecommendedTopScore"',
        'id="vqRecommendationsRefresh"', 'id="vqRecommendedMinimum"',
        '/assets/recommendations.js', '/assets/recommendations.css',
        "up to three previous real Discovery runs",
        "Source URLs, buyers, budgets and restricted paid details",
    ):
        assert needle in html,needle
    assert html.count('id="vqRecommendations"')==1
    assert 'href="#recommended"' in html


def test_archived_history_only_and_no_sensitive_data_leak_from_cards():
    js=(ROOT/'app/api/static/recommendations.js').read_text(encoding="utf-8")
    for required in (
        "credentials:'same-origin'", "cache:'no-store'",
        "'/discovery/history'", "detail.organization_id!==scope.organizationId",
        "detail.company_id!==scope.companyId",
        "item?.preliminary_scoring?.fit_score",
        "r.total_failure===false", "score===null",
        "JSON.stringify([item.source,item.external_id])",
        "key(current())",
        "window.addEventListener('workspace-context'",
        "No new source call was made",
    ):
        assert required in js,required
    for prohibited in (
        "/discover/tenders", "/api/v1/public", "method:'POST'",
        "Math.random(", "innerHTML", "localStorage",
        "item.customer", "item.url", "item.initial_price", "item.currency",
    ):
        assert prohibited not in js
    assert "'#search-history'" in js
    node=shutil.which("node")
    if node:
        check=subprocess.run([node,"--check",str(ROOT/'app/api/static/recommendations.js')],
                             capture_output=True,text=True,timeout=10)
        assert check.returncode==0,check.stderr
