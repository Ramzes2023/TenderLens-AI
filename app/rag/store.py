"""Persistent local SQLite vector store for Phase 8.

Vectors are stored as float32 BLOBs. Search is exact cosine/dot-product over the
user/document slice. This keeps the MVP dependency-free and makes the storage
backend replaceable by Qdrant later.
"""
from __future__ import annotations

import sqlite3
from array import array
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .models import DocumentChunk, RetrievedChunk


class RagStoreError(RuntimeError):
    pass


class SQLiteVectorStore:
    def __init__(self, path: Path, dimensions: int):
        self.path = Path(path)
        self.dimensions = dimensions

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
                        CREATE TABLE IF NOT EXISTS rag_chunks (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            owner_user_id INTEGER NOT NULL,
                            pdf_sha256 TEXT NOT NULL,
                            chunk_index INTEGER NOT NULL,
                            page_number INTEGER NOT NULL,
                            chunk_text TEXT NOT NULL,
                            vector_blob BLOB NOT NULL,
                            created_at TEXT NOT NULL,
                            UNIQUE(owner_user_id, pdf_sha256, chunk_index)
                        );
                        CREATE INDEX IF NOT EXISTS idx_rag_document
                        ON rag_chunks(owner_user_id, pdf_sha256, chunk_index);
                        """
                    )
        except (OSError, sqlite3.Error):
            raise RagStoreError("Не удалось инициализировать локальный RAG-индекс.") from None

    def _encode(self, vector: tuple[float, ...]) -> bytes:
        if len(vector) != self.dimensions:
            raise RagStoreError("Размерность вектора не соответствует RAG-конфигурации.")
        values = array("f", vector)
        return values.tobytes()

    def _decode(self, blob: bytes) -> tuple[float, ...]:
        values = array("f")
        values.frombytes(blob)
        if len(values) != self.dimensions:
            raise RagStoreError("RAG-индекс содержит вектор неверной размерности.")
        return tuple(values)

    def has_document(self, owner_user_id: int, pdf_sha256: str) -> bool:
        try:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    "SELECT 1 FROM rag_chunks WHERE owner_user_id=? AND pdf_sha256=? LIMIT 1",
                    (owner_user_id, pdf_sha256),
                ).fetchone()
            return row is not None
        except sqlite3.Error:
            raise RagStoreError("Не удалось прочитать RAG-индекс.") from None

    def replace_document(self, owner_user_id: int, pdf_sha256: str,
                         items: list[tuple[DocumentChunk, tuple[float, ...]]]) -> int:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute(
                        "DELETE FROM rag_chunks WHERE owner_user_id=? AND pdf_sha256=?",
                        (owner_user_id, pdf_sha256),
                    )
                    conn.executemany(
                        """
                        INSERT INTO rag_chunks(
                            owner_user_id, pdf_sha256, chunk_index, page_number,
                            chunk_text, vector_blob, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            (owner_user_id, pdf_sha256, chunk.chunk_index, chunk.page_number,
                             chunk.text, self._encode(vector), now)
                            for chunk, vector in items
                        ],
                    )
            return len(items)
        except sqlite3.Error:
            raise RagStoreError("Не удалось сохранить RAG-индекс документа.") from None

    def search(self, owner_user_id: int, pdf_sha256: str, query_vector: tuple[float, ...],
               limit: int = 5) -> list[RetrievedChunk]:
        if len(query_vector) != self.dimensions:
            raise RagStoreError("Размерность запроса не соответствует RAG-конфигурации.")
        limit = max(1, min(int(limit), 10))
        try:
            with closing(self._connect()) as conn:
                rows = conn.execute(
                    "SELECT chunk_index, page_number, chunk_text, vector_blob "
                    "FROM rag_chunks WHERE owner_user_id=? AND pdf_sha256=?",
                    (owner_user_id, pdf_sha256),
                ).fetchall()
        except sqlite3.Error:
            raise RagStoreError("Не удалось выполнить поиск по RAG-индексу.") from None
        scored: list[RetrievedChunk] = []
        for row in rows:
            vector = self._decode(row["vector_blob"])
            score = sum(a * b for a, b in zip(query_vector, vector))
            scored.append(RetrievedChunk(
                chunk_index=row["chunk_index"], page_number=row["page_number"],
                text=row["chunk_text"], score=float(score),
            ))
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:limit]
