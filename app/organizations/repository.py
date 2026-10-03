"""Internal persistence API. Mutations are serialized and preserve an owner."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .migration import migrate, ensure_personal, now
from .models import Organization, Membership, Role


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
            raise OrganizationError("Organization storage operation failed.") from None
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
            raise OrganizationError("Organization name must contain 1–200 characters.")
        with self.transaction(True) as conn:
            timestamp = now()
            cursor = conn.execute("""INSERT INTO organizations(name,created_at,updated_at,created_by_account_id)
                                     VALUES (?,?,?,?)""", (name, timestamp, timestamp, account_id))
            org_id = cursor.lastrowid
            conn.execute("INSERT INTO organization_members VALUES (?,?,'owner',?)", (org_id, account_id, timestamp))
            return Organization(**dict(conn.execute("SELECT * FROM organizations WHERE id=?", (org_id,)).fetchone()))

    def default_for_account(self, account_id):
        with self.transaction(True) as conn:
            org_id = ensure_personal(conn, account_id)
            return Organization(**dict(conn.execute("SELECT * FROM organizations WHERE id=?", (org_id,)).fetchone()))

    def get(self, organization_id):
        """Internal unrestricted lookup; HTTP callers must use service authorization."""
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM organizations WHERE id=?", (organization_id,)).fetchone()
            return Organization(**dict(row)) if row else None

    def list_for_account(self, account_id):
        with self.transaction() as conn:
            return [Organization(**dict(row)) for row in conn.execute(
                "SELECT o.* FROM organizations o JOIN organization_members m ON m.organization_id=o.id WHERE m.account_id=? ORDER BY o.id", (account_id,))]

    @staticmethod
    def _membership(row):
        return Membership(row["organization_id"], row["account_id"], Role(row["role"]), row["created_at"]) if row else None

    def get_membership(self, organization_id, account_id):
        with self.transaction() as conn:
            return self._membership(conn.execute("SELECT * FROM organization_members WHERE organization_id=? AND account_id=?", (organization_id, account_id)).fetchone())

    def list_memberships(self, organization_id):
        with self.transaction() as conn:
            return [self._membership(row) for row in conn.execute("SELECT * FROM organization_members WHERE organization_id=? ORDER BY account_id", (organization_id,))]

    def add_membership(self, organization_id, account_id, role):
        role = Role(role)
        with self.transaction(True) as conn:
            conn.execute("INSERT INTO organization_members VALUES (?,?,?,?)", (organization_id, account_id, role.value, now()))

    def _change(self, organization_id, account_id, role):
        with self.transaction(True) as conn:
            row = conn.execute("SELECT role FROM organization_members WHERE organization_id=? AND account_id=?", (organization_id, account_id)).fetchone()
            if row is None:
                raise OrganizationError("Membership not found.")
            personal = conn.execute("SELECT personal_account_id FROM organizations WHERE id=?", (organization_id,)).fetchone()[0]
            if personal == account_id and role != Role.OWNER:
                raise OrganizationError("Personal organization owner must remain an owner.")
            if row["role"] == "owner" and role != Role.OWNER:
                count = conn.execute("SELECT COUNT(*) FROM organization_members WHERE organization_id=? AND role='owner'", (organization_id,)).fetchone()[0]
                if count <= 1:
                    raise OrganizationError("Cannot remove the last organization owner.")
            if role is None:
                conn.execute("DELETE FROM organization_members WHERE organization_id=? AND account_id=?", (organization_id, account_id))
            else:
                conn.execute("UPDATE organization_members SET role=? WHERE organization_id=? AND account_id=?", (role.value, organization_id, account_id))

    def update_role(self, organization_id, account_id, role):
        self._change(organization_id, account_id, Role(role))

    def remove_membership(self, organization_id, account_id):
        self._change(organization_id, account_id, None)
