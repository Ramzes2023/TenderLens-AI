"""Real account- and company-scoped deadline delivery journal acceptance."""
import asyncio
from contextlib import closing
from types import SimpleNamespace

import pytest

from app.auth import AuthRepository
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.organizations import OrganizationRepository
from app.launch.deadline_alerts import DeadlineAlerts
from app.api.dashboard import dashboard_html
import app.api.deadline_alert_routes as routes


def _environment(tmp_path):
    db=Database(DatabaseSettings("",tmp_path/"OFFLINE_FIXTURE-receipts.sqlite"))
    db.migrate()
    auth=AuthRepository(db)
    user=auth.create_account("journal-owner@example.test","test-only-hash")
    teammate=auth.create_account("journal-team@example.test","test-only-hash")
    outsider=auth.create_account("journal-outside@example.test","test-only-hash")
    org=OrganizationRepository(db).default_for_account(user.id)
    foreign=OrganizationRepository(db).default_for_account(outsider.id)
    with closing(db.connect()) as conn:
        with conn:
            conn.execute("INSERT INTO organization_members "
                         "(organization_id,account_id,role,created_at) "
                         "VALUES (?,?,?,?)",(org.id,teammate.id,"member","now"))
            for org_id,company,source,external in (
                (org.id,11,"eis","OFFLINE_FIXTURE-own"),
                (org.id,12,"eis","OFFLINE_FIXTURE-other-company"),
                (foreign.id,55,"eis","OFFLINE_FIXTURE-foreign")):
                conn.execute("INSERT INTO saved_opportunities "
                    "(organization_id,company_id,source,external_id,snapshot_json,"
                    "created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                    (org_id,company,source,external,"{}","now","now"))
            def receipt(who,orgid,company,external,channel,state):
                conn.execute("INSERT INTO deadline_alert_receipts "
                    "(account_id,organization_id,company_id,source,external_id,"
                    "deadline,lead_hours,channel,state,claimed_at,sent_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (who,orgid,company,"eis",external,"2026-10-26T12:00:00+03:00",48,
                     channel,state,"2026-10-24T11:12:13+00:00",
                     "2026-10-24T11:12:15+00:00" if state=="sent" else None))
            receipt(user.id,org.id,11,"OFFLINE_FIXTURE-own","email","sent")
            receipt(user.id,org.id,11,"OFFLINE_FIXTURE-own","telegram","failed")
            receipt(user.id,org.id,12,"OFFLINE_FIXTURE-other-company","email","pending")
            receipt(teammate.id,org.id,11,"OFFLINE_FIXTURE-own","email","pending")
            receipt(outsider.id,foreign.id,55,"OFFLINE_FIXTURE-foreign","email","sent")
    return db,user,teammate,outsider,org,foreign


def test_only_own_company_receipts_and_no_sensitive_upstream_identity(tmp_path):
    db,user,teammate,outsider,org,foreign=_environment(tmp_path)
    history=DeadlineAlerts(db)
    own=history.delivery_history(account_id=user.id,organization_id=org.id,company_id=11)
    assert own["scope"]=="my_recorded_deadline_delivery_attempts"
    assert own["delivery_confirmation"]=="sender_return_only"
    assert len(own["records"])==2
    assert {row["state"] for row in own["records"]}=={"sent","failed"}
    assert {row["channel"] for row in own["records"]}=={"email","telegram"}
    assert all(row["saved_id"] is not None for row in own["records"])
    assert all(row["lead_hours"]==48 for row in own["records"])
    assert "OFFLINE_FIXTURE" not in str(own)
    assert "eis" not in str(own)
    assert "journal-owner@example.test" not in str(own)
    assert "2026-10-26T12" not in str(own)
    assert history.delivery_history(account_id=user.id,organization_id=org.id,company_id=12)["records"][0]["state"]=="pending"
    assert len(history.delivery_history(account_id=teammate.id,organization_id=org.id,company_id=11)["records"])==1
    assert len(history.delivery_history(account_id=outsider.id,organization_id=foreign.id,company_id=55)["records"])==1
    with pytest.raises(PermissionError):
        history.delivery_history(account_id=outsider.id,organization_id=org.id,company_id=11)
    for invalid in (0,51,True,-1):
        with pytest.raises(ValueError):
            history.delivery_history(account_id=user.id,organization_id=org.id,company_id=11,limit=invalid)
    with closing(db.connect()) as conn:
        with conn:
            conn.execute("DELETE FROM saved_opportunities WHERE organization_id=? AND company_id=?",
                         (org.id,11))
    deleted=history.delivery_history(account_id=user.id,organization_id=org.id,company_id=11)
    assert len(deleted["records"])==2
    assert all(row["saved_id"] is None for row in deleted["records"])
    db.close()


