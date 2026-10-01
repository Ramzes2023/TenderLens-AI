"""Qdrant-backed vector storage for Phase 8.1.

The default uses qdrant-client local mode, so no Docker/server is required for
this prototype. The same payload/filter contract can later be pointed at a real
Qdrant service with minimal changes.
"""
from __future__ import annotations

import uuid
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


class QdrantVectorStore:
    def __init__(self, path: Path, collection: str):
        self.path = Path(path)
        self.collection = collection

    def _require_dependency(self) -> None:
        if QdrantClient is None or models is None:
            raise QdrantStoreError("Не установлен qdrant-client. Выполните pip install -r requirements.txt.")

    @contextmanager
    def _client(self) -> Iterator[object]:
        self._require_dependency()
        self.path.mkdir(parents=True, exist_ok=True)
        client = QdrantClient(path=str(self.path))
        try:
            yield client
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

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
            # Named-vector configs are not used by TenderLens, but fail clearly.
            raise QdrantStoreError("Qdrant collection использует несовместимую named-vector конфигурацию.")
        if int(size) != dimensions:
            raise QdrantStoreError(
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
    ) -> list[RetrievedChunk]:
        limit = max(1, min(int(limit), 10))
        try:
            with self._client() as client:
                if not client.collection_exists(self.collection):
                    return []
                result = client.query_points(
                    collection_name=self.collection,
                    query=list(query_vector),
                    query_filter=self._filter(owner_user_id, pdf_sha256),
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
