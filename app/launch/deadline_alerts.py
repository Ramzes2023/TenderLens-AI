"""Opt-in tender-deadline reminder scheduling. No automatic sending on import."""
from __future__ import annotations

import asyncio
from contextlib import closing
from datetime import datetime, timezone, timedelta
import json
import os
from urllib.parse import urlsplit

from app.database.backend import database_for
from app.api.schemas import TenderDiscoveryItem

MAX_SAVED_PER_SCOPE = 200
MAX_REMINDERS_PER_CYCLE = 100
LEAD_HOURS = (48,)  # 24-hour notifications require separate release approval.


def aware_deadline(value: str | None) -> datetime | None:
    """Do not assume a timezone for date-only or ambiguous source timestamps."""
    if not value or len(value) > 64:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None or dt.utcoffset() is None:
        return None
    return dt.astimezone(timezone.utc)


def due_lead_hours(deadline: str | None, *, now: datetime) -> int | None:
    parsed = aware_deadline(deadline)
    if parsed is None or now.tzinfo is None:
        return None
    remaining = (parsed - now.astimezone(timezone.utc)).total_seconds()
    if remaining <= 0:
        return None
    for hours in LEAD_HOURS:
        if remaining <= hours * 3600:
            return hours
    return None


def safe_official_url(raw: str | None) -> str:
    try:
        url = urlsplit(raw or "")
        if (url.scheme.lower() != "https" or not url.hostname or url.username
                or url.password or url.port not in (None, 443)):
            return ""
        if any(ord(c) <= 32 or ord(c) == 127 for c in (raw or "")):
            return ""
        return raw
    except (ValueError, TypeError):
        return ""