def test_endpoint_read_only_uses_selected_company_and_private_cache(monkeypatch,tmp_path):
    db,user,teammate,outsider,org,foreign=_environment(tmp_path)
    current=[user]
    active_company=[11]
    async def account(request):return current[0]
    async def company(request,account,organization_id):
        return SimpleNamespace(id=active_company[0])
    monkeypatch.setattr(routes,"_account",account)
    monkeypatch.setattr(routes,"_active_company",company)
    request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=SimpleNamespace(database=db))))
    resp=asyncio.run(routes.get_deadline_delivery_history(org.id,request))
    assert resp.status_code==200 and resp.headers["cache-control"]=="private, no-store"
    import json
    payload=json.loads(resp.body)
    assert payload["company_id"]==11
    assert len(payload["records"])==2
    active_company[0]=12
    payload=json.loads(asyncio.run(routes.get_deadline_delivery_history(org.id,request)).body)
    assert payload["company_id"]==12 and len(payload["records"])==1
    current[0]=outsider
    active_company[0]=11
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as caught:
        asyncio.run(routes.get_deadline_delivery_history(org.id,request))
    assert caught.value.status_code==403
    db.close()


def test_real_dashboard_mounts_interactive_journal_without_fake_alerts():
    html=dashboard_html()
    for expected in (
        'id="vqDeliveryJournal"', 'data-page="notifications"',
        'id="vqDeliveryRefresh"', 'id="vqDeliveryStatus"',
        'id="vqDeliveryRows"', 'id="vqDeliveryCount"',
        '/assets/delivery_journal.js', '/assets/delivery_journal.css',
        '/assets/delivery_preferences.js', 'id="vqDeliveryEmailOptIn"',
        'id="vqDeliveryTelegramOptIn"', 'id="vqDeliverySavePrefs"',
        'not verify inbox delivery',
    ):
        assert expected in html,expected
    js=__import__("pathlib").Path("app/api/static/delivery_journal.js").read_text(encoding="utf-8")
    for required in (
        "credentials:'same-origin'", "my_recorded_deadline_delivery_attempts",
        "state.accountId", "state.activeCompanyId", "loadedKey",
        "valyqon-open-saved", "scope()", "records.length>50",
        "vqDeliveryRows", "window.addEventListener('workspace-context'",
    ):
        assert required in js, required
    prefs=__import__("pathlib").Path("app/api/static/delivery_preferences.js").read_text(encoding="utf-8")
    for required in (
        "method:'PUT'", "email_enabled:email.checked", "telegram_enabled:telegram.checked",
        "credentials:'same-origin'", "Number.isInteger(state.activeCompanyId)",
        "No message was sent.", "loadedKey", "shell-locale-change",
    ):
        assert required in prefs,required
    for forbidden in ("Math.random(", "innerHTML", "localStorage", "send_message(", "send_mail("):
        assert forbidden not in prefs
    for fake in ("Math.random(", "innerHTML", "demoMessages", "fakeNotification", "localStorage"):
        assert fake not in js
