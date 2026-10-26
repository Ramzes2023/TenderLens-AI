"""Bounded fair opt-in Worker scan: no first-page starvation, no duplicate sends.

All records use OFFLINE_FIXTURE identities in isolated SQLite, never external
mail/Telegram or live procurement feeds.
"""
from contextlib import closing
from datetime import timedelta
import json

from app.launch.deadline_alerts import (
    DeadlineAlerts, MAX_REMINDERS_PER_CYCLE, MAX_SCANNED_PER_CYCLE,
)
from datetime import datetime, timezone
from app.auth import AuthRepository
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.organizations import OrganizationRepository

NOW=datetime(2026,10,17,12,0,tzinfo=timezone.utc)


def _fixture(tmp_path):
    db=Database(DatabaseSettings("",tmp_path/"isolated-fair-reminders.sqlite"))
    db.migrate()
    user=AuthRepository(db).create_account("fair-worker@example.test","test-only-hash")
    org=OrganizationRepository(db).default_for_account(user.id)
    with closing(db.connect()) as conn:
        with conn:
            conn.execute("UPDATE auth_accounts SET email_verified=1 WHERE id=?",(user.id,))
            snapshot={
                "source":"eis", "external_id":"OFFLINE_FIXTURE_000",
                "title":"OFFLINE_FIXTURE initial past scan",
                "url":"https://zakupki.gov.ru/view/OFFLINE_FIXTURE_000",
                "deadline":"2026-10-19T10:00:00+00:00",
                "reasons":[], "metadata_analysis":{},
                "preliminary_scoring":{
                    "profile_name":"OFFLINE_FIXTURE", "profile_version":"1",
                    "fit_score":70, "scorable_weight":100,
                    "completeness_percent":80, "criteria":[],
                },
            }
            conn.execute(
                "INSERT INTO saved_opportunities"
                "(organization_id,company_id,source,external_id,snapshot_json,"
                "created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                (org.id,500,"eis",snapshot["external_id"],
                 json.dumps(snapshot), NOW.isoformat(),NOW.isoformat()))
    return db,user,org


def _seed(db, organization_id, *, noise, valid):
    """Keep official-looking identities clearly marked as offline fixture."""
    base={
        "source":"eis", "title":"OFFLINE_FIXTURE notice",
        "url":"https://zakupki.gov.ru/view/OFFLINE_FIXTURE",
        "reasons":[], "metadata_analysis":{},
        "preliminary_scoring":{
            "profile_name":"OFFLINE_FIXTURE", "profile_version":"1",
            "fit_score":70, "scorable_weight":100,
            "completeness_percent":80, "criteria":[],
        },
    }
    with closing(db.connect()) as conn:
        with conn:
            # Existing fixture includes exactly one valid notice. Disable its
            # deadline so only the later inserted genuine test row can send.
            snapshot=json.loads(conn.execute(
                "SELECT snapshot_json FROM saved_opportunities"
            ).fetchone()["snapshot_json"])
            snapshot["deadline"]="2026-10-19"
            conn.execute("UPDATE saved_opportunities SET snapshot_json=?",
                         (json.dumps(snapshot),))
            for index in range(noise+valid):
                notice=dict(base)
                notice["external_id"]=f"OFFLINE_FIXTURE_SCAN_{index:05d}"
                notice["title"]=f"OFFLINE_FIXTURE scan item {index}"
                notice["deadline"]="2026-10-19" if index<noise else "2026-10-19T10:00:00+00:00"
                conn.execute(
                    "INSERT INTO saved_opportunities"
                    "(organization_id,company_id,source,external_id,snapshot_json,"
                    "created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                    (organization_id,500,"eis",notice["external_id"],
                     json.dumps(notice),"2026-10-17T12:00:00+00:00",
                     "2026-10-17T12:00:00+00:00"),
                )


def test_saved_due_notice_after_first_hundred_is_not_starved(tmp_path):
    db,user,org=_fixture(tmp_path)
    try:
        alerts=DeadlineAlerts(db)
        _seed(db,org.id,noise=116,valid=1)
        alerts.set_preferences(account_id=user.id,organization_id=org.id,
                               company_id=500,email_enabled=True,telegram_enabled=False)
        recorded=[]
        result=alerts.run_once(send_email=lambda recipient,msg: recorded.append(msg),now=NOW)
        assert result=={"examined":118,"sent":1,"failed":0}
        assert len(recorded)==1 and "OFFLINE_FIXTURE_SCAN_00116" in recorded[0]
        assert alerts.last_scan["eligible_rows"]==118
        assert alerts.last_scan["scan_incomplete"] is False
        result=alerts.run_once(send_email=lambda recipient,msg: recorded.append(msg),now=NOW)
        assert result["sent"]==0 and len(recorded)==1
    finally:
        db.close()


def test_sender_budget_never_exceeds_100_and_remaining_send_next_cycle(tmp_path):
    db,user,org=_fixture(tmp_path)
    try:
        alerts=DeadlineAlerts(db)
        _seed(db,org.id,noise=0,valid=MAX_REMINDERS_PER_CYCLE+15)
        alerts.set_preferences(account_id=user.id,organization_id=org.id,
                               company_id=500,email_enabled=True,telegram_enabled=False)
        sent=[]
        first=alerts.run_once(send_email=lambda _,msg: sent.append(msg),now=NOW)
        assert first["sent"]==MAX_REMINDERS_PER_CYCLE
        assert alerts.last_scan["scan_incomplete"]
        assert alerts.last_scan["send_cap_reached"]
        second=alerts.run_once(send_email=lambda _,msg: sent.append(msg),now=NOW)
        assert second["sent"]==15
        third=alerts.run_once(send_email=lambda _,msg: sent.append(msg),now=NOW)
        assert third["sent"]==0
        assert len(sent)==115
        assert len(set(sent))==115
        with closing(db.connect()) as conn:
            receipt_count=conn.execute(
                "SELECT COUNT(*) FROM deadline_alert_receipts WHERE state='sent'"
            ).fetchone()[0]
        assert receipt_count==115
    finally:
        db.close()


def test_rotating_two_hour_windows_cover_more_than_scan_cap(tmp_path):
    db,user,org=_fixture(tmp_path)
    try:
        alerts=DeadlineAlerts(db)
        _seed(db,org.id,noise=MAX_SCANNED_PER_CYCLE+6,valid=1)
        alerts.set_preferences(account_id=user.id,organization_id=org.id,
                               company_id=500,email_enabled=True,telegram_enabled=False)
        sent=[]
        first=alerts.run_once(send_email=lambda _,msg: sent.append(msg),now=NOW)
        assert first["examined"]==MAX_SCANNED_PER_CYCLE
        assert alerts.last_scan["scan_incomplete"]
        second=alerts.run_once(send_email=lambda _,msg: sent.append(msg),
                               now=NOW+timedelta(hours=1))
        assert first["sent"]+second["sent"]==1
        assert len(sent)==1
        assert "OFFLINE_FIXTURE_SCAN_02006" in sent[0]
        assert alerts.last_scan["eligible_rows"]==MAX_SCANNED_PER_CYCLE+8
    finally:
        db.close()
