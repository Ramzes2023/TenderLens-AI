"""Qdrant-backed vector storage for Phase 8.1.

The default uses qdrant-client local mode, so no Docker/server is required for
this prototype. The same payload/filter contract can later be pointed at a real
Qdrant service with minimal changes.
"""
from __future__ import annotations

import uuid
import hashlib
import json
import os
import time
import threading
import weakref
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    from qdrant_client import QdrantClient, models
except ImportError:  # clearer startup error before requirements are installed
    QdrantClient = None  # type: ignore[assignment]
    models = None  # type: ignore[assignment]

from .models import DocumentChunk, RetrievedChunk


class QdrantStoreError(RuntimeError):
    pass


class QdrantSchemaError(QdrantStoreError):
    """Deterministic schema/dependency failure; do not retry."""


# Protect lock-file creation as well as Qdrant's lazy initialization in this
# process. The OS lock below remains mandatory for independent processes.
_path_locks_guard = threading.Lock()
_path_locks: weakref.WeakValueDictionary = weakref.WeakValueDictionary()


def _path_lock(path: Path) -> threading.Lock:
    key = os.path.normcase(str(path.resolve()))
    with _path_locks_guard:
        return _path_locks.setdefault(key, threading.Lock())


class QdrantVectorStore:
    def __init__(self, path: Path, collection: str):
        self.path = Path(path)
        self.collection = collection

    def _require_dependency(self) -> None:
        if QdrantClient is None or models is None:
            raise QdrantSchemaError("Qdrant dependency unavailable.")

    @contextmanager
    def _client(self) -> Iterator[object]:
        self._require_dependency()
        self.path.mkdir(parents=True, exist_ok=True)
        # Local Qdrant prohibits concurrent opens. Serialize API/worker operations
        # across processes and threads; no lock is held during embeddings.
        with self._local_lock():
            client = QdrantClient(path=str(self.path))
            try:
                yield client
            finally:
                close = getattr(client, "close", None)
                if callable(close):
                    close()

    @contextmanager
    def _local_lock(self):
        lock = _path_lock(self.path)
        deadline = time.monotonic() + 30
        if not lock.acquire(timeout=30):
            raise QdrantStoreError('Local vector storage busy.')
        try:
            with self._process_lock(deadline):
                yield
        finally:
            lock.release()

    @contextmanager
    def _process_lock(self, deadline: float):
        with open(self.path / '.valyqon.lock', 'a+b') as handle:
            # Windows permits locking a byte beyond EOF. Initialize the byte
            # only after acquisition, so a concurrent creator cannot write to
            # an already locked region.
            acquired = False
            while not acquired:
                handle.seek(0)
                try:
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except OSError:
                    if time.monotonic() >= deadline:
                        raise QdrantStoreError('Local vector storage busy.') from None
                    time.sleep(.05)
            try:
                handle.seek(0, 2)
                if handle.tell() == 0:
                    handle.write(b'0')
                    handle.flush()
                yield
            finally:
                handle.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def initialize(self) -> None:
        try:
            with self._client():
                pass
        except QdrantStoreError:
            raise
        except Exception:
            raise QdrantStoreError("Не удалось инициализировать Qdrant local storage.") from None

    @staticmethod
    def _filter(owner_user_id: int, pdf_sha256: str):
        return models.Filter(must=[
            models.FieldCondition(key="owner_user_id", match=models.MatchValue(value=owner_user_id)),
            models.FieldCondition(key="pdf_sha256", match=models.MatchValue(value=pdf_sha256)),
        ])

    @staticmethod
    def _point_id(owner_user_id: int, pdf_sha256: str, chunk_index: int) -> str:
        value = f"tenderlens:{owner_user_id}:{pdf_sha256}:{chunk_index}"
        return str(uuid.uuid5(uuid.NAMESPACE_URL, value))

    def _ensure_collection(self, client, dimensions: int) -> None:
        if not client.collection_exists(self.collection):
            client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(size=dimensions, distance=models.Distance.COSINE),
            )
            return
        info = client.get_collection(self.collection)
        vectors = info.config.params.vectors
        size = getattr(vectors, "size", None)
        if size is None and isinstance(vectors, dict) and vectors:
            # Named-vector configs are not used by VALYQON AI, but fail clearly.
            raise QdrantSchemaError("Incompatible vector schema.")
        if type(size) is not int or size != dimensions:
            raise QdrantSchemaError(
                "Размерность embeddings изменилась. Укажите новое RAG_QDRANT_COLLECTION и переиндексируйте PDF."
            )

    def has_document(self, owner_user_id: int, pdf_sha256: str) -> bool:
        try:
            with self._client() as client:
                if not client.collection_exists(self.collection):
                    return False
                points, _ = client.scroll(
                    collection_name=self.collection,
                    scroll_filter=self._filter(owner_user_id, pdf_sha256),
                    limit=1,
                    with_payload=False,
                    with_vectors=False,
                )
                return bool(points)
        except QdrantStoreError:
            raise
        except Exception:
            raise QdrantStoreError("Не удалось прочитать Qdrant RAG-индекс.") from None

    def replace_document(
        self,
        owner_user_id: int,
        pdf_sha256: str,
        items: list[tuple[DocumentChunk, tuple[float, ...]]],
    ) -> int:
        if not items:
            return 0
        dimensions = len(items[0][1])
        if dimensions < 1 or any(len(vector) != dimensions for _, vector in items):
            raise QdrantStoreError("Embedding-векторы имеют некорректную размерность.")
        try:
            with self._client() as client:
                self._ensure_collection(client, dimensions)
                client.delete(
                    collection_name=self.collection,
                    points_selector=models.FilterSelector(filter=self._filter(owner_user_id, pdf_sha256)),
                    wait=True,
                )
                points = [
                    models.PointStruct(
                        id=self._point_id(owner_user_id, pdf_sha256, chunk.chunk_index),
                        vector=list(vector),
                        payload={
                            "owner_user_id": owner_user_id,
                            "pdf_sha256": pdf_sha256,
                            "chunk_index": chunk.chunk_index,
                            "page_number": chunk.page_number,
                            "chunk_text": chunk.text,
                        },
                    )
                    for chunk, vector in items
                ]
                client.upsert(collection_name=self.collection, points=points, wait=True)
            return len(items)
        except QdrantStoreError:
            raise
        except Exception:
            raise QdrantStoreError("Не удалось сохранить semantic RAG-индекс в Qdrant.") from None

    def search(
        self,
        owner_user_id: int,
        pdf_sha256: str,
        query_vector: tuple[float, ...],
        limit: int = 5,
        *, ingestion_scope: str | None = None, pipeline_version: str | None = None,
    ) -> list[RetrievedChunk]:
        limit = max(1, min(int(limit), 10))
        try:
            with self._client() as client:
                if not client.collection_exists(self.collection):
                    return []
                result = client.query_points(
                    collection_name=self.collection,
                    query=list(query_vector),
                    query_filter=(self._ingestion_filter(ingestion_scope, pdf_sha256, pipeline_version)
                                  if ingestion_scope is not None else self._filter(owner_user_id, pdf_sha256)),
                    limit=limit,
                    with_payload=True,
                    with_vectors=False,
                )
                output: list[RetrievedChunk] = []
                for point in result.points:
                    payload = point.payload or {}
                    output.append(RetrievedChunk(
                        chunk_index=int(payload.get("chunk_index", 0)),
                        page_number=int(payload.get("page_number", 0)),
                        text=str(payload.get("chunk_text", "")),
                        score=float(point.score),
                    ))
                return output
        except QdrantStoreError:
            raise
        except Exception:
            raise QdrantStoreError("Не удалось выполнить semantic search в Qdrant.") from None

    @staticmethod
    def _ingestion_filter(scope, digest, pipeline):
        return models.Filter(must=[models.FieldCondition(key=key, match=models.MatchValue(value=value))
                                  for key, value in [('ingestion_scope', scope), ('pdf_sha256', digest),
                                                     ('pipeline_version', pipeline)]])

    @staticmethod
    def ingestion_point_id(scope, digest, pipeline, index):
        identity = json.dumps([scope, digest, pipeline, index], separators=(',', ':'))
        return str(uuid.UUID(bytes=hashlib.sha256(identity.encode()).digest()[:16]))

    def upsert_ingestion(self, scope, digest, pipeline, reference, items):
        if not items:
            return 0
        dimensions = len(items[0][1])
        if not dimensions or any(len(vector) != dimensions for _, vector in items):
            raise QdrantSchemaError('Invalid vector dimensions.')
        try:
            with self._client() as client:
                self._ensure_collection(client, dimensions)
                points = [models.PointStruct(
                    id=self.ingestion_point_id(scope, digest, pipeline, chunk.chunk_index), vector=list(vector),
                    payload={'ingestion_scope': scope, 'pdf_sha256': digest, 'pipeline_version': pipeline,
                             'document_ref': reference, 'chunk_index': chunk.chunk_index,
                             'page_number': chunk.page_number, 'chunk_text': chunk.text})
                    for chunk, vector in items]
                client.upsert(collection_name=self.collection, points=points, wait=True)
            return len(items)
        except QdrantStoreError:
            raise
        except Exception:
            raise QdrantStoreError('Vector upsert unavailable.') from None
