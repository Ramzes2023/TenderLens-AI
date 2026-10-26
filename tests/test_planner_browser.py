"""Real Chromium UI regression with explicit OFFLINE_FIXTURE API responses.

No source access, user credentials, or existing database. Playwright is optional
for the default Python suite; the browser acceptance job must install it.
"""
import json
from datetime import date
from pathlib import Path

import pytest


def test_calendar_opens_exact_saved_record_and_scope(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    from app.api.planner_ui import PLANNER_HTML
    source = Path("app/api/static/planner.js").read_text(encoding="utf-8")
    html = PLANNER_HTML.replace(' hidden aria-labelledby=', ' aria-labelledby=')
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route("**/*", lambda route: route.fulfill(
                content_type="text/html", body=html))
            page.goto("http://offline-fixture.test/#tender-planner")
            page.evaluate("""() => {
                window.state = {organizationId:17, activeCompanyId:29};
                window.usingSharedOrganization = () => true;
                window.canWriteWorkspace = () => true;
                window.openedSaved = [];
                window.addEventListener('valyqon-open-saved', e => openedSaved.push(e.detail));
            }""")
            rows = [{"id": number, "opportunity": {
                "title": f"OFFLINE_FIXTURE tender {number}", "deadline": date.today().isoformat()
            }} for number in (41, 42)]
            rows[0]['opportunity']['deadline'] += 'T22:30:00+03:00'
            page.route("**/api/v1/organizations/17/shortlist", lambda route: route.fulfill(
                content_type="application/json", body=json.dumps(rows)))
            page.route("**/workflow", lambda route: route.fulfill(
                content_type="application/json", body='{"stage":"new","revision":0,"note":""}'))
            page.add_script_tag(content=source)
            page.wait_for_selector('.vq-planner-card[data-saved-id="42"]')
            with page.expect_download() as exported:
                page.click('#vqPlannerCalendarExport')
            destination = tmp_path / 'deadlines.ics'
            exported.value.save_as(destination)
            calendar = destination.read_bytes()
            assert calendar.startswith(b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\n')
            assert calendar.count(b'BEGIN:VEVENT') == 2
            assert b'DTSTART;VALUE=DATE:' + date.today().strftime('%Y%m%d').encode() in calendar
            assert b'DTSTART:' + date.today().strftime('%Y%m%d').encode() + b'T193000Z' in calendar
            assert all(len(line) <= 75 for line in calendar.split(b'\r\n'))
            assert b'UID:42-17@valyqon.local' in calendar
            page.click("#vqPlannerMonthTab")
            page.get_by_role("link", name="OFFLINE_FIXTURE tender 42", exact=True).click()
            assert page.evaluate("openedSaved") == [
                {"id": 42, "organizationId": 17, "companyId": 29}]
            assert page.evaluate("location.hash") == "#saved"
            assert errors == []
        finally:
            browser.close()
