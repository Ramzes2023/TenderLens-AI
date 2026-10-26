"""Real SQLite tenant/worker reminder acceptance; never touches external delivery."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from app.auth import AuthRepository
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.launch.deadline_alerts import DeadlineAlerts
from app.organizations import OrganizationRepository

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)


def _fixture(tmp_path):
    db = Database(DatabaseSettings("", tmp_path / "isolated.db"))
    db.migrate()
    auth = AuthRepository(db)
    user = auth.create_account("test-reminder@example.test", "fake-test-hash")
    org = OrganizationRepository(db).default_for_account(user.id)
    with closing(db.connect()) as conn:
        with conn:
            conn.execute("UPDATE auth_accounts SET email_verified=1 WHERE id=?", (user.id,))
            conn.execute(
                "INSERT INTO saved_opportunities "
                "(organization_id,company_id,source,external_id,snapshot_json,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (org.id, 500, "eis", "fixture-1",
                 '{"source":"eis","external_id":"fixture-1","title":"Test procurement",'
                 '"url":"https://zakupki.gov.ru/view/fixture-1",'
                 '"deadline":"2026-10-19T10:00:00+00:00","reasons":[],"metadata_analysis":{},"preliminary_scoring":{"profile_name":"Test company","profile_version":"1","fit_score":82.0,"scorable_weight":100,"completeness_percent":80,"criteria":[]}}',
                 NOW.isoformat(), NOW.isoformat()),
            )
    return db, user, org


def test_opt_in_idempotent_email_and_cannot_use_wrong_org(tmp_path):
    db, user, org = _fixture(tmp_path)
    alerts = DeadlineAlerts(db)
    assert alerts.preferences(account_id=user.id, organization_id=org.id,
                              company_id=500) == {"email_enabled": False, "telegram_enabled": False}
    deliveries = []
    assert alerts.run_once(send_email=lambda to, msg: deliveries.append((to,msg)),
                           now=NOW)["sent"] == 0
    try:
        alerts.set_preferences(account_id=user.id, organization_id=org.id+999,
                               company_id=500, email_enabled=True, telegram_enabled=False)
    except PermissionError:
        pass
    else:
        raise AssertionError("Non-member organization preferences were accepted")
    alerts.set_preferences(account_id=user.id, organization_id=org.id,
                           company_id=500, email_enabled=True, telegram_enabled=False)
    first = alerts.run_once(send_email=lambda to,msg: deliveries.append((to,msg)),now=NOW)
    second = alerts.run_once(send_email=lambda to,msg: deliveries.append((to,msg)),now=NOW)
    assert first == {"examined": 1, "sent": 1, "failed": 0}
    assert second["sent"] == 0
    assert len(deliveries) == 1
    assert "fixture-1" in deliveries[0][1]
    with closing(db.connect()) as conn:
        row = conn.execute("SELECT state FROM deadline_alert_receipts").fetchone()
    assert row["state"] == "sent"
    db.close()


def test_explicit_moscow_time_saved_notice_triggers_once(tmp_path):
    db, user, org = _fixture(tmp_path)
    alerts = DeadlineAlerts(db)
    alerts.set_preferences(
        account_id=user.id, organization_id=org.id, company_id=500,
        email_enabled=True, telegram_enabled=False,
    )
    with closing(db.connect()) as conn:
        with conn:
            old = conn.execute(
                "SELECT snapshot_json FROM saved_opportunities"
            ).fetchone()["snapshot_json"]
            conn.execute(
                "UPDATE saved_opportunities SET snapshot_json=?",
                (old.replace("2026-10-19T10:00:00+00:00", "19.10.2026 14:00 МСК"),),
            )
    sent = []
    result = alerts.run_once(
        send_email=lambda address, message: sent.append(message), now=NOW,
    )
    assert result["sent"] == 1
    assert "19.10.2026 14:00 МСК" in sent[0]
    assert alerts.run_once(send_email=lambda *_: None, now=NOW)["sent"] == 0
    db.close()


def test_unknown_timezone_is_not_sent(tmp_path):
    db,user,org = _fixture(tmp_path)
    alerts=DeadlineAlerts(db)
    alerts.set_preferences(account_id=user.id, organization_id=org.id,
                           company_id=500, email_enabled=True, telegram_enabled=False)
    with closing(db.connect()) as conn:
        with conn:
            conn.execute("UPDATE saved_opportunities SET snapshot_json=?",
                         ('{"source":"eis","external_id":"fixture-1","title":"No timezone",'
                          '"url":"https://zakupki.gov.ru/view/fixture-1",'
                          '"deadline":"2026-10-19","reasons":[],"metadata_analysis":{},"preliminary_scoring":{"profile_name":"Test company","profile_version":"1","fit_score":82.0,"scorable_weight":100,"completeness_percent":80,"criteria":[]}}',))
    assert alerts.run_once(send_email=lambda *_: (_ for _ in ()).throw(
        AssertionError("Cannot send ambiguous deadline")),now=NOW)["sent"] == 0
    db.close()



@pytest.mark.parametrize("revocation", [
    "disable_email", "remove_membership", "deactivate_account",
    "revoke_verification", "change_destination", "delete_saved_notice",
])
def test_stale_candidate_cannot_send_after_consent_or_access_revoked(tmp_path, monkeypatch, revocation):
    """Candidate selection may precede opt-out or access removal.

    A stale in-memory row must NOT produce a new receipt or outbound send.
    Only an isolated SQLite test account and a fake sender are involved.
    """
    db, user, org = _fixture(tmp_path)
    alerts = DeadlineAlerts(db)
    alerts.set_preferences(account_id=user.id, organization_id=org.id,
                           company_id=500, email_enabled=True, telegram_enabled=False)
    candidate = alerts.candidates()[0]
    if revocation == "disable_email":
        alerts.set_preferences(account_id=user.id, organization_id=org.id,
                               company_id=500, email_enabled=False, telegram_enabled=False)
    else:
        with closing(db.connect()) as conn:
            with conn:
                if revocation == "remove_membership":
                    conn.execute("DELETE FROM organization_members WHERE organization_id=? "
                                 "AND account_id=?", (org.id,user.id))
                elif revocation == "deactivate_account":
                    conn.execute("UPDATE auth_accounts SET is_active=0 WHERE id=?", (user.id,))
                elif revocation == "revoke_verification":
                    conn.execute("UPDATE auth_accounts SET email_verified=0 WHERE id=?", (user.id,))
                elif revocation == "change_destination":
                    conn.execute("UPDATE auth_accounts SET email=? WHERE id=?",
                                 ("new-address@example.test",user.id))
                elif revocation == "delete_saved_notice":
                    conn.execute("DELETE FROM saved_opportunities WHERE "
                                 "organization_id=? AND company_id=?",(org.id,500))
    monkeypatch.setattr(alerts,"candidates",lambda: [candidate])
    deliveries=[]
    outcome=alerts.run_once(send_email=lambda to,msg:deliveries.append((to,msg)),now=NOW)
    assert outcome == {"examined":1,"sent":0,"failed":0}, revocation
    assert deliveries == []
    with closing(db.connect()) as conn:
        count=conn.execute("SELECT COUNT(*) FROM deadline_alert_receipts").fetchone()[0]
    assert count==0,revocation
    db.close()


def test_normal_consent_remains_atomic_and_deduplicated_after_revalidation(tmp_path):
    """The safety check must not accidentally disable valid reminders."""
    db,user,org=_fixture(tmp_path)
    alerts=DeadlineAlerts(db)
    alerts.set_preferences(account_id=user.id,organization_id=org.id,
                           company_id=500,email_enabled=True,telegram_enabled=False)
    deliveries=[]
    first=alerts.run_once(send_email=lambda to,msg:deliveries.append(to),now=NOW)
    second=alerts.run_once(send_email=lambda to,msg:deliveries.append(to),now=NOW)
    assert first["sent"]==1 and first["failed"]==0
    assert second["sent"]==0 and len(deliveries)==1
    with closing(db.connect()) as conn:
        receipts=conn.execute("SELECT state FROM deadline_alert_receipts").fetchall()
    assert len(receipts)==1 and receipts[0]["state"]=="sent"
    db.close()