class DeadlineAlerts:
    def __init__(self, database):
        self.database = database_for(database)

    def initialize(self):
        self.database.migrate("deadline_alerts")

    def preferences(self, *, account_id: int, organization_id: int, company_id: int):
        with closing(self.database.connect()) as connection:
            row = connection.execute(
                "SELECT email_enabled,telegram_enabled FROM deadline_alert_preferences "
                "WHERE account_id=? AND organization_id=? AND company_id=?",
                (account_id, organization_id, company_id),
            ).fetchone()
        return {
            "email_enabled": bool(row["email_enabled"]) if row else False,
            "telegram_enabled": bool(row["telegram_enabled"]) if row else False,
        }

    def set_preferences(self, *, account_id: int, organization_id: int, company_id: int,
                        email_enabled: bool, telegram_enabled: bool):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with closing(self.database.connect()) as conn:
            with conn:
                # Server-side membership confirmation, independent of submitted IDs.
                membership = conn.execute(
                    "SELECT 1 FROM organization_members WHERE account_id=? AND organization_id=?",
                    (account_id, organization_id),
                ).fetchone()
                if membership is None:
                    raise PermissionError("Organization membership required.")
                conn.execute(
                    "INSERT INTO deadline_alert_preferences "
                    "(account_id,organization_id,company_id,email_enabled,telegram_enabled,updated_at) "
                    "VALUES (?,?,?,?,?,?) ON CONFLICT(account_id,organization_id,company_id) "
                    "DO UPDATE SET email_enabled=excluded.email_enabled,"
                    "telegram_enabled=excluded.telegram_enabled,updated_at=excluded.updated_at",
                    (account_id, organization_id, company_id,
                     int(email_enabled), int(telegram_enabled), now),
                )
        return self.preferences(
            account_id=account_id, organization_id=organization_id, company_id=company_id,
        )

    def candidates(self, *, limit: int = MAX_REMINDERS_PER_CYCLE):
        # Preferences + active organization membership + verified email; no unsolicited send.
        with closing(self.database.connect()) as conn:
            records = conn.execute(
                "SELECT p.account_id,p.organization_id,p.company_id,"
                "p.email_enabled,p.telegram_enabled,a.email,a.owner_user_id,"
                "s.source,s.external_id,s.snapshot_json,m.chat_id,m.enabled AS telegram_link_enabled "
                "FROM deadline_alert_preferences p "
                "JOIN auth_accounts a ON a.id=p.account_id "
                "JOIN organization_members om ON om.organization_id=p.organization_id "
                " AND om.account_id=p.account_id "
                "JOIN saved_opportunities s ON s.organization_id=p.organization_id "
                " AND s.company_id=p.company_id "
                "LEFT JOIN monitor_subscriptions m ON m.owner_user_id=a.owner_user_id "
                "WHERE a.is_active=1 AND a.email_verified=1 "
                "AND (p.email_enabled=1 OR p.telegram_enabled=1) "
                "ORDER BY p.organization_id,p.company_id,s.id "
                "LIMIT ?",
                (max(1, min(int(limit), MAX_REMINDERS_PER_CYCLE)),),
            ).fetchall()
        return records

    def _claim(self, row, deadline: str, lead_hours: int, channel: str) -> bool:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with closing(self.database.connect()) as conn:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO deadline_alert_receipts "
                    "(account_id,organization_id,company_id,source,external_id,"
                    "deadline,lead_hours,channel,state,claimed_at) "
                    "VALUES (?,?,?,?,?,?,?,?,'pending',?) ON CONFLICT DO NOTHING",
                    (row["account_id"], row["organization_id"], row["company_id"],
                     row["source"], row["external_id"], deadline, lead_hours, channel, now),
                )
                return cursor.rowcount == 1

    def _mark(self, row, deadline: str, lead_hours: int, channel: str, state: str):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with closing(self.database.connect()) as conn:
            with conn:
                conn.execute(
                    "UPDATE deadline_alert_receipts SET state=?,sent_at=? "
                    "WHERE account_id=? AND organization_id=? AND company_id=? "
                    "AND source=? AND external_id=? AND deadline=? "
                    "AND lead_hours=? AND channel=? AND state='pending'",
                    (state, now if state == "sent" else None,
                     row["account_id"], row["organization_id"], row["company_id"],
                     row["source"], row["external_id"], deadline, lead_hours, channel),
                )

    def run_once(self, *, send_email=None, send_telegram=None, now=None):
        now = now or datetime.now(timezone.utc)
        examined = delivered = failed = 0
        for row in self.candidates():
            examined += 1
            try:
                tender = TenderDiscoveryItem.model_validate_json(row["snapshot_json"])
            except ValueError:
                continue
            # Require exact persisted identity and do not invent missing deadlines.
            if (tender.source != row["source"] or tender.external_id != row["external_id"]):
                continue
            hours = due_lead_hours(tender.deadline, now=now)
            url = safe_official_url(tender.url)
            if hours is None or not url:
                continue
            title = tender.title[:250]
            message = (
                "VALYQON AI — срок подачи заявки приближается\n"
                + f"Закупка: {title}\n"
                + f"Источник: {tender.source}\n"
                + f"Дедлайн источника: {tender.deadline}\n"
                + f"Осталось не более {hours} часов по указанному времени.\n"
                + f"Официальная закупка: {url}\n"
                + "Перед подачей проверьте срок на первоисточнике."
            )
            channels = (
                ("email", bool(row["email_enabled"]), row["email"], send_email),
                ("telegram", bool(row["telegram_enabled"]) and bool(row["telegram_link_enabled"])
                 and bool(row["chat_id"]), row["chat_id"], send_telegram),
            )
            for channel, enabled, destination, sender in channels:
                if not enabled or sender is None:
                    continue
                if not self._claim(row, tender.deadline, hours, channel):
                    continue
                try:
                    sender(destination, message)
                except Exception:
                    failed += 1
                    self._mark(row, tender.deadline, hours, channel, "failed")
                else:
                    delivered += 1
                    self._mark(row, tender.deadline, hours, channel, "sent")
        return {"examined": examined, "sent": delivered, "failed": failed}


def main():
    if os.environ.get("VALYQON_DEADLINE_ALERTS_ENABLED", "").lower() != "true":
        print("DEADLINE_ALERTS=DISABLED")
        return 0
    from app.database.config import load_database_settings
    from app.auth.email_delivery import load_email_sender_from_env

    db = database_for(load_database_settings())
    alerts = DeadlineAlerts(db)
    alerts.initialize()
    sender = load_email_sender_from_env()
    email_function = None
    if sender is not None:
        email_function = lambda to, text: sender.send_deadline_reminder(
            recipient=to, text=text,
        )
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    def telegram_function(chat_id, text):
        from aiogram import Bot
        async def send():
            async with Bot(token=token) as bot:
                await bot.send_message(chat_id=chat_id, text=text, disable_web_page_preview=True)
        asyncio.run(send())
    result = alerts.run_once(
        send_email=email_function,
        send_telegram=telegram_function if token else None,
    )
    print("DEADLINE_ALERTS=RUN; EXAMINED={examined}; SENT={sent}; FAILED={failed}".format(**result))
    return 1 if result["failed"] else 0

if __name__ == "__main__":
    raise SystemExit(main())
