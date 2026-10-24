"""Chromium interaction acceptance using explicitly synthetic *history API* fixtures.

This is UI-level evidence, not source-to-worker or live Discovery proof.
"""
import json
from pathlib import Path
import pytest


def test_recommendation_scores_scoped_deduped_and_non_disclosing_in_chromium():
    playwright=pytest.importorskip("playwright.sync_api")
    from app.api.recommendations_ui import RECOMMENDATIONS_HTML

    current_company=[12]
    def item(identity,score,buyer):
        return dict(source="eis",external_id=identity,title="OFFLINE_FIXTURE tender "+identity,
            preliminary_scoring=dict(fit_score=score,completeness_percent=81.0),
            customer=buyer,initial_price=8745123,currency="RUB",
            url="https://example.invalid/restricted/notice")
    def summary(id,count):
        return dict(id=id,organization_id=7,company_id=12,total_failure=False,
            result_count=count,created_at="2026-10-24T10:00:00+00:00")
    runs=[summary(43,2),summary(41,2)]
    payloads={
        43:dict(id=43,organization_id=7,company_id=12,
                discovery=dict(total_failure=False,items=[
                    item("001",86,"PRIVATE-HIDDEN-BUYER"),
                    item("002",62,"PRIVATE-BUYER-2")])),
        41:dict(id=41,organization_id=7,company_id=12,
                discovery=dict(total_failure=False,items=[
                    item("001",95,"PRIVATE-BUYER-OLD"),
                    item("003",49,"PRIVATE-BUYER-3")]))
    }
    with playwright.sync_playwright() as p:
        browser=p.chromium.launch()
        try:
            page=browser.new_page()
            errors=[]
            calls=[]
            page.on("pageerror",lambda err:errors.append(str(err)))
            def route(r):
                request=r.request
                address=request.url.split("#")[0]
                if address.startswith("http://testserver/recommended"):
                    html='<html lang="en"><body>'+RECOMMENDATIONS_HTML.replace(
                        ' hidden aria-labelledby=', ' aria-labelledby=')+'</body></html>'
                    r.fulfill(content_type="text/html",body=html)
                elif "/api/v1/organizations/7/discovery/history" in address:
                    calls.append(address)
                    data=[]
                    if current_company[0]==12:
                        if address.endswith("/43"):data=payloads[43]
                        elif address.endswith("/41"):data=payloads[41]
                        else:data=runs
                    r.fulfill(status=200,content_type="application/json",
                              body=json.dumps(data))
                else:
                    r.abort()
            page.route("**/*",route)
            page.goto("http://testserver/recommended#recommended")
            page.evaluate("""() => {
                window.state={organizationId:7,activeCompanyId:12,uiEpoch:1};
                window.usingSharedOrganization=()=>true;
            }""")
            page.add_script_tag(content=Path("app/api/static/recommendations.js").read_text(encoding="utf-8"))
            page.wait_for_function("document.getElementById('vqRecommendedCount').textContent==='3'")
            assert page.locator("#vqRecommendedRuns").inner_text()=="2"
            assert page.locator("#vqRecommendedTopScore").inner_text()=="95%"
            assert page.locator(".vq-recommend-card").count()==3
            assert page.locator(".vq-recommend-card").first.locator(".vq-recommend-score").inner_text()=="95%"
            body=page.locator("body").inner_text()
            for private in ("PRIVATE-HIDDEN-BUYER","PRIVATE-BUYER-OLD",
                            "8745123","example.invalid/restricted"):
                assert private not in body
            assert all("/discovery/history" in url for url in calls)
            page.select_option("#vqRecommendedMinimum","70")
            assert page.locator(".vq-recommend-card").count()==1
            page.select_option("#vqRecommendedMinimum","0")
            page.click("#vqRecommendationsRefresh")
            page.wait_for_function("document.getElementById('vqRecommendedCount').textContent==='3'")

            current_company[0]=55
            page.evaluate("""() => {
                window.state.activeCompanyId=55;
                window.state.uiEpoch=2;
                window.dispatchEvent(new Event('workspace-context'));
            }""")
            page.wait_for_function("document.getElementById('vqRecommendedCount').textContent==='0'")
            assert page.locator(".vq-recommend-card").count()==0
            assert page.locator("body").inner_text().find("OFFLINE_FIXTURE tender")==-1
            assert errors==[]
        finally:
            browser.close()
