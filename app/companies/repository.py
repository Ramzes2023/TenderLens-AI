"""SQLite repository for multi-company workspaces.

The tables deliberately live in the same SQLite database as tender history so
Docker/API/bot processes can share one persistent state volume.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from app.scoring.models import CompanyProfile

from .models import CompanyWorkspace
from app.organizations.migration import migrate, backfill_companies


ORGANIZATION_OWNER_OFFSET = 8_000_000_000_000


class CompanyRepositoryError(RuntimeError):
    pass


class CompanyAuthorizationError(CompanyRepositoryError):
    pass


class CompanyNotFoundError(CompanyRepositoryError):
    pass


class CompanyRepository:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as conn:
                with conn:
                    conn.executescript(
                        """
                        CREATE TABLE IF NOT EXISTS company_workspaces (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            owner_user_id INTEGER NOT NULL,
                            name TEXT NOT NULL,
                            profile_json TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            UNIQUE(owner_user_id, name)
                        );

                        CREATE INDEX IF NOT EXISTS idx_company_owner
                        ON company_workspaces(owner_user_id, updated_at DESC);

                        CREATE TABLE IF NOT EXISTS company_active (
                            owner_user_id INTEGER PRIMARY KEY,
                            company_id INTEGER NOT NULL,
                            updated_at TEXT NOT NULL,
                            FOREIGN KEY(company_id) REFERENCES company_workspaces(id) ON DELETE CASCADE
                        );
                        """
                    )
                    conn.execute("BEGIN IMMEDIATE")
                    migrate(conn)
        except (OSError, sqlite3.Error):
            raise CompanyRepositoryError("Не удалось инициализировать company workspace storage.") from None

    @staticmethod
    def _workspace(row: sqlite3.Row, active_id: int | None = None) -> CompanyWorkspace:
        try:
            profile = CompanyProfile.model_validate_json(row["profile_json"])
            return CompanyWorkspace(
                id=int(row["id"]),
                owner_user_id=int(row["owner_user_id"]),
                organization_id=(
                    int(row["organization_id"])
                    if "organization_id" in row.keys()
                    and row["organization_id"] is not None
                    else None
                ),
                name=row["name"],
                profile=profile,
                is_active=int(row["id"]) == active_id,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        except Exception:
            raise CompanyRepositoryError("Сохранённый профиль компании повреждён.") from None

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _reserved_organization_owner(owner_user_id: int) -> bool:
        return int(owner_user_id) >= ORGANIZATION_OWNER_OFFSET

    @staticmethod
    def _organization_owner_id(organization_id: int) -> int:
        return ORGANIZATION_OWNER_OFFSET + int(organization_id)

    def _active_id(self, conn: sqlite3.Connection, owner_user_id: int) -> int | None:
        row = conn.execute(
            "SELECT company_id FROM company_active WHERE owner_user_id=?",
            (int(owner_user_id),),
        ).fetchone()
        return int(row["company_id"]) if row else None

    def create(self, owner_user_id: int, name: str, profile: CompanyProfile,
               *, make_active: bool = True) -> CompanyWorkspace:
        if self._reserved_organization_owner(owner_user_id):
            raise CompanyRepositoryError(
                "Reserved organization owner namespace."
            )

        clean_name = " ".join(name.split())[:200]
        if not clean_name:
            raise CompanyRepositoryError("Название компании не может быть пустым.")
        now = self._now()
        try:
            with closing(self._connect()) as conn:
                with conn:
                    cursor = conn.execute(
                        """
                        INSERT INTO company_workspaces(owner_user_id, name, profile_json, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (int(owner_user_id), clean_name, profile.model_dump_json(), now, now),
                    )
                    company_id = int(cursor.lastrowid)
                    backfill_companies(conn, owner_user_id)
                    active_id = self._active_id(conn, owner_user_id)
                    if make_active or active_id is None:
                        conn.execute(
                            """
                            INSERT INTO company_active(owner_user_id, company_id, updated_at)
                            VALUES (?, ?, ?)
                            ON CONFLICT(owner_user_id) DO UPDATE SET
                                company_id=excluded.company_id,
                                updated_at=excluded.updated_at
                            """,
                            (int(owner_user_id), company_id, now),
                        )
                        active_id = company_id
                    row = conn.execute(
                        "SELECT * FROM company_workspaces WHERE id=? AND owner_user_id=?",
                        (company_id, int(owner_user_id)),
                    ).fetchone()
            if row is None:
                raise CompanyRepositoryError("Не удалось сохранить профиль компании.")
            return self._workspace(row, active_id)
        except sqlite3.IntegrityError:
            raise CompanyRepositoryError("Компания с таким названием уже существует.") from None
        except sqlite3.Error:
            raise CompanyRepositoryError("Не удалось сохранить профиль компании.") from None

    def list_for_owner(self, owner_user_id: int) -> list[CompanyWorkspace]:
        if self._reserved_organization_owner(owner_user_id):
            return []

        try:
            with closing(self._connect()) as conn:
                active_id = self._active_id(conn, owner_user_id)
                rows = conn.execute(
                    "SELECT * FROM company_workspaces WHERE owner_user_id=? ORDER BY updated_at DESC, id DESC",
                    (int(owner_user_id),),
                ).fetchall()
            return [self._workspace(row, active_id) for row in rows]
        except sqlite3.Error:
            raise CompanyRepositoryError("Не удалось получить список компаний.") from None

    def get(self, owner_user_id: int, company_id: int) -> CompanyWorkspace | None:
        if self._reserved_organization_owner(owner_user_id):
            return None

        try:
            with closing(self._connect()) as conn:
                active_id = self._active_id(conn, owner_user_id)
                row = conn.execute(
                    "SELECT * FROM company_workspaces WHERE owner_user_id=? AND id=?",
                    (int(owner_user_id), int(company_id)),
                ).fetchone()
            return self._workspace(row, active_id) if row else None
        except sqlite3.Error:
            raise CompanyRepositoryError("Не удалось прочитать профиль компании.") from None

    def active(self, owner_user_id: int) -> CompanyWorkspace | None:
        if self._reserved_organization_owner(owner_user_id):
            return None

        try:
            with closing(self._connect()) as conn:
                active_id = self._active_id(conn, owner_user_id)
                if active_id is None:
                    return None
                row = conn.execute(
                    "SELECT * FROM company_workspaces WHERE owner_user_id=? AND id=?",
                    (int(owner_user_id), active_id),
                ).fetchone()
            return self._workspace(row, active_id) if row else None
        except sqlite3.Error:
            raise CompanyRepositoryError("Не удалось прочитать активную компанию.") from None

    def set_active(self, owner_user_id: int, company_id: int) -> CompanyWorkspace:
        if self._reserved_organization_owner(owner_user_id):
            raise CompanyRepositoryError("Company not found.")

        now = self._now()
        try:
            with closing(self._connect()) as conn:
                with conn:
                    row = conn.execute(
                        "SELECT * FROM company_workspaces WHERE owner_user_id=? AND id=?",
                        (int(owner_user_id), int(company_id)),
                    ).fetchone()
                    if row is None:
                        raise CompanyRepositoryError("Компания не найдена.")
                    conn.execute(
                        """
                        INSERT INTO company_active(owner_user_id, company_id, updated_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(owner_user_id) DO UPDATE SET
                            company_id=excluded.company_id,
                            updated_at=excluded.updated_at
                        """,
                        (int(owner_user_id), int(company_id), now),
                    )
            return self._workspace(row, int(company_id))
        except CompanyRepositoryError:
            raise
        except sqlite3.Error:
            raise CompanyRepositoryError("Не удалось переключить активную компанию.") from None

    def update_profile(self, owner_user_id: int, company_id: int, profile: CompanyProfile,
                       *, name: str | None = None) -> CompanyWorkspace:
        if self._reserved_organization_owner(owner_user_id):
            raise CompanyRepositoryError("Company not found.")

        now = self._now()
        try:
            with closing(self._connect()) as conn:
                with conn:
                    current = conn.execute(
                        "SELECT * FROM company_workspaces WHERE owner_user_id=? AND id=?",
                        (int(owner_user_id), int(company_id)),
                    ).fetchone()
                    if current is None:
                        raise CompanyRepositoryError("Компания не найдена.")
                    clean_name = " ".join((name or current["name"]).split())[:200]
                    conn.execute(
                        """
                        UPDATE company_workspaces
                        SET name=?, profile_json=?, updated_at=?
                        WHERE owner_user_id=? AND id=?
                        """,
                        (clean_name, profile.model_dump_json(), now, int(owner_user_id), int(company_id)),
                    )
                    active_id = self._active_id(conn, owner_user_id)
                    row = conn.execute(
                        "SELECT * FROM company_workspaces WHERE owner_user_id=? AND id=?",
                        (int(owner_user_id), int(company_id)),
                    ).fetchone()
            return self._workspace(row, active_id)
        except sqlite3.IntegrityError:
            raise CompanyRepositoryError("Компания с таким названием уже существует.") from None
        except CompanyRepositoryError:
            raise
        except sqlite3.Error:
            raise CompanyRepositoryError("Не удалось обновить профиль компании.") from None

    def delete(self, owner_user_id: int, company_id: int) -> bool:
        if self._reserved_organization_owner(owner_user_id):
            return False

        try:
            with closing(self._connect()) as conn:
                with conn:
                    active_id = self._active_id(conn, owner_user_id)
                    cursor = conn.execute(
                        "DELETE FROM company_workspaces WHERE owner_user_id=? AND id=?",
                        (int(owner_user_id), int(company_id)),
                    )
                    deleted = cursor.rowcount > 0
                    if deleted and active_id == int(company_id):
                        replacement = conn.execute(
                            "SELECT id FROM company_workspaces WHERE owner_user_id=? ORDER BY updated_at DESC, id DESC LIMIT 1",
                            (int(owner_user_id),),
                        ).fetchone()
                        if replacement:
                            conn.execute(
                                """
                                INSERT INTO company_active(owner_user_id, company_id, updated_at)
                                VALUES (?, ?, ?)
                                ON CONFLICT(owner_user_id) DO UPDATE SET
                                    company_id=excluded.company_id,
                                    updated_at=excluded.updated_at
                                """,
                                (int(owner_user_id), int(replacement["id"]), self._now()),
                            )
                        else:
                            conn.execute("DELETE FROM company_active WHERE owner_user_id=?", (int(owner_user_id),))
            return deleted
        except sqlite3.Error:
            raise CompanyRepositoryError("Не удалось удалить профиль компании.") from None

    # ================================================================
    # Phase 18C - organization-scoped company operations.
    #
    # Membership authorization and writes happen on the same SQLite
    # connection/transaction to avoid check-then-write races.
    # Legacy owner_user_id methods above remain unchanged.
    # ================================================================

    @staticmethod
    def _require_org_role(
        conn: sqlite3.Connection,
        account_id: int,
        organization_id: int,
        allowed_roles: set[str] | None = None,
    ) -> str:
        row = conn.execute(
            """SELECT role
               FROM organization_members
               WHERE organization_id=? AND account_id=?""",
            (int(organization_id), int(account_id)),
        ).fetchone()

        if row is None:
            raise CompanyAuthorizationError(
                "Organization access denied."
            )

        role = str(row["role"])

        if allowed_roles is not None and role not in allowed_roles:
            raise CompanyAuthorizationError(
                "Organization access denied."
            )

        return role

    def list_for_organization(
        self,
        account_id: int,
        organization_id: int,
    ) -> list[CompanyWorkspace]:
        try:
            with closing(self._connect()) as conn:
                self._require_org_role(
                    conn,
                    account_id,
                    organization_id,
                )
                active_id = self._active_id(
                    conn,
                    self._organization_owner_id(organization_id),
                )
                rows = conn.execute(
                    """SELECT *
                       FROM company_workspaces
                       WHERE organization_id=?
                       ORDER BY updated_at DESC, id DESC""",
                    (int(organization_id),),
                ).fetchall()

            return [
                self._workspace(row, active_id)
                for row in rows
            ]
        except CompanyAuthorizationError:
            raise
        except sqlite3.Error:
            raise CompanyRepositoryError(
                "Company storage is unavailable."
            ) from None

    def get_for_organization(
        self,
        account_id: int,
        organization_id: int,
        company_id: int,
    ) -> CompanyWorkspace | None:
        try:
            with closing(self._connect()) as conn:
                self._require_org_role(
                    conn,
                    account_id,
                    organization_id,
                )
                active_id = self._active_id(
                    conn,
                    self._organization_owner_id(organization_id),
                )
                row = conn.execute(
                    """SELECT *
                       FROM company_workspaces
                       WHERE organization_id=? AND id=?""",
                    (
                        int(organization_id),
                        int(company_id),
                    ),
                ).fetchone()

            return (
                self._workspace(row, active_id)
                if row is not None
                else None
            )
        except CompanyAuthorizationError:
            raise
        except sqlite3.Error:
            raise CompanyRepositoryError(
                "Company storage is unavailable."
            ) from None

    def create_for_organization(
        self,
        *,
        account_id: int,
        organization_id: int,
        name: str,
        profile: CompanyProfile,
    ) -> CompanyWorkspace:
        clean_name = " ".join(name.split())[:200]
        if not clean_name:
            raise CompanyRepositoryError(
                "Company name cannot be empty."
            )

        timestamp = self._now()

        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute("BEGIN IMMEDIATE")

                    self._require_org_role(
                        conn,
                        account_id,
                        organization_id,
                        {"owner", "admin", "member"},
                    )

                    organization_owner_id = self._organization_owner_id(
                        organization_id
                    )

                    cursor = conn.execute(
                        """INSERT INTO company_workspaces(
                            owner_user_id,
                            organization_id,
                            name,
                            profile_json,
                            created_at,
                            updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            organization_owner_id,
                            int(organization_id),
                            clean_name,
                            profile.model_dump_json(),
                            timestamp,
                            timestamp,
                        ),
                    )

                    company_id = int(cursor.lastrowid)

                    active_id = self._active_id(
                        conn,
                        organization_owner_id,
                    )

                    if active_id is None:
                        conn.execute(
                            """INSERT INTO company_active(
                                owner_user_id,
                                company_id,
                                updated_at
                            ) VALUES (?, ?, ?)""",
                            (
                                organization_owner_id,
                                company_id,
                                timestamp,
                            ),
                        )
                        active_id = company_id

                    row = conn.execute(
                        """SELECT *
                           FROM company_workspaces
                           WHERE organization_id=? AND id=?""",
                        (
                            int(organization_id),
                            company_id,
                        ),
                    ).fetchone()

            if row is None:
                raise CompanyRepositoryError(
                    "Could not save company profile."
                )

            return self._workspace(row, active_id)

        except CompanyAuthorizationError:
            raise
        except sqlite3.IntegrityError:
            raise CompanyRepositoryError(
                "Company with this name already exists in the organization."
            ) from None
        except sqlite3.Error:
            raise CompanyRepositoryError(
                "Company storage is unavailable."
            ) from None

    def active_for_organization(
        self,
        account_id: int,
        organization_id: int,
    ) -> CompanyWorkspace | None:
        try:
            with closing(self._connect()) as conn:
                self._require_org_role(
                    conn,
                    account_id,
                    organization_id,
                )

                active_id = self._active_id(
                    conn,
                    self._organization_owner_id(organization_id),
                )

                if active_id is None:
                    return None

                row = conn.execute(
                    """SELECT *
                       FROM company_workspaces
                       WHERE organization_id=? AND id=?""",
                    (
                        int(organization_id),
                        active_id,
                    ),
                ).fetchone()

            return (
                self._workspace(row, active_id)
                if row is not None
                else None
            )

        except CompanyAuthorizationError:
            raise
        except sqlite3.Error:
            raise CompanyRepositoryError(
                "Company storage is unavailable."
            ) from None

    def set_active_for_organization(
        self,
        *,
        account_id: int,
        organization_id: int,
        company_id: int,
    ) -> CompanyWorkspace:
        timestamp = self._now()

        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute("BEGIN IMMEDIATE")

                    self._require_org_role(
                        conn,
                        account_id,
                        organization_id,
                        {"owner", "admin", "member"},
                    )

                    row = conn.execute(
                        """SELECT *
                           FROM company_workspaces
                           WHERE organization_id=? AND id=?""",
                        (
                            int(organization_id),
                            int(company_id),
                        ),
                    ).fetchone()

                    if row is None:
                        raise CompanyNotFoundError(
                            "Company not found."
                        )

                    organization_owner_id = self._organization_owner_id(
                        organization_id
                    )

                    conn.execute(
                        """INSERT INTO company_active(
                            owner_user_id,
                            company_id,
                            updated_at
                        ) VALUES (?, ?, ?)
                        ON CONFLICT(owner_user_id) DO UPDATE SET
                            company_id=excluded.company_id,
                            updated_at=excluded.updated_at""",
                        (
                            organization_owner_id,
                            int(company_id),
                            timestamp,
                        ),
                    )

            return self._workspace(
                row,
                int(company_id),
            )

        except (
            CompanyAuthorizationError,
            CompanyNotFoundError,
        ):
            raise
        except sqlite3.Error:
            raise CompanyRepositoryError(
                "Company storage is unavailable."
            ) from None

    def update_for_organization(
        self,
        *,
        account_id: int,
        organization_id: int,
        company_id: int,
        profile: CompanyProfile | None = None,
        name: str | None = None,
    ) -> CompanyWorkspace:
        timestamp = self._now()

        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute("BEGIN IMMEDIATE")

                    self._require_org_role(
                        conn,
                        account_id,
                        organization_id,
                        {"owner", "admin", "member"},
                    )

                    current = conn.execute(
                        """SELECT *
                           FROM company_workspaces
                           WHERE organization_id=? AND id=?""",
                        (
                            int(organization_id),
                            int(company_id),
                        ),
                    ).fetchone()

                    if current is None:
                        raise CompanyNotFoundError(
                            "Company not found."
                        )

                    clean_name = current["name"]

                    if name is not None:
                        clean_name = " ".join(name.split())[:200]
                        if not clean_name:
                            raise CompanyRepositoryError(
                                "Company name cannot be empty."
                            )

                    profile_json = (
                        profile.model_dump_json()
                        if profile is not None
                        else current["profile_json"]
                    )

                    conn.execute(
                        """UPDATE company_workspaces
                           SET name=?, profile_json=?, updated_at=?
                           WHERE organization_id=? AND id=?""",
                        (
                            clean_name,
                            profile_json,
                            timestamp,
                            int(organization_id),
                            int(company_id),
                        ),
                    )

                    row = conn.execute(
                        """SELECT *
                           FROM company_workspaces
                           WHERE organization_id=? AND id=?""",
                        (
                            int(organization_id),
                            int(company_id),
                        ),
                    ).fetchone()

            return self._workspace(row, None)

        except (
            CompanyAuthorizationError,
            CompanyNotFoundError,
            CompanyRepositoryError,
        ):
            raise
        except sqlite3.IntegrityError:
            raise CompanyRepositoryError(
                "Company with this name already exists in the organization."
            ) from None
        except sqlite3.Error:
            raise CompanyRepositoryError(
                "Company storage is unavailable."
            ) from None

    def delete_for_organization(
        self,
        *,
        account_id: int,
        organization_id: int,
        company_id: int,
    ) -> None:
        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute("BEGIN IMMEDIATE")

                    self._require_org_role(
                        conn,
                        account_id,
                        organization_id,
                        {"owner", "admin"},
                    )

                    organization_owner_id = self._organization_owner_id(
                        organization_id
                    )
                    active_id = self._active_id(
                        conn,
                        organization_owner_id,
                    )

                    cursor = conn.execute(
                        """DELETE FROM company_workspaces
                           WHERE organization_id=? AND id=?""",
                        (
                            int(organization_id),
                            int(company_id),
                        ),
                    )

                    if cursor.rowcount != 1:
                        raise CompanyNotFoundError(
                            "Company not found."
                        )

                    if active_id == int(company_id):
                        replacement = conn.execute(
                            """SELECT id
                               FROM company_workspaces
                               WHERE organization_id=?
                               ORDER BY updated_at DESC, id DESC
                               LIMIT 1""",
                            (int(organization_id),),
                        ).fetchone()

                        if replacement is not None:
                            conn.execute(
                                """INSERT INTO company_active(
                                    owner_user_id,
                                    company_id,
                                    updated_at
                                ) VALUES (?, ?, ?)
                                ON CONFLICT(owner_user_id) DO UPDATE SET
                                    company_id=excluded.company_id,
                                    updated_at=excluded.updated_at""",
                                (
                                    organization_owner_id,
                                    int(replacement["id"]),
                                    self._now(),
                                ),
                            )
                        else:
                            conn.execute(
                                """DELETE FROM company_active
                                   WHERE owner_user_id=?""",
                                (organization_owner_id,),
                            )

        except (
            CompanyAuthorizationError,
            CompanyNotFoundError,
        ):
            raise
        except sqlite3.Error:
            raise CompanyRepositoryError(
                "Company storage is unavailable."
            ) from None
