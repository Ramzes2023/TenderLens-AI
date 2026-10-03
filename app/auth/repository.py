"""SQLite persistence for TenderLens web accounts and sessions."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .models import AuthAccount, AuthSession
from app.organizations.migration import migrate, ensure_personal, backfill_companies

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
                        CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions(expires_at);

                        CREATE TABLE IF NOT EXISTS auth_telegram_links (
                            token_hash TEXT PRIMARY KEY,
                            account_id INTEGER NOT NULL,
                            expires_at TEXT NOT NULL,
                            consumed_at TEXT,
                            created_at TEXT NOT NULL,
                            FOREIGN KEY(account_id) REFERENCES auth_accounts(id) ON DELETE CASCADE
                        );
                        CREATE INDEX IF NOT EXISTS idx_auth_telegram_links_account
                        ON auth_telegram_links(account_id, expires_at);
                    """)
                    conn.execute("BEGIN IMMEDIATE")
                    migrate(conn)
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
                    ensure_personal(conn, account_id)
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
        # Safely claim a legacy Telegram owner namespace for a web account.
        # Lightweight web-owned state is migrated transactionally. PDF history
        # is blocked because Qdrant RAG points are also keyed by owner_user_id
        # and live outside SQLite.
        target_owner = int(owner_user_id)
        if target_owner <= 0:
            raise AuthRepositoryError("owner_user_id must be positive.")
        now = self._now()

        def table_exists(conn: sqlite3.Connection, table: str) -> bool:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            return row is not None

        def owner_count(conn: sqlite3.Connection, table: str, owner: int) -> int:
            if not table_exists(conn, table):
                return 0
            row = conn.execute(
                f"SELECT COUNT(*) AS n FROM {table} WHERE owner_user_id=?",
                (owner,),
            ).fetchone()
            return int(row["n"]) if row else 0

        try:
            with closing(self._connect()) as conn:
                with conn:
                    account = conn.execute(
                        "SELECT * FROM auth_accounts WHERE id=?",
                        (int(account_id),),
                    ).fetchone()
                    if account is None:
                        raise AuthRepositoryError("Account not found.")

                    source_owner = int(account["owner_user_id"])
                    if source_owner == target_owner:
                        return self._account(account)

                    other = conn.execute(
                        "SELECT id FROM auth_accounts WHERE owner_user_id=? AND id<>?",
                        (target_owner, int(account_id)),
                    ).fetchone()
                    if other is not None:
                        raise AuthRepositoryError(
                            "This owner is already linked to another account."
                        )

                    if owner_count(conn, "tenders", source_owner):
                        raise AuthRepositoryError(
                            "Cannot link this account after web PDF history exists. "
                            "Migrate the owner-scoped RAG index first."
                        )

                    known_owner_tables = {
                        "auth_accounts",
                        "company_workspaces",
                        "company_active",
                        "monitor_subscriptions",
                        "monitor_seen",
                        "tenders",
                        "rag_chunks",
                    }
                    tables = conn.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    ).fetchall()
                    for table_row in tables:
                        table = str(table_row["name"])
                        columns = {
                            str(column["name"])
                            for column in conn.execute(f"PRAGMA table_info({table})").fetchall()
                        }
                        if "owner_user_id" not in columns or table in known_owner_tables:
                            continue
                        if owner_count(conn, table, source_owner):
                            raise AuthRepositoryError(
                                f"Cannot link owner safely: unsupported owner-scoped table {table} has data."
                            )

                    if table_exists(conn, "company_workspaces"):
                        duplicate = conn.execute(
                            """
                            SELECT source.name
                            FROM company_workspaces AS source
                            JOIN company_workspaces AS target
                              ON target.owner_user_id=?
                             AND source.owner_user_id=?
                             AND target.name=source.name
                            LIMIT 1
                            """,
                            (target_owner, source_owner),
                        ).fetchone()
                        if duplicate is not None:
                            raise AuthRepositoryError(
                                "Cannot link owners because both sides contain a company "
                                f"named {duplicate['name']!r}."
                            )

                        source_active = None
                        target_active = None
                        if table_exists(conn, "company_active"):
                            source_active = conn.execute(
                                "SELECT company_id FROM company_active WHERE owner_user_id=?",
                                (source_owner,),
                            ).fetchone()
                            target_active = conn.execute(
                                "SELECT company_id FROM company_active WHERE owner_user_id=?",
                                (target_owner,),
                            ).fetchone()

                        conn.execute(
                            "UPDATE company_workspaces SET owner_user_id=? WHERE owner_user_id=?",
                            (target_owner, source_owner),
                        )

                        if table_exists(conn, "company_active"):
                            if source_active is not None and target_active is None:
                                conn.execute(
                                    "UPDATE company_active SET owner_user_id=?, updated_at=? "
                                    "WHERE owner_user_id=?",
                                    (target_owner, now, source_owner),
                                )
                            else:
                                conn.execute(
                                    "DELETE FROM company_active WHERE owner_user_id=?",
                                    (source_owner,),
                                )

                    if table_exists(conn, "monitor_seen"):
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO monitor_seen(
                                owner_user_id, source, external_id, first_seen_at
                            )
                            SELECT ?, source, external_id, first_seen_at
                            FROM monitor_seen
                            WHERE owner_user_id=?
                            """,
                            (target_owner, source_owner),
                        )
                        conn.execute(
                            "DELETE FROM monitor_seen WHERE owner_user_id=?",
                            (source_owner,),
                        )

                    if table_exists(conn, "monitor_subscriptions"):
                        source_subscription = conn.execute(
                            "SELECT * FROM monitor_subscriptions WHERE owner_user_id=?",
                            (source_owner,),
                        ).fetchone()
                        target_subscription = conn.execute(
                            "SELECT * FROM monitor_subscriptions WHERE owner_user_id=?",
                            (target_owner,),
                        ).fetchone()
                        if source_subscription is not None:
                            if target_subscription is None:
                                source_chat = int(source_subscription["chat_id"])
                                chat_id = target_owner if source_chat == source_owner else source_chat
                                conn.execute(
                                    "UPDATE monitor_subscriptions "
                                    "SET owner_user_id=?, chat_id=?, updated_at=? "
                                    "WHERE owner_user_id=?",
                                    (target_owner, chat_id, now, source_owner),
                                )
                            else:
                                conn.execute(
                                    "DELETE FROM monitor_subscriptions WHERE owner_user_id=?",
                                    (source_owner,),
                                )

                    if table_exists(conn, "rag_chunks"):
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO rag_chunks(
                                owner_user_id, pdf_sha256, chunk_index, page_number,
                                chunk_text, vector_blob, created_at
                            )
                            SELECT ?, pdf_sha256, chunk_index, page_number,
                                   chunk_text, vector_blob, created_at
                            FROM rag_chunks
                            WHERE owner_user_id=?
                            """,
                            (target_owner, source_owner),
                        )
                        conn.execute(
                            "DELETE FROM rag_chunks WHERE owner_user_id=?",
                            (source_owner,),
                        )

                    cursor = conn.execute(
                        "UPDATE auth_accounts SET owner_user_id=?, updated_at=? WHERE id=?",
                        (target_owner, now, int(account_id)),
                    )
                    if cursor.rowcount != 1:
                        raise AuthRepositoryError("Account not found.")
                    backfill_companies(conn, target_owner)

                    row = conn.execute(
                        "SELECT * FROM auth_accounts WHERE id=?",
                        (int(account_id),),
                    ).fetchone()

            if row is None:
                raise AuthRepositoryError("Account not found.")
            return self._account(row)
        except sqlite3.IntegrityError:
            raise AuthRepositoryError(
                "Could not link owners because their stored data conflicts."
            ) from None
        except AuthRepositoryError:
            raise
        except sqlite3.Error:
            raise AuthRepositoryError("Could not link account owner.") from None

    def create_telegram_link(self, *, account_id: int, token_hash: str, expires_at: str) -> bool:
        """Create a ticket only while the account is still web-owned.

        Returns False when another process already completed Telegram linking.
        """
        now = self._now()
        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute("BEGIN IMMEDIATE")
                    account = conn.execute(
                        "SELECT owner_user_id FROM auth_accounts WHERE id=?",
                        (int(account_id),),
                    ).fetchone()
                    if account is None:
                        raise AuthRepositoryError("Account not found.")
                    owner_user_id = account["owner_user_id"]
                    if owner_user_id is None:
                        raise AuthRepositoryError("Account owner is unavailable.")
                    if 0 < int(owner_user_id) < WEB_OWNER_OFFSET:
                        return False
                    conn.execute(
                        "DELETE FROM auth_telegram_links WHERE account_id=?",
                        (int(account_id),),
                    )
                    conn.execute(
                        """
                        INSERT INTO auth_telegram_links(
                            token_hash, account_id, expires_at, consumed_at, created_at
                        ) VALUES (?, ?, ?, NULL, ?)
                        """,
                        (token_hash, int(account_id), expires_at, now),
                    )
            return True
        except AuthRepositoryError:
            raise
        except sqlite3.Error:
            raise AuthRepositoryError("Could not create Telegram link ticket.") from None

    def claim_telegram_link(self, *, token_hash: str, now: str) -> int | None:
        """Atomically reserve a valid one-time Telegram link ticket."""
        try:
            with closing(self._connect()) as conn:
                with conn:
                    row = conn.execute(
                        """
                        SELECT account_id
                        FROM auth_telegram_links
                        WHERE token_hash=?
                          AND consumed_at IS NULL
                          AND expires_at>?
                        """,
                        (token_hash, now),
                    ).fetchone()
                    if row is None:
                        return None
                    cursor = conn.execute(
                        """
                        UPDATE auth_telegram_links
                        SET consumed_at=?
                        WHERE token_hash=?
                          AND consumed_at IS NULL
                          AND expires_at>?
                        """,
                        (now, token_hash, now),
                    )
                    if cursor.rowcount != 1:
                        return None
                    return int(row["account_id"])
        except sqlite3.Error:
            raise AuthRepositoryError("Could not claim Telegram link ticket.") from None

    def release_telegram_link(self, *, token_hash: str, consumed_at: str) -> None:
        """Release this process' reservation when owner migration fails."""
        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute(
                        """
                        UPDATE auth_telegram_links
                        SET consumed_at=NULL
                        WHERE token_hash=? AND consumed_at=?
                        """,
                        (token_hash, consumed_at),
                    )
        except sqlite3.Error:
            raise AuthRepositoryError("Could not release Telegram link ticket.") from None

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
