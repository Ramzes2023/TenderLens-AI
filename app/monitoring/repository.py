"""SQLite state for source deduplication and Telegram monitoring subscriptions."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class MonitoringRepositoryError(RuntimeError):
    pass


class MonitoringAuthorizationError(MonitoringRepositoryError):
    pass


@dataclass(frozen=True)
class Subscription:
    owner_user_id: int
    chat_id: int
    enabled: bool
    created_at: str
    updated_at: str


class MonitoringRepository:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as conn:
                with conn:
                    conn.executescript(
                        """
                        CREATE TABLE IF NOT EXISTS monitor_subscriptions (
                            owner_user_id INTEGER PRIMARY KEY,
                            chat_id INTEGER NOT NULL,
                            enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        );

                        CREATE TABLE IF NOT EXISTS monitor_seen (
                            owner_user_id INTEGER NOT NULL,
                            source TEXT NOT NULL,
                            external_id TEXT NOT NULL,
                            first_seen_at TEXT NOT NULL,
                            PRIMARY KEY(owner_user_id, source, external_id)
                        );

                        CREATE INDEX IF NOT EXISTS idx_monitor_subscriptions_enabled
                        ON monitor_subscriptions(enabled, updated_at DESC);
                        """
                    )
        except (OSError, sqlite3.Error):
            raise MonitoringRepositoryError("Не удалось инициализировать monitoring-таблицы SQLite.") from None

    @staticmethod
    def _subscription(row: sqlite3.Row) -> Subscription:
        return Subscription(
            owner_user_id=row["owner_user_id"], chat_id=row["chat_id"], enabled=bool(row["enabled"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def set_subscription(self, owner_user_id: int, chat_id: int, enabled: bool) -> Subscription:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO monitor_subscriptions(owner_user_id, chat_id, enabled, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(owner_user_id) DO UPDATE SET
                            chat_id=excluded.chat_id, enabled=excluded.enabled, updated_at=excluded.updated_at
                        """,
                        (owner_user_id, chat_id, int(enabled), now, now),
                    )
                    row = conn.execute(
                        "SELECT * FROM monitor_subscriptions WHERE owner_user_id=?", (owner_user_id,)
                    ).fetchone()
            if row is None:
                raise MonitoringRepositoryError("Не удалось сохранить подписку.")
            return self._subscription(row)
        except sqlite3.Error:
            raise MonitoringRepositoryError("Не удалось сохранить подписку monitoring.") from None

    def get_subscription(self, owner_user_id: int) -> Subscription | None:
        try:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    "SELECT * FROM monitor_subscriptions WHERE owner_user_id=?", (owner_user_id,)
                ).fetchone()
            return self._subscription(row) if row else None
        except sqlite3.Error:
            raise MonitoringRepositoryError("Не удалось прочитать подписку monitoring.") from None

    def list_active(self) -> list[Subscription]:
        try:
            with closing(self._connect()) as conn:
                rows = conn.execute(
                    "SELECT * FROM monitor_subscriptions WHERE enabled=1 ORDER BY updated_at ASC"
                ).fetchall()
            return [self._subscription(row) for row in rows]
        except sqlite3.Error:
            raise MonitoringRepositoryError("Не удалось прочитать активные monitoring-подписки.") from None

    def seen(self, owner_user_id: int, source: str, external_id: str) -> bool:
        try:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    "SELECT 1 FROM monitor_seen WHERE owner_user_id=? AND source=? AND external_id=?",
                    (owner_user_id, source, external_id),
                ).fetchone()
            return row is not None
        except sqlite3.Error:
            raise MonitoringRepositoryError("Не удалось проверить дедупликацию monitoring.") from None

    def mark_seen_for_organization(
        self,
        *,
        account_id: int,
        organization_id: int,
        owner_user_id: int,
        source: str,
        external_id: str,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute("BEGIN IMMEDIATE")

                    membership = conn.execute(
                        """SELECT role
                           FROM organization_members
                           WHERE organization_id=? AND account_id=?""",
                        (
                            int(organization_id),
                            int(account_id),
                        ),
                    ).fetchone()

                    if membership is None or membership["role"] not in {
                        "owner",
                        "admin",
                        "member",
                    }:
                        raise MonitoringAuthorizationError(
                            "Organization monitoring access denied."
                        )

                    cursor = conn.execute(
                        """INSERT OR IGNORE INTO monitor_seen(
                            owner_user_id,
                            source,
                            external_id,
                            first_seen_at
                        ) VALUES (?, ?, ?, ?)""",
                        (
                            int(owner_user_id),
                            source,
                            external_id,
                            now,
                        ),
                    )

            return cursor.rowcount > 0

        except MonitoringAuthorizationError:
            raise
        except sqlite3.Error:
            raise MonitoringRepositoryError(
                "Could not save organization monitoring dedup state."
            ) from None

    def mark_seen(self, owner_user_id: int, source: str, external_id: str) -> bool:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            with closing(self._connect()) as conn:
                with conn:
                    cursor = conn.execute(
                        "INSERT OR IGNORE INTO monitor_seen(owner_user_id, source, external_id, first_seen_at) "
                        "VALUES (?, ?, ?, ?)",
                        (owner_user_id, source, external_id, now),
                    )
            return cursor.rowcount > 0
        except sqlite3.Error:
            raise MonitoringRepositoryError("Не удалось сохранить monitoring dedup state.") from None
