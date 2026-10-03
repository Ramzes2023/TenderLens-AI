"""SQLite persistence for TenderLens web accounts and sessions."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .models import AuthAccount, AuthSession

WEB_OWNER_OFFSET = 4_000_000_000_000


class AuthRepositoryError(RuntimeError):
    pass


class AuthRepository:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _account(row: sqlite3.Row) -> AuthAccount:
        return AuthAccount(id=int(row["id"]), email=str(row["email"]), owner_user_id=int(row["owner_user_id"]), is_active=bool(row["is_active"]), created_at=str(row["created_at"]), updated_at=str(row["updated_at"]))

    @staticmethod
    def _session(row: sqlite3.Row) -> AuthSession:
        return AuthSession(token_hash=str(row["token_hash"]), account_id=int(row["account_id"]), expires_at=str(row["expires_at"]), created_at=str(row["created_at"]), last_seen_at=str(row["last_seen_at"]))

    def initialize(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as conn:
                with conn:
                    conn.executescript("""
                        CREATE TABLE IF NOT EXISTS auth_accounts (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                            password_hash TEXT NOT NULL,
                            owner_user_id INTEGER UNIQUE,
                            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_auth_accounts_owner ON auth_accounts(owner_user_id);
                        CREATE TABLE IF NOT EXISTS auth_sessions (
                            token_hash TEXT PRIMARY KEY,
                            account_id INTEGER NOT NULL,
                            expires_at TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            last_seen_at TEXT NOT NULL,
                            FOREIGN KEY(account_id) REFERENCES auth_accounts(id) ON DELETE CASCADE
                        );
                        CREATE INDEX IF NOT EXISTS idx_auth_sessions_account ON auth_sessions(account_id, expires_at);
                    """)
        except (OSError, sqlite3.Error):
            raise AuthRepositoryError("Could not initialize authentication storage.") from None

    def create_account(self, email: str, password_hash: str) -> AuthAccount:
        now = self._now()
        try:
            with closing(self._connect()) as conn:
                with conn:
                    cursor = conn.execute("INSERT INTO auth_accounts(email,password_hash,owner_user_id,is_active,created_at,updated_at) VALUES (?, ?, NULL, 1, ?, ?)", (email, password_hash, now, now))
                    account_id = int(cursor.lastrowid)
                    owner_user_id = WEB_OWNER_OFFSET + account_id
                    conn.execute("UPDATE auth_accounts SET owner_user_id=? WHERE id=?", (owner_user_id, account_id))
                    row = conn.execute("SELECT * FROM auth_accounts WHERE id=?", (account_id,)).fetchone()
            if row is None:
                raise AuthRepositoryError("Could not create account.")
            return self._account(row)
        except sqlite3.IntegrityError:
            raise AuthRepositoryError("An account with this email already exists.") from None
        except sqlite3.Error:
            raise AuthRepositoryError("Could not create account.") from None

    def find_account_by_email(self, email: str):
        try:
            with closing(self._connect()) as conn:
                row = conn.execute("SELECT * FROM auth_accounts WHERE email=?", (email,)).fetchone()
            if row is None:
                return None
            return self._account(row), str(row["password_hash"])
        except sqlite3.Error:
            raise AuthRepositoryError("Could not read account.") from None

    def find_account_by_id(self, account_id: int):
        try:
            with closing(self._connect()) as conn:
                row = conn.execute("SELECT * FROM auth_accounts WHERE id=?", (int(account_id),)).fetchone()
            return self._account(row) if row else None
        except sqlite3.Error:
            raise AuthRepositoryError("Could not read account.") from None

    def link_owner(self, account_id: int, owner_user_id: int) -> AuthAccount:
        if int(owner_user_id) <= 0:
            raise AuthRepositoryError("owner_user_id must be positive.")
        now = self._now()
        try:
            with closing(self._connect()) as conn:
                with conn:
                    cursor = conn.execute("UPDATE auth_accounts SET owner_user_id=?, updated_at=? WHERE id=?", (int(owner_user_id), now, int(account_id)))
                    if cursor.rowcount != 1:
                        raise AuthRepositoryError("Account not found.")
                    row = conn.execute("SELECT * FROM auth_accounts WHERE id=?", (int(account_id),)).fetchone()
            if row is None:
                raise AuthRepositoryError("Account not found.")
            return self._account(row)
        except sqlite3.IntegrityError:
            raise AuthRepositoryError("This owner is already linked to another account.") from None
        except AuthRepositoryError:
            raise
        except sqlite3.Error:
            raise AuthRepositoryError("Could not link account owner.") from None

    def create_session(self, *, account_id: int, token_hash: str, expires_at: str) -> AuthSession:
        now = self._now()
        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute("INSERT INTO auth_sessions(token_hash,account_id,expires_at,created_at,last_seen_at) VALUES (?, ?, ?, ?, ?)", (token_hash, int(account_id), expires_at, now, now))
                    row = conn.execute("SELECT * FROM auth_sessions WHERE token_hash=?", (token_hash,)).fetchone()
            if row is None:
                raise AuthRepositoryError("Could not create session.")
            return self._session(row)
        except sqlite3.Error:
            raise AuthRepositoryError("Could not create session.") from None

    def find_account_for_session(self, token_hash: str, now: str):
        try:
            with closing(self._connect()) as conn:
                row = conn.execute("""SELECT a.* FROM auth_sessions s JOIN auth_accounts a ON a.id=s.account_id WHERE s.token_hash=? AND s.expires_at>? AND a.is_active=1""", (token_hash, now)).fetchone()
            return self._account(row) if row else None
        except sqlite3.Error:
            raise AuthRepositoryError("Could not read session.") from None

    def touch_session(self, token_hash: str) -> None:
        now = self._now()
        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute("UPDATE auth_sessions SET last_seen_at=? WHERE token_hash=?", (now, token_hash))
        except sqlite3.Error:
            raise AuthRepositoryError("Could not update session.") from None

    def delete_session(self, token_hash: str) -> None:
        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute("DELETE FROM auth_sessions WHERE token_hash=?", (token_hash,))
        except sqlite3.Error:
            raise AuthRepositoryError("Could not delete session.") from None

    def delete_expired_sessions(self, now: str) -> int:
        try:
            with closing(self._connect()) as conn:
                with conn:
                    cursor = conn.execute("DELETE FROM auth_sessions WHERE expires_at<=?", (now,))
            return int(cursor.rowcount)
        except sqlite3.Error:
            raise AuthRepositoryError("Could not clean expired sessions.") from None
