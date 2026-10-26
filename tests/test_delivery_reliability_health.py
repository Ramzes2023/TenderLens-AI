"""Real persisted sender-claim health: count all rows without auto-resending.

Only disposable SQLite OFFLINE_FIXTURE data. No email, Telegram or Worker send.
"""
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

from app.auth import AuthRepository
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.launch.deadline_alerts import DeadlineAlerts
from app.organizations import OrganizationRepository
from app.api.dashboard import dashboard_html


def test_scoped_pending_failure_health_and_no_side_effects(tmp_path):
    db=Database(DatabaseSettings("",tmp_path/"delivery-health-offline.sqlite"))
    db.migrate()
    auth=AuthRepository(db)
    user=auth.create_account("offline-health@example.test","fixture-hash")
    colleague=auth.create_account("offline-colleague@example.test","fixture-hash")
    outside=auth.create_account("offline-outside@example.test","fixture-hash")
    org=OrganizationRepository(db).default_for_account(user.id)
    foreign=OrganizationRepository(db).default_for_account(outside.id)
    now=datetime.now(timezone.utc)
    stale=(now-timedelta(hours=3)).isoformat(timespec="seconds")
    recent=(now-timedelta(seconds=15)).isoformat(timespec="seconds")
    with closing(db.connect()) as conn:
        with conn:
            conn.execute("INSERT INTO organization_members "
                         "(organization_id,account_id,role,created_at) "
                         "VALUES (?,?,?,?)",(org.id,colleague.id,"member",recent))
            def receipt(account,organization,company,external,state,channel,claimed):
                conn.execute("INSERT INTO deadline_alert_receipts "
                    "(account_id,organization_id,company_id,source,external_id,deadline,"
                    "lead_hours,channel,state,claimed_at,sent_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (account,organization,company,"eis",external,"2026-11-05T16:00:00+03:00",
                     48,channel,state,claimed,recent if state=="sent" else None))
            receipt(user.id,org.id,1,"OFFLINE_FIXTURE-sent","sent","email",recent)
            receipt(user.id,org.id,1,"OFFLINE_FIXTURE-failed","failed","telegram",recent)
            receipt(user.id,org.id,1,"OFFLINE_FIXTURE-old-pending","pending","email",stale)
            receipt(user.id,org.id,1,"OFFLINE_FIXTURE-fresh-pending","pending","telegram",recent)
            receipt(user.id,org.id,2,"OFFLINE_FIXTURE-other-company","pending","email",stale)
            receipt(colleague.id,org.id,1,"OFFLINE_FIXTURE-colleague","pending","email",stale)
            receipt(outside.id,foreign.id,3,"OFFLINE_FIXTURE-other-org","failed","email",recent)
        before=conn.execute("SELECT COUNT(*) FROM deadline_alert_receipts").fetchone()[0]

    service=DeadlineAlerts(db)
    report=service.delivery_history(account_id=user.id,organization_id=org.id,company_id=1,limit=2)
    health=report["health"]
    assert len(report["records"])==2  # Journal pagination must not hide history counts.
    assert health=={
        "total":4,"sender_ok":1,"failed":1,"pending":2,
        "potentially_stranded_pending":1,"stale_after_minutes":30,
        "scope":"my_all_recorded_attempts","automatic_retry_enabled":False,
    }
    assert health["total"]>len(report["records"])
    assert "OFFLINE_FIXTURE" not in str(report)
    assert service.delivery_history(account_id=user.id,organization_id=org.id,
                                    company_id=2)["health"]["potentially_stranded_pending"]==1
    assert service.delivery_history(account_id=colleague.id,organization_id=org.id,
                                    company_id=1)["health"]["pending"]==1
    with pytest.raises(PermissionError):
        service.delivery_history(account_id=outside.id,organization_id=org.id,company_id=1)
    with closing(db.connect()) as conn:
        after=conn.execute("SELECT COUNT(*) FROM deadline_alert_receipts").fetchone()[0]
        states=[r[0] for r in conn.execute(
            "SELECT state FROM deadline_alert_receipts WHERE account_id=?",
            (user.id,)).fetchall()]
    assert before==after
    assert states.count("pending")==3 and states.count("failed")==1
    db.close()


def test_authenticated_notifications_show_real_health_without_retry_buttons():
    html=dashboard_html()
    for value in ("vqDeliveryReliability","vqDeliveryReliabilityStatus",
                  "vqDeliveryAllFailed","vqDeliveryOldPending",
                  "No automatic retries occur"):
        assert value in html
    from pathlib import Path
    script=Path("app/api/static/delivery_journal.js").read_text(encoding="utf-8")
    for value in ("my_all_recorded_attempts","potentially_stranded_pending",
                  "stale_after_minutes!==30","automatic_retry_enabled!==false",
                  "cache={records:data.records,health:health||null}",
                  "vqDeliveryReliabilityStatus"):
        assert value in script
    for unsafe in ("retrySend(", "retryDeadline(", "method:'POST'",
                   "method:'PATCH'", "method:'PUT'", "fakeDelivery"):
        assert unsafe not in script
