"""Transactional persistence for VALYQON AI web accounts and sessions."""

from __future__ import annotations

import sqlite3
from app.database.backend import database_for, StorageError, StorageIntegrityError, table_exists, table_columns, table_names, identifier
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .models import AuthAccount, AuthSession
from app.organizations.migration import ensure_personal, backfill_companies

WEB_OWNER_OFFSET = 4_000_000_000_000


class AuthRepositoryError(RuntimeError):
    pass


class AuthRepository:
    def __init__(self, path):
        self.database = database_for(path)
        self.path = self.database.settings.path

    def _connect(self):
        return self.database.connect()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _account(row: sqlite3.Row) -> AuthAccount:
        return AuthAccount(
            id=int(row["id"]),
            email=str(row["email"]),
            owner_user_id=int(row["owner_user_id"]),
            is_active=bool(row["is_active"]),
            email_verified=bool(row["email_verified"]),
            email_verified_at=(
                str(row["email_verified_at"])
                if row["email_verified_at"] is not None
                else None
            ),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _session(row: sqlite3.Row) -> AuthSession:
        return AuthSession(token_hash=str(row["token_hash"]), account_id=int(row["account_id"]), expires_at=str(row["expires_at"]), created_at=str(row["created_at"]), last_seen_at=str(row["last_seen_at"]))

    def initialize(self) -> None:
        try:
            self.database.migrate("auth")
        except (OSError, sqlite3.Error, StorageError, ValueError):
            raise AuthRepositoryError("Could not initialize auth storage.") from None

    def create_account(self, email: str, password_hash: str) -> AuthAccount:
        now = self._now()
        try:
            with closing(self._connect()) as conn:
                with conn:
                    cursor = conn.execute(
                        """
                        INSERT INTO auth_accounts(
                            email,
                            password_hash,
                            owner_user_id,
                            is_active,
                            email_verified,
                            email_verified_at,
                            created_at,
                            updated_at
                        )
                        VALUES (?, ?, NULL, 1, 0, NULL, ?, ?)
                        """,
                        (
                            email,
                            password_hash,
                            now,
                            now,
                        ),
                    )
                    account_id = int(cursor.lastrowid)
                    owner_user_id = WEB_OWNER_OFFSET + account_id
                    conn.execute("UPDATE auth_accounts SET owner_user_id=? WHERE id=?", (owner_user_id, account_id))
                    ensure_personal(conn, account_id)
                    row = conn.execute("SELECT * FROM auth_accounts WHERE id=?", (account_id,)).fetchone()
            if row is None:
                raise AuthRepositoryError("Could not create account.")
            return self._account(row)
        except (sqlite3.IntegrityError, StorageIntegrityError):
            raise AuthRepositoryError("An account with this email already exists.") from None
        except (sqlite3.Error, StorageError):
            raise AuthRepositoryError("Could not create account.") from None

    def find_account_by_email(self, email: str):
        try:
            with closing(self._connect()) as conn:
                row = conn.execute("SELECT * FROM auth_accounts WHERE lower(email)=lower(?)", (email,)).fetchone()
            if row is None:
                return None
            return self._account(row), str(row["password_hash"])
        except (sqlite3.Error, StorageError):
            raise AuthRepositoryError("Could not read account.") from None

    def find_account_by_id(self, account_id: int):
        try:
            with closing(self._connect()) as conn:
                row = conn.execute("SELECT * FROM auth_accounts WHERE id=?", (int(account_id),)).fetchone()
            return self._account(row) if row else None
        except (sqlite3.Error, StorageError):
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

        def owner_count(conn: sqlite3.Connection, table: str, owner: int) -> int:
            if not table_exists(conn, table):
                return 0
            row = conn.execute(
                f"SELECT COUNT(*) AS n FROM {identifier(table)} WHERE owner_user_id=?",
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
                    for table in table_names(conn):
                        columns = set(table_columns(conn, table))
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
                            INSERT INTO monitor_seen(
                                owner_user_id, source, external_id, first_seen_at
                            )
                            SELECT ?, source, external_id, first_seen_at
                            FROM monitor_seen
                            WHERE owner_user_id=? ON CONFLICT DO NOTHING""",
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
                            INSERT INTO rag_chunks(
                                owner_user_id, pdf_sha256, chunk_index, page_number,
                                chunk_text, vector_blob, created_at
                            )
                            SELECT ?, pdf_sha256, chunk_index, page_number,
                                   chunk_text, vector_blob, created_at
                            FROM rag_chunks
                            WHERE owner_user_id=? ON CONFLICT DO NOTHING""",
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
        except (sqlite3.IntegrityError, StorageIntegrityError):
            raise AuthRepositoryError(
                "Could not link owners because their stored data conflicts."
            ) from None
        except AuthRepositoryError:
            raise
        except (sqlite3.Error, StorageError):
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
        except (sqlite3.Error, StorageError):
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
        except (sqlite3.Error, StorageError):
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
        except (sqlite3.Error, StorageError):
            raise AuthRepositoryError("Could not release Telegram link ticket.") from None

    def create_email_verification(
        self,
        *,
        account_id: int,
        token_hash: str,
        expires_at: str,
        cooldown_after: str | None = None,
    ) -> bool:
        """Store one active verification token without storing its raw value.

        Returns False when the account is still inside the resend cooldown.
        """
        now = self._now()

        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute(
                        "BEGIN IMMEDIATE"
                    )

                    account = conn.execute(
                        """
                        SELECT email_verified
                        FROM auth_accounts
                        WHERE id=?
                        """,
                        (
                            int(account_id),
                        ),
                    ).fetchone()

                    if account is None:
                        raise AuthRepositoryError(
                            "Account not found."
                        )

                    if bool(
                        account["email_verified"]
                    ):
                        raise AuthRepositoryError(
                            "Email is already verified."
                        )

                    conn.execute(
                        """
                        DELETE FROM auth_email_verifications
                        WHERE expires_at<=?
                        """,
                        (
                            now,
                        ),
                    )

                    if cooldown_after is not None:
                        latest = conn.execute(
                            """
                            SELECT created_at
                            FROM auth_email_verifications
                            WHERE account_id=?
                            ORDER BY created_at DESC
                            LIMIT 1
                            """,
                            (
                                int(account_id),
                            ),
                        ).fetchone()

                        if (
                            latest is not None
                            and str(
                                latest["created_at"]
                            ) > cooldown_after
                        ):
                            return False

                    # Only one usable ticket per account.
                    conn.execute(
                        """
                        DELETE FROM auth_email_verifications
                        WHERE account_id=?
                          AND consumed_at IS NULL
                        """,
                        (
                            int(account_id),
                        ),
                    )

                    conn.execute(
                        """
                        INSERT INTO auth_email_verifications(
                            token_hash,
                            account_id,
                            expires_at,
                            consumed_at,
                            created_at
                        )
                        VALUES (?, ?, ?, NULL, ?)
                        """,
                        (
                            token_hash,
                            int(account_id),
                            expires_at,
                            now,
                        ),
                    )

            return True

        except AuthRepositoryError:
            raise

        except (sqlite3.Error, StorageError):
            raise AuthRepositoryError(
                "Could not create email verification ticket."
            ) from None

    def consume_email_verification(
        self,
        *,
        token_hash: str,
        now: str,
    ) -> AuthAccount | None:
        """Atomically consume a valid token and verify its account."""

        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute(
                        "BEGIN IMMEDIATE"
                    )

                    ticket = conn.execute(
                        """
                        SELECT account_id
                        FROM auth_email_verifications
                        WHERE token_hash=?
                          AND consumed_at IS NULL
                          AND expires_at>?
                        """,
                        (
                            token_hash,
                            now,
                        ),
                    ).fetchone()

                    if ticket is None:
                        return None

                    account_id = int(
                        ticket["account_id"]
                    )

                    claimed = conn.execute(
                        """
                        UPDATE auth_email_verifications
                        SET consumed_at=?
                        WHERE token_hash=?
                          AND consumed_at IS NULL
                          AND expires_at>?
                        """,
                        (
                            now,
                            token_hash,
                            now,
                        ),
                    )

                    if claimed.rowcount != 1:
                        return None

                    conn.execute(
                        """
                        UPDATE auth_accounts
                        SET
                            email_verified=1,
                            email_verified_at=
                                COALESCE(
                                    email_verified_at,
                                    ?
                                ),
                            updated_at=?
                        WHERE id=?
                        """,
                        (
                            now,
                            now,
                            account_id,
                        ),
                    )

                    row = conn.execute(
                        """
                        SELECT *
                        FROM auth_accounts
                        WHERE id=?
                        """,
                        (
                            account_id,
                        ),
                    ).fetchone()

            return (
                self._account(row)
                if row is not None
                else None
            )

        except (sqlite3.Error, StorageError):
            raise AuthRepositoryError(
                "Could not verify email."
            ) from None

    def delete_email_verification(
        self,
        *,
        token_hash: str,
    ) -> None:
        try:
            with closing(
                self._connect()
            ) as conn:
                with conn:
                    conn.execute(
                        """
                        DELETE FROM auth_email_verifications
                        WHERE token_hash=?
                        """,
                        (
                            token_hash,
                        ),
                    )

        except (sqlite3.Error, StorageError):
            raise AuthRepositoryError(
                "Could not revoke email verification ticket."
            ) from None

    def delete_expired_email_verifications(
        self,
        now: str,
    ) -> int:
        try:
            with closing(self._connect()) as conn:
                with conn:
                    cursor = conn.execute(
                        """
                        DELETE FROM auth_email_verifications
                        WHERE expires_at<=?
                        """,
                        (
                            now,
                        ),
                    )

            return int(cursor.rowcount)

        except (sqlite3.Error, StorageError):
            raise AuthRepositoryError(
                "Could not clean expired email verification tickets."
            ) from None

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
        except (sqlite3.Error, StorageError):
            raise AuthRepositoryError("Could not create session.") from None

    def find_account_for_session(self, token_hash: str, now: str):
        try:
            with closing(self._connect()) as conn:
                row = conn.execute("""SELECT a.* FROM auth_sessions s JOIN auth_accounts a ON a.id=s.account_id WHERE s.token_hash=? AND s.expires_at>? AND a.is_active=1""", (token_hash, now)).fetchone()
            return self._account(row) if row else None
        except (sqlite3.Error, StorageError):
            raise AuthRepositoryError("Could not read session.") from None

    def touch_session(self, token_hash: str) -> None:
        now = self._now()
        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute("UPDATE auth_sessions SET last_seen_at=? WHERE token_hash=?", (now, token_hash))
        except (sqlite3.Error, StorageError):
            raise AuthRepositoryError("Could not update session.") from None

    def delete_session(self, token_hash: str) -> None:
        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute("DELETE FROM auth_sessions WHERE token_hash=?", (token_hash,))
        except (sqlite3.Error, StorageError):
            raise AuthRepositoryError("Could not delete session.") from None

    def delete_expired_sessions(self, now: str) -> int:
        try:
            with closing(self._connect()) as conn:
                with conn:
                    cursor = conn.execute("DELETE FROM auth_sessions WHERE expires_at<=?", (now,))
            return int(cursor.rowcount)
        except (sqlite3.Error, StorageError):
            raise AuthRepositoryError("Could not clean expired sessions.") from None

    def create_password_reset(
        self, *, account_id: int, token_hash: str, expires_at: str,
        cooldown_after: str | None = None,
    ) -> bool:
        """Serialize cooldown checks and rotation; persist only a token hash."""
        now = self._now()
        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute("BEGIN IMMEDIATE")
                    account = conn.execute(
                        "SELECT id FROM auth_accounts WHERE id=? AND is_active=1",
                        (account_id,),
                    ).fetchone()
                    if account is None:
                        return False
                    if cooldown_after is not None:
                        recent = conn.execute(
                            "SELECT 1 FROM auth_password_resets WHERE account_id=? AND created_at>? LIMIT 1",
                            (account_id, cooldown_after),
                        ).fetchone()
                        if recent is not None:
                            return False
                    conn.execute(
                        "UPDATE auth_password_resets SET consumed_at=? WHERE account_id=? AND consumed_at IS NULL",
                        (now, account_id),
                    )
                    conn.execute(
                        "INSERT INTO auth_password_resets VALUES (?, ?, ?, NULL, ?)",
                        (token_hash, account_id, expires_at, now),
                    )
            return True
        except (sqlite3.Error, StorageError):
            raise AuthRepositoryError("Could not create password reset ticket.") from None

    def consume_password_reset(
        self, *, token_hash: str, password_hash: str, now: str,
    ) -> AuthAccount | None:
        """Change the password and revoke every session in one transaction."""
        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute("BEGIN IMMEDIATE")
                    ticket = conn.execute(
                        """SELECT r.account_id FROM auth_password_resets r
                        JOIN auth_accounts a ON a.id=r.account_id
                        WHERE r.token_hash=? AND r.consumed_at IS NULL
                        AND r.expires_at>? AND a.is_active=1""",
                        (token_hash, now),
                    ).fetchone()
                    if ticket is None:
                        return None
                    claimed = conn.execute(
                        """UPDATE auth_password_resets SET consumed_at=?
                        WHERE token_hash=? AND consumed_at IS NULL AND expires_at>?""",
                        (now, token_hash, now),
                    )
                    if claimed.rowcount != 1:
                        return None
                    account_id = int(ticket["account_id"])
                    conn.execute(
                        "UPDATE auth_accounts SET password_hash=?, updated_at=? WHERE id=?",
                        (password_hash, now, account_id),
                    )
                    conn.execute("DELETE FROM auth_sessions WHERE account_id=?", (account_id,))
                    conn.execute(
                        "UPDATE auth_password_resets SET consumed_at=? WHERE account_id=? AND consumed_at IS NULL",
                        (now, account_id),
                    )
                    row = conn.execute("SELECT * FROM auth_accounts WHERE id=?", (account_id,)).fetchone()
            return self._account(row)
        except (sqlite3.Error, StorageError):
            raise AuthRepositoryError("Could not reset password.") from None

    def delete_password_reset(self, *, token_hash: str) -> None:
        # Keep the request timestamp so failed delivery cannot bypass cooldown.
        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute(
                        "UPDATE auth_password_resets SET consumed_at=? WHERE token_hash=? AND consumed_at IS NULL",
                        (self._now(), token_hash),
                    )
        except (sqlite3.Error, StorageError):
            raise AuthRepositoryError("Could not revoke password reset ticket.") from None
