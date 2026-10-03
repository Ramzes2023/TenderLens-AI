"""Internal organization persistence with transactional RBAC invariants."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .migration import ensure_personal, migrate, now
from .models import Membership, Organization, Role


class OrganizationError(ValueError):
    pass


class OrganizationRepository:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def transaction(self, write=False):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise OrganizationError(
                "Organization storage operation failed."
            ) from None
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self):
        with self.transaction(True) as conn:
            migrate(conn)

    def create(self, name, account_id):
        name = name.strip()
        if not 1 <= len(name) <= 200:
            raise OrganizationError(
                "Organization name must contain 1?200 characters."
            )
        with self.transaction(True) as conn:
            timestamp = now()
            cursor = conn.execute(
                """INSERT INTO organizations(
                    name, created_at, updated_at, created_by_account_id
                ) VALUES (?,?,?,?)""",
                (name, timestamp, timestamp, account_id),
            )
            org_id = int(cursor.lastrowid)
            conn.execute(
                """INSERT INTO organization_members(
                    organization_id, account_id, role, created_at
                ) VALUES (?,?,'owner',?)""",
                (org_id, account_id, timestamp),
            )
            row = conn.execute(
                "SELECT * FROM organizations WHERE id=?",
                (org_id,),
            ).fetchone()
            return Organization(**dict(row))

    def default_for_account(self, account_id):
        with self.transaction(True) as conn:
            org_id = ensure_personal(conn, account_id)
            row = conn.execute(
                "SELECT * FROM organizations WHERE id=?",
                (org_id,),
            ).fetchone()
            return Organization(**dict(row))

    def get(self, organization_id):
        """Internal unrestricted lookup; HTTP callers must use service authorization."""
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM organizations WHERE id=?",
                (organization_id,),
            ).fetchone()
            return Organization(**dict(row)) if row else None

    def list_for_account(self, account_id):
        with self.transaction() as conn:
            rows = conn.execute(
                """SELECT o.*
                   FROM organizations o
                   JOIN organization_members m
                     ON m.organization_id=o.id
                   WHERE m.account_id=?
                   ORDER BY o.id""",
                (account_id,),
            )
            return [Organization(**dict(row)) for row in rows]

    @staticmethod
    def _membership(row):
        if row is None:
            return None
        return Membership(
            row["organization_id"],
            row["account_id"],
            Role(row["role"]),
            row["created_at"],
        )

    def get_membership(self, organization_id, account_id):
        with self.transaction() as conn:
            row = conn.execute(
                """SELECT *
                   FROM organization_members
                   WHERE organization_id=? AND account_id=?""",
                (organization_id, account_id),
            ).fetchone()
            return self._membership(row)

    def list_memberships(self, organization_id):
        with self.transaction() as conn:
            rows = conn.execute(
                """SELECT *
                   FROM organization_members
                   WHERE organization_id=?
                   ORDER BY account_id""",
                (organization_id,),
            )
            return [self._membership(row) for row in rows]

    # -----------------------------------------------------------------
    # Low-level trusted methods kept for internal compatibility.
    # -----------------------------------------------------------------

    def add_membership(self, organization_id, account_id, role):
        role = Role(role)
        with self.transaction(True) as conn:
            conn.execute(
                """INSERT INTO organization_members(
                    organization_id, account_id, role, created_at
                ) VALUES (?,?,?,?)""",
                (organization_id, account_id, role.value, now()),
            )

    @staticmethod
    def _change_in_conn(conn, organization_id, account_id, role):
        row = conn.execute(
            """SELECT role
               FROM organization_members
               WHERE organization_id=? AND account_id=?""",
            (organization_id, account_id),
        ).fetchone()
        if row is None:
            raise OrganizationError("Membership not found.")

        personal_row = conn.execute(
            "SELECT personal_account_id FROM organizations WHERE id=?",
            (organization_id,),
        ).fetchone()
        if personal_row is None:
            raise OrganizationError("Organization not found.")

        personal_account_id = personal_row["personal_account_id"]

        if personal_account_id == account_id and role != Role.OWNER:
            raise OrganizationError(
                "Personal organization owner must remain an owner."
            )

        if row["role"] == Role.OWNER.value and role != Role.OWNER:
            owner_count = conn.execute(
                """SELECT COUNT(*)
                   FROM organization_members
                   WHERE organization_id=? AND role='owner'""",
                (organization_id,),
            ).fetchone()[0]
            if owner_count <= 1:
                raise OrganizationError(
                    "Cannot remove the last organization owner."
                )

        if role is None:
            conn.execute(
                """DELETE FROM organization_members
                   WHERE organization_id=? AND account_id=?""",
                (organization_id, account_id),
            )
        else:
            conn.execute(
                """UPDATE organization_members
                   SET role=?
                   WHERE organization_id=? AND account_id=?""",
                (role.value, organization_id, account_id),
            )

    def _change(self, organization_id, account_id, role):
        with self.transaction(True) as conn:
            self._change_in_conn(
                conn,
                organization_id,
                account_id,
                role,
            )

    def update_role(self, organization_id, account_id, role):
        self._change(
            organization_id,
            account_id,
            Role(role),
        )

    def remove_membership(self, organization_id, account_id):
        self._change(
            organization_id,
            account_id,
            None,
        )

    # -----------------------------------------------------------------
    # Phase 18B actor-aware methods.
    #
    # Authorization and mutation intentionally happen under the SAME
    # BEGIN IMMEDIATE transaction. This avoids role-check/mutation races.
    # -----------------------------------------------------------------

    @staticmethod
    def _manager_role(conn, organization_id, actor_account_id):
        row = conn.execute(
            """SELECT role
               FROM organization_members
               WHERE organization_id=? AND account_id=?""",
            (organization_id, actor_account_id),
        ).fetchone()

        if row is None:
            raise OrganizationError("Organization access denied.")

        role = Role(row["role"])
        if role not in {Role.OWNER, Role.ADMIN}:
            raise OrganizationError("Organization access denied.")

        return role

    def add_membership_authorized(
        self,
        *,
        actor_account_id,
        organization_id,
        account_id,
        role,
    ):
        role = Role(role)

        with self.transaction(True) as conn:
            actor_role = self._manager_role(
                conn,
                organization_id,
                actor_account_id,
            )

            if actor_role == Role.ADMIN and role == Role.OWNER:
                raise OrganizationError(
                    "Only an organization owner can grant the owner role."
                )

            account_exists = conn.execute(
                "SELECT 1 FROM auth_accounts WHERE id=?",
                (account_id,),
            ).fetchone()
            if account_exists is None:
                raise OrganizationError("Account not found.")

            existing = conn.execute(
                """SELECT 1
                   FROM organization_members
                   WHERE organization_id=? AND account_id=?""",
                (organization_id, account_id),
            ).fetchone()
            if existing is not None:
                raise OrganizationError("Membership already exists.")

            timestamp = now()
            conn.execute(
                """INSERT INTO organization_members(
                    organization_id, account_id, role, created_at
                ) VALUES (?,?,?,?)""",
                (
                    organization_id,
                    account_id,
                    role.value,
                    timestamp,
                ),
            )

            row = conn.execute(
                """SELECT *
                   FROM organization_members
                   WHERE organization_id=? AND account_id=?""",
                (organization_id, account_id),
            ).fetchone()
            return self._membership(row)

    def update_role_authorized(
        self,
        *,
        actor_account_id,
        organization_id,
        account_id,
        role,
    ):
        role = Role(role)

        with self.transaction(True) as conn:
            actor_role = self._manager_role(
                conn,
                organization_id,
                actor_account_id,
            )

            target = conn.execute(
                """SELECT role
                   FROM organization_members
                   WHERE organization_id=? AND account_id=?""",
                (organization_id, account_id),
            ).fetchone()
            if target is None:
                raise OrganizationError("Membership not found.")

            target_role = Role(target["role"])

            if actor_role == Role.ADMIN and (
                target_role == Role.OWNER or role == Role.OWNER
            ):
                raise OrganizationError(
                    "Only an organization owner can manage owner membership."
                )

            self._change_in_conn(
                conn,
                organization_id,
                account_id,
                role,
            )

            row = conn.execute(
                """SELECT *
                   FROM organization_members
                   WHERE organization_id=? AND account_id=?""",
                (organization_id, account_id),
            ).fetchone()
            return self._membership(row)

    def remove_membership_authorized(
        self,
        *,
        actor_account_id,
        organization_id,
        account_id,
    ):
        with self.transaction(True) as conn:
            actor_role = self._manager_role(
                conn,
                organization_id,
                actor_account_id,
            )

            target = conn.execute(
                """SELECT role
                   FROM organization_members
                   WHERE organization_id=? AND account_id=?""",
                (organization_id, account_id),
            ).fetchone()
            if target is None:
                raise OrganizationError("Membership not found.")

            target_role = Role(target["role"])

            if actor_role == Role.ADMIN and target_role == Role.OWNER:
                raise OrganizationError(
                    "Only an organization owner can manage owner membership."
                )

            self._change_in_conn(
                conn,
                organization_id,
                account_id,
                None,
            )
