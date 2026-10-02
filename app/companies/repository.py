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


class CompanyRepositoryError(RuntimeError):
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
        except (OSError, sqlite3.Error):
            raise CompanyRepositoryError("Не удалось инициализировать company workspace storage.") from None

    @staticmethod
    def _workspace(row: sqlite3.Row, active_id: int | None = None) -> CompanyWorkspace:
        try:
            profile = CompanyProfile.model_validate_json(row["profile_json"])
            return CompanyWorkspace(
                id=int(row["id"]),
                owner_user_id=int(row["owner_user_id"]),
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

    def _active_id(self, conn: sqlite3.Connection, owner_user_id: int) -> int | None:
        row = conn.execute(
            "SELECT company_id FROM company_active WHERE owner_user_id=?",
            (int(owner_user_id),),
        ).fetchone()
        return int(row["company_id"]) if row else None

    def create(self, owner_user_id: int, name: str, profile: CompanyProfile,
               *, make_active: bool = True) -> CompanyWorkspace:
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
