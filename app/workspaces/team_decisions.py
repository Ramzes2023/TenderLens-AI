"""Real saved-tender assignment and two-person internal approval.

All operations validate current membership and the active organization/company.
Neither approval nor 'submitted' lifecycle status submits a procurement bid.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone

from app.workspaces.lifecycle import WorkflowDenied, WorkflowMissing, WorkflowConflict


class TeamDecision:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def _scope(conn, *, account_id, organization_id, company_id, saved_id):
        member = conn.execute(
            "SELECT role FROM organization_members WHERE organization_id=? AND account_id=?",
            (organization_id, account_id),
        ).fetchone()
        if member is None:
            raise WorkflowDenied()
        saved = conn.execute(
            "SELECT id FROM saved_opportunities WHERE id=? AND organization_id=? AND company_id=?",
            (saved_id, organization_id, company_id),
        ).fetchone()
        if saved is None:
            raise WorkflowMissing()
        return member["role"]

    @staticmethod
    def _snapshot(row):
        if row is None:
            return {
                "assignee_account_id": None, "approval_state": "not_requested",
                "requested_by_account_id": None, "decided_by_account_id": None,
                "revision": 0, "updated_at": None,
            }
        return {
            "assignee_account_id": row["assignee_account_id"],
            "approval_state": row["approval_state"],
            "requested_by_account_id": row["requested_by_account_id"],
            "decided_by_account_id": row["decided_by_account_id"],
            "revision": int(row["revision"]), "updated_at": row["updated_at"],
        }

    @staticmethod
    def _read(conn, saved_id):
        return TeamDecision._snapshot(conn.execute(
            "SELECT assignee_account_id,approval_state,requested_by_account_id,"
            "decided_by_account_id,revision,updated_at FROM saved_tender_team_decisions "
            "WHERE saved_opportunity_id=?", (saved_id,),
        ).fetchone())

    @staticmethod
    def _members(conn, organization_id):
        return [dict(row) for row in conn.execute(
            "SELECT m.account_id,m.role,a.email FROM organization_members m "
            "JOIN auth_accounts a ON a.id=m.account_id "
            "WHERE m.organization_id=? AND a.is_active=1 ORDER BY m.account_id",
            (organization_id,),
        ).fetchall()]

    def get(self, *, account_id, organization_id, company_id, saved_id):
        with closing(self.database.connect()) as conn:
            role=self._scope(conn,account_id=account_id,organization_id=organization_id,
                             company_id=company_id,saved_id=saved_id)
            row=self._read(conn,saved_id)
            row["members"]=self._members(conn,organization_id)
            row["your_role"]=role
            return row

    def events(self, *, account_id, organization_id, company_id, saved_id):
        with closing(self.database.connect()) as conn:
            self._scope(conn,account_id=account_id,organization_id=organization_id,
                        company_id=company_id,saved_id=saved_id)
            return [dict(r) for r in conn.execute(
                "SELECT actor_account_id,action,previous_state,next_state,"
                "previous_assignee_account_id,next_assignee_account_id,changed_at "
                "FROM saved_tender_team_decision_events WHERE saved_opportunity_id=? "
                "ORDER BY id DESC LIMIT 40", (saved_id,),
            ).fetchall()]

    def change(self, *, account_id, organization_id, company_id, saved_id,
               action, expected_revision, assignee_account_id=None):
        if action not in {"assign","request","approve","reject","withdraw"}:
            raise ValueError("Unsupported internal tender action.")
        if type(expected_revision) is not int or expected_revision<0 or expected_revision>2147483646:
            raise ValueError("Invalid revision.")
        if assignee_account_id is not None and (type(assignee_account_id) is not int or assignee_account_id<=0):
            raise ValueError("Invalid assignee identifier.")
        if action!="assign" and assignee_account_id is not None:
            raise ValueError("Assignee is only valid for assignment.")
        with closing(self.database.connect()) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                role=self._scope(conn,account_id=account_id,organization_id=organization_id,
                                 company_id=company_id,saved_id=saved_id)
                if role=="viewer":
                    raise WorkflowDenied()
                old=self._read(conn,saved_id)
                if old["revision"]!=expected_revision:
                    raise WorkflowConflict()
                new=dict(old)
                if action=="assign":
                    if role not in {"owner","admin"}:
                        raise WorkflowDenied()
                    if assignee_account_id is not None:
                        target=conn.execute(
                            "SELECT 1 FROM organization_members m JOIN auth_accounts a "
                            "ON a.id=m.account_id WHERE m.organization_id=? "
                            "AND m.account_id=? AND a.is_active=1",
                            (organization_id,assignee_account_id),
                        ).fetchone()
                        if target is None:
                            raise WorkflowDenied()
                    if old["assignee_account_id"]==assignee_account_id:
                        return self.get_without_members(conn,new,role)
                    new["assignee_account_id"]=assignee_account_id
                elif action=="request":
                    if old["approval_state"]=="pending":
                        raise WorkflowConflict()
                    new.update(approval_state="pending", requested_by_account_id=account_id,
                               decided_by_account_id=None)
                elif action in {"approve","reject"}:
                    if role not in {"owner","admin"}:
                        raise WorkflowDenied()
                    if old["approval_state"]!="pending":
                        raise WorkflowConflict()
                    if old["requested_by_account_id"]==account_id:
                        raise WorkflowDenied()  # two-person internal authorization
                    new["approval_state"]="approved" if action=="approve" else "rejected"
                    new["decided_by_account_id"]=account_id
                else:
                    if old["approval_state"]!="pending":
                        raise WorkflowConflict()
                    if account_id!=old["requested_by_account_id"] and role not in {"owner","admin"}:
                        raise WorkflowDenied()
                    new.update(approval_state="not_requested",requested_by_account_id=None,
                               decided_by_account_id=None)
                now=datetime.now(timezone.utc).isoformat(timespec="seconds")
                new["revision"]=old["revision"]+1
                new["updated_at"]=now
                conn.execute(
                    "INSERT INTO saved_tender_team_decisions "
                    "(saved_opportunity_id,assignee_account_id,approval_state,"
                    "requested_by_account_id,decided_by_account_id,revision,"
                    "updated_by_account_id,updated_at) VALUES (?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(saved_opportunity_id) DO UPDATE SET "
                    "assignee_account_id=excluded.assignee_account_id,"
                    "approval_state=excluded.approval_state,"
                    "requested_by_account_id=excluded.requested_by_account_id,"
                    "decided_by_account_id=excluded.decided_by_account_id,"
                    "revision=excluded.revision,"
                    "updated_by_account_id=excluded.updated_by_account_id,"
                    "updated_at=excluded.updated_at",
                    (saved_id,new["assignee_account_id"],new["approval_state"],
                     new["requested_by_account_id"],new["decided_by_account_id"],
                     new["revision"],account_id,now),
                )
                conn.execute(
                    "INSERT INTO saved_tender_team_decision_events "
                    "(saved_opportunity_id,actor_account_id,action,previous_state,"
                    "next_state,previous_assignee_account_id,next_assignee_account_id,"
                    "changed_at) VALUES (?,?,?,?,?,?,?,?)",
                    (saved_id,account_id,action,old["approval_state"],new["approval_state"],
                     old["assignee_account_id"],new["assignee_account_id"],now),
                )
                return self.get_without_members(conn,new,role)

    @staticmethod
    def get_without_members(conn,snapshot,role):
        value=dict(snapshot)
        value["members"]=None
        value["your_role"]=role
        return value
