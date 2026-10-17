"""Tenant-scoped saved-tender workflow. No notifications, submissions or billing effects."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone

from app.database.backend import StorageError

STAGES = frozenset({"new", "reviewing", "preparing", "submitted", "won", "lost", "archived"})
WRITE_ROLES = frozenset({"owner", "admin", "member"})


class WorkflowDenied(Exception):
    pass


class WorkflowMissing(Exception):
    pass


class WorkflowConflict(Exception):
    pass


class SavedTenderWorkflow:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def _scope(conn, account_id, organization_id, company_id, saved_id, *, write):
        member = conn.execute(
            "SELECT role FROM organization_members WHERE organization_id=? AND account_id=?",
            (organization_id, account_id),
        ).fetchone()
        if member is None or (write and member["role"] not in WRITE_ROLES):
            raise WorkflowDenied()
        saved = conn.execute(
            "SELECT id FROM saved_opportunities WHERE id=? AND organization_id=? AND company_id=?",
            (saved_id, organization_id, company_id),
        ).fetchone()
        if saved is None:
            raise WorkflowMissing()

    @staticmethod
    def _snapshot(row):
        if row is None:
            return {"stage": "new", "note": "", "revision": 0, "updated_at": None}
        return {
            "stage": row["stage"],
            "note": row["note"],
            "revision": int(row["revision"]),
            "updated_at": row["updated_at"],
        }

    def get(self, *, account_id, organization_id, company_id, saved_id):
        with closing(self.database.connect()) as conn:
            self._scope(conn, account_id, organization_id, company_id, saved_id, write=False)
            row = conn.execute(
                "SELECT stage,note,revision,updated_at FROM saved_opportunity_workflow "
                "WHERE saved_opportunity_id=?", (saved_id,),
            ).fetchone()
            return self._snapshot(row)

    def update(self, *, account_id, organization_id, company_id, saved_id,
               stage, note, expected_revision):
        if stage not in STAGES or not isinstance(note, str) or len(note) > 2000:
            raise ValueError("Invalid workflow stage or note.")
        if type(expected_revision) is not int or not 0 <= expected_revision < 2147483647:
            raise ValueError("Invalid revision.")
        with closing(self.database.connect()) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                self._scope(conn, account_id, organization_id, company_id, saved_id, write=True)
                old = conn.execute(
                    "SELECT stage,note,revision,updated_at FROM saved_opportunity_workflow "
                    "WHERE saved_opportunity_id=?", (saved_id,),
                ).fetchone()
                current = self._snapshot(old)
                if current["revision"] != expected_revision:
                    raise WorkflowConflict()
                if current["stage"] == stage and current["note"] == note:
                    return current
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                conn.execute(
                    "INSERT INTO saved_opportunity_workflow "
                    "(saved_opportunity_id,stage,note,revision,updated_by_account_id,updated_at) "
                    "VALUES (?,?,?,?,?,?) ON CONFLICT(saved_opportunity_id) DO UPDATE SET "
                    "stage=excluded.stage,note=excluded.note,revision=excluded.revision,"
                    "updated_by_account_id=excluded.updated_by_account_id,updated_at=excluded.updated_at",
                    (saved_id, stage, note, expected_revision + 1, account_id, now),
                )
                conn.execute(
                    "INSERT INTO saved_opportunity_workflow_events "
                    "(saved_opportunity_id,actor_account_id,previous_stage,next_stage,note_changed,changed_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (saved_id, account_id, current["stage"], stage,
                     int(current["note"] != note), now),
                )
                return {"stage": stage, "note": note, "revision": expected_revision + 1,
                        "updated_at": now}

    def events(self, *, account_id, organization_id, company_id, saved_id):
        with closing(self.database.connect()) as conn:
            self._scope(conn, account_id, organization_id, company_id, saved_id, write=False)
            rows = conn.execute(
                "SELECT actor_account_id,previous_stage,next_stage,note_changed,changed_at "
                "FROM saved_opportunity_workflow_events WHERE saved_opportunity_id=? "
                "ORDER BY id DESC LIMIT 20", (saved_id,),
            ).fetchall()
            return [dict(row) for row in rows]
