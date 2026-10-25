"""Local Mailpit SMTP acceptance for the real deadline-reminder worker.

Run only against disposable GitHub Actions Mailpit on loopback. Creates a
throwaway SQLite dataset. Never sends to real recipients or external SMTP.
This proves Worker→SMTP→Mailpit→DB, NOT production SMTP deliverability.
"""
from __future__ import annotations

import json
import tempfile
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from app.auth import AuthRepository
from app.auth.email_delivery import SMTPEmailSender
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.launch.deadline_alerts import DeadlineAlerts
from app.organizations import OrganizationRepository


MAILPIT_HTTP = "http://127.0.0.1:8025/api/v1/messages"
TEST_RECIPIENT = "valyqon-worker-mailpit@example.test"
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def inbox():
    with urlopen(MAILPIT_HTTP, timeout=5) as response:
        data = json.load(response)
    messages = data.get("messages")
    if not isinstance(messages, list):
        raise ValueError("Unexpected Mailpit API response")
    return messages


def wait_for_mailpit():
    for attempt in range(20):
        try:
            return inbox()
        except (OSError, ValueError):
            time.sleep(0.5)
    raise RuntimeError("Mailpit did not become available on loopback")


def main():
    previous = wait_for_mailpit()
    if previous:
        raise RuntimeError("Acceptance requires an empty disposable Mailpit inbox")
    with tempfile.TemporaryDirectory(prefix="valyqon-mailpit-worker-") as folder:
        db = Database(DatabaseSettings("", Path(folder) / "disposable.sqlite"))
        db.migrate()
        try:
            user = AuthRepository(db).create_account(TEST_RECIPIENT, "test-only-hash")
            org = OrganizationRepository(db).default_for_account(user.id)
            notice = {
                "source": "eis",
                "external_id": "OFFLINE_FIXTURE_MAILPIT_001",
                "title": "OFFLINE_FIXTURE: local-only application deadline",
                "url": "https://zakupki.gov.ru/view/OFFLINE_FIXTURE_MAILPIT_001",
                "deadline": "2026-10-26T10:00:00+00:00",
                "reasons": [],
                "metadata_analysis": {},
                "preliminary_scoring": {
                    "profile_name": "OFFLINE_FIXTURE company",
                    "profile_version": "1",
                    "fit_score": 82,
                    "scorable_weight": 100,
                    "completeness_percent": 80,
                    "criteria": [],
                },
            }
            with closing(db.connect()) as conn:
                with conn:
                    conn.execute("UPDATE auth_accounts SET email_verified=1 WHERE id=?", (user.id,))
                    conn.execute(
                        "INSERT INTO saved_opportunities "
                        "(organization_id,company_id,source,external_id,snapshot_json,created_at,updated_at) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (org.id, 42, notice["source"], notice["external_id"],
                         json.dumps(notice), NOW.isoformat(), NOW.isoformat()),
                    )

            alerts = DeadlineAlerts(db)
            smtp = SMTPEmailSender(
                host="127.0.0.1", port=1025,
                from_address="ci@valyqon.example.test",
                public_base_url="http://127.0.0.1:18865",
                starttls=False, ssl_enabled=False, timeout_seconds=5,
            )
            sender = lambda recipient, message: smtp.send_deadline_reminder(
                recipient=recipient, text=message,
            )
            # Default opt-out: nothing must leave the Worker.
            assert alerts.run_once(send_email=sender, now=NOW)["sent"] == 0
            assert inbox() == [], "A notification was sent without opt-in"
            alerts.set_preferences(
                account_id=user.id, organization_id=org.id, company_id=42,
                email_enabled=True, telegram_enabled=False,
            )

            first = alerts.run_once(send_email=sender, now=NOW)
            assert first == {"examined": 1, "sent": 1, "failed": 0}, first
            second = alerts.run_once(send_email=sender, now=NOW)
            assert second["sent"] == 0, second

            for i in range(10):
                messages = inbox()
                if len(messages) == 1:
                    break
                time.sleep(0.5)
            assert len(messages) == 1, "Expected exactly one real Mailpit SMTP message"
            msg = messages[0]
            assert "deadline approaching" in str(msg.get("Subject", "")).lower()
            assert str(msg.get("ID", "")).strip()
            with urlopen("http://127.0.0.1:8025/api/v1/message/" + str(msg["ID"]), timeout=5) as response:
                email_details = json.load(response)
            body = str(email_details.get("Text", ""))
            assert "OFFLINE_FIXTURE_MAILPIT_001" in body
            assert "2026-10-26T10:00:00+00:00" in body
            assert "zakupki.gov.ru" in body
            assert "Перед подачей проверьте срок" in body
            with closing(db.connect()) as conn:
                receipt = conn.execute(
                    "SELECT state,channel,lead_hours,sent_at FROM deadline_alert_receipts"
                ).fetchall()
            assert len(receipt) == 1
            assert receipt[0]["state"] == "sent" and receipt[0]["channel"] == "email"
            assert receipt[0]["lead_hours"] == 48 and receipt[0]["sent_at"]
            journal = alerts.delivery_history(
                account_id=user.id, organization_id=org.id, company_id=42,
            )
            assert journal["records"][0]["state"] == "sent"
            assert journal["records"][0]["saved_id"] is not None
            assert journal["delivery_confirmation"] == "sender_return_only"
            print("OPT_OUT=PASS")
            print("WORKER_TO_LOCAL_SMTP=PASS")
            print("MAILPIT_INBOX_CAPTURE=PASS")
            print("WORKER_RECEIPT_AND_AUTH_JOURNAL=PASS")
            print("DEADLINE_DEDUPLICATION=PASS")
            print("EXTERNAL_DELIVERY=NOT_TESTED")
            print("LIVE_TENDER_SOURCE=OFFLINE_FIXTURE_ONLY")
        finally:
            db.close()


if __name__ == "__main__":
    main()
