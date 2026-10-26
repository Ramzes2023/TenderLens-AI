"""Real Chromium -> authenticated ASGI receipt endpoint -> disposable SQLite.

The two receipt records are OFFLINE_FIXTURE, NOT evidence of external SMTP
or Telegram delivery. The UI receives actual server responses, not mocked JSON.
"""
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit
import pytest


def test_delivery_journal_chromium_real_api_refresh_and_outsider_denial():
    playwright=pytest.importorskip("playwright.sync_api")
    from scripts import phase24_v6_customer_browser_acceptance as factory
    from app.api.notifications_ui import DELIVERY_JOURNAL_HTML
    from app.api.security import SESSION_COOKIE
    from app.database.backend import Database
    from app.database.config import DatabaseSettings

    with factory.isolated_customer() as customer, playwright.sync_playwright() as p:
        db=Database(DatabaseSettings("",customer.path))
        db.migrate()
        customer.client.app.state.runtime.database=db
        try:
            factory.login(customer,customer.owner)
            company=factory.create_company(customer)
            org=customer.organization.id
            with closing(db.connect()) as conn,conn:
                conn.execute(
                    "INSERT INTO saved_opportunities "
                    "(organization_id,company_id,source,external_id,snapshot_json,created_at,updated_at)"
                    "VALUES (?,?,?,?,?,?,?)",
                    (org,company["id"],"eis","OFFLINE_FIXTURE-notify",
                     "{}","now","now"))
                saved=conn.execute(
                    "SELECT id FROM saved_opportunities WHERE organization_id=?",
                    (org,)).fetchone()[0]
                for channel,status in [("email","sent"),("telegram","failed")]:
                    conn.execute(
                        "INSERT INTO deadline_alert_receipts "
                        "(account_id,organization_id,company_id,source,external_id,"
                        "deadline,lead_hours,channel,state,claimed_at,sent_at)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (customer.owner.id,org,company["id"],"eis",
                         "OFFLINE_FIXTURE-notify","2026-10-26T12:00:00+03:00",
                         48,channel,status,"2026-10-24T12:00:00+00:00",
                         "2026-10-24T12:00:01+00:00" if status=="sent" else None))
            browser=p.chromium.launch()
            try:
                context=browser.new_context()
                page=context.new_page()
                errors=[]
                page.on("pageerror",lambda error:errors.append(str(error)))

                def transport(route):
                    req=route.request
                    if req.url.startswith("http://testserver/fixture"):
                        markup=DELIVERY_JOURNAL_HTML.replace(
                            ' hidden aria-labelledby=', ' aria-labelledby=')
                        route.fulfill(content_type="text/html",
                            body='<!doctype html><html lang="en"><body>'+markup+'</body></html>')
                        return
                    if urlsplit(req.url).netloc!="testserver":
                        route.abort()
                        return
                    customer.client.cookies.clear()
                    response=customer.client.request(req.method,req.url,
                        headers=req.headers,content=req.post_data_buffer,
                        follow_redirects=False)
                    route.fulfill(status=response.status_code,
                        content_type="application/json",body=response.content)

                page.route("**/*",transport)

                def open_as(account):
                    factory.login(customer,account)
                    context.clear_cookies()
                    context.add_cookies([dict(name=SESSION_COOKIE,
                        value=customer.client.cookies.get(SESSION_COOKIE),
                        url="http://testserver")])
                    page.goto("http://testserver/fixture#notifications")
                    page.evaluate("(v)=>{window.state=v;window.opened=[];window.addEventListener('valyqon-open-saved',e=>window.opened.push(e.detail));}",
                        dict(accountId=account.id,organizationId=org,
                             activeCompanyId=company["id"]))
                    page.add_script_tag(content=Path(
                        "app/api/static/delivery_journal.js").read_text(encoding="utf-8"))
                    page.add_script_tag(content=Path(
                        "app/api/static/delivery_preferences.js").read_text(encoding="utf-8"))

                open_as(customer.owner)
                page.wait_for_function("document.getElementById('vqDeliveryCount').textContent==='2'")
                page.wait_for_function("!document.getElementById('vqDeliveryEmailOptIn').disabled")
                assert not page.locator("#vqDeliveryEmailOptIn").is_checked()
                assert not page.locator("#vqDeliveryTelegramOptIn").is_checked()
                page.check("#vqDeliveryEmailOptIn")
                page.click("#vqDeliverySavePrefs")
                page.wait_for_function(
                    "document.getElementById('vqDeliveryPrefsStatus').textContent.includes('saved')")
                with closing(db.connect()) as conn:
                    preference=conn.execute(
                        "SELECT email_enabled,telegram_enabled FROM deadline_alert_preferences "
                        "WHERE account_id=? AND organization_id=? AND company_id=?",
                        (customer.owner.id,org,company["id"])).fetchone()
                    assert tuple(preference)==(1,0)
                assert page.locator("#vqDeliverySent").inner_text()=="1"
                assert page.locator("#vqDeliveryFailed").inner_text()=="1"
                # Same company/account: the full-history reliability view must
                # show the failed SMTP/Telegram sender record, not fake inbox
                # delivery or a retry control.
                assert page.locator("#vqDeliveryAllFailed").inner_text()=="1"
                assert page.locator("#vqDeliveryOldPending").inner_text()=="0"
                assert "needs-review" in page.locator(
                    "#vqDeliveryReliabilityStatus").get_attribute("class")
                assert page.locator(".vq-delivery-row").count()==2
                assert page.locator("body").inner_text().find("OFFLINE_FIXTURE-notify")==-1
                page.click("#vqDeliveryRefresh")
                page.wait_for_function("document.getElementById('vqDeliveryCount').textContent==='2'")
                page.locator(".vq-delivery-row-meta a").first.click()
                opened=page.evaluate("window.opened")
                assert opened==[dict(id=saved,organizationId=org,companyId=company["id"])]

                open_as(customer.outsider)
                page.wait_for_function(
                    "document.getElementById('vqDeliveryStatus').textContent.includes('unavailable')")
                assert page.locator("#vqDeliveryCount").inner_text()=="—"
                assert page.locator("#vqDeliveryAllFailed").inner_text()=="—"
                assert page.locator("#vqDeliveryOldPending").inner_text()=="—"
                assert page.locator("#vqDeliverySavePrefs").is_disabled()
                assert page.locator(".vq-delivery-row").count()==0
                assert errors==[]
            finally:
                browser.close()
        finally:
            db.close()
