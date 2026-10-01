"""SQLite persistence for processed tenders.

The MVP stores metadata and structured results only: no PDF bytes and no extracted full text.
Connections are short-lived so repository methods can safely be called via asyncio.to_thread().
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.models.tender import TenderAnalysis
from app.scoring.models import ScoringResult

SCHEMA_VERSION = 1


class DatabaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredTender:
    id: int
    owner_user_id: int
    chat_id: int
    pdf_sha256: str
    source_filename: str
    pages: int | None
    characters: int
    analysis: TenderAnalysis
    scoring: ScoringResult | None
    analysis_truncated: bool
    created_at: str
    updated_at: str


class TenderRepository:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as conn:
                with conn:
                    conn.executescript(
                        """
                        CREATE TABLE IF NOT EXISTS schema_meta (
                            key TEXT PRIMARY KEY,
                            value TEXT NOT NULL
                        );

                        CREATE TABLE IF NOT EXISTS tenders (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            owner_user_id INTEGER NOT NULL,
                            chat_id INTEGER NOT NULL,
                            pdf_sha256 TEXT NOT NULL,
                            source_filename TEXT NOT NULL,
                            pages INTEGER,
                            characters INTEGER NOT NULL,
                            analysis_json TEXT NOT NULL,
                            scoring_json TEXT,
                            analysis_truncated INTEGER NOT NULL DEFAULT 0 CHECK (analysis_truncated IN (0,1)),
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            UNIQUE(owner_user_id, pdf_sha256)
                        );

                        CREATE INDEX IF NOT EXISTS idx_tenders_owner_created
                        ON tenders(owner_user_id, created_at DESC);
                        """
                    )
                    current = conn.execute(
                        "SELECT value FROM schema_meta WHERE key='schema_version'"
                    ).fetchone()
                    if current is None:
                        conn.execute(
                            "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?)",
                            (str(SCHEMA_VERSION),),
                        )
                    elif int(current["value"]) != SCHEMA_VERSION:
                        raise DatabaseError("Неподдерживаемая версия локальной базы данных.")
        except (OSError, sqlite3.Error, ValueError) as error:
            if isinstance(error, DatabaseError):
                raise
            raise DatabaseError("Не удалось инициализировать локальную базу данных.") from None

    @staticmethod
    def _deserialize(row: sqlite3.Row) -> StoredTender:
        try:
            analysis = TenderAnalysis.model_validate_json(row["analysis_json"])
            scoring = (
                ScoringResult.model_validate_json(row["scoring_json"])
                if row["scoring_json"]
                else None
            )
            return StoredTender(
                id=row["id"],
                owner_user_id=row["owner_user_id"],
                chat_id=row["chat_id"],
                pdf_sha256=row["pdf_sha256"],
                source_filename=row["source_filename"],
                pages=row["pages"],
                characters=row["characters"],
                analysis=analysis,
                scoring=scoring,
                analysis_truncated=bool(row["analysis_truncated"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        except Exception:
            raise DatabaseError("Сохранённая запись тендера повреждена.") from None

    def find_by_hash(self, owner_user_id: int, pdf_sha256: str) -> StoredTender | None:
        try:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    "SELECT * FROM tenders WHERE owner_user_id=? AND pdf_sha256=?",
                    (owner_user_id, pdf_sha256),
                ).fetchone()
            return self._deserialize(row) if row else None
        except sqlite3.Error:
            raise DatabaseError("Не удалось прочитать локальную базу данных.") from None

    def save_success(
        self,
        *,
        owner_user_id: int,
        chat_id: int,
        pdf_sha256: str,
        source_filename: str,
        pages: int | None,
        characters: int,
        analysis: TenderAnalysis,
        scoring: ScoringResult | None,
        analysis_truncated: bool,
    ) -> StoredTender:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        analysis_json = analysis.model_dump_json()
        scoring_json = scoring.model_dump_json() if scoring is not None else None
        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO tenders(
                            owner_user_id, chat_id, pdf_sha256, source_filename, pages,
                            characters, analysis_json, scoring_json, analysis_truncated,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(owner_user_id, pdf_sha256) DO UPDATE SET
                            chat_id=excluded.chat_id,
                            source_filename=excluded.source_filename,
                            pages=excluded.pages,
                            characters=excluded.characters,
                            analysis_json=excluded.analysis_json,
                            scoring_json=excluded.scoring_json,
                            analysis_truncated=excluded.analysis_truncated,
                            updated_at=excluded.updated_at
                        """,
                        (
                            owner_user_id,
                            chat_id,
                            pdf_sha256,
                            source_filename,
                            pages,
                            characters,
                            analysis_json,
                            scoring_json,
                            int(analysis_truncated),
                            now,
                            now,
                        ),
                    )
                    row = conn.execute(
                        "SELECT * FROM tenders WHERE owner_user_id=? AND pdf_sha256=?",
                        (owner_user_id, pdf_sha256),
                    ).fetchone()
            if row is None:
                raise DatabaseError("Не удалось сохранить тендер.")
            return self._deserialize(row)
        except sqlite3.Error:
            raise DatabaseError("Не удалось сохранить тендер в локальную базу данных.") from None

    def list_recent(self, owner_user_id: int, limit: int = 10) -> list[StoredTender]:
        limit = max(1, min(int(limit), 20))
        try:
            with closing(self._connect()) as conn:
                rows = conn.execute(
                    "SELECT * FROM tenders WHERE owner_user_id=? "
                    "ORDER BY updated_at DESC, id DESC LIMIT ?",
                    (owner_user_id, limit),
                ).fetchall()
            return [self._deserialize(row) for row in rows]
        except sqlite3.Error:
            raise DatabaseError("Не удалось получить историю тендеров.") from None
