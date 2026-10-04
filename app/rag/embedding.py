"""Embedding providers for VALYQON AI RAG.

Phase 8.1 defaults to a local multilingual FastEmbed model so semantic RAG does
not require a paid embeddings API. GigaChat embeddings remain available as an
optional provider for accounts with embedding access.
"""
from __future__ import annotations

import logging
import math
from typing import Protocol, Sequence

import httpx
from gigachat import GigaChat
from gigachat.exceptions import AuthenticationError, ForbiddenError, GigaChatException

from app.llm.config import GigaChatSettings

try:
    from fastembed import TextEmbedding
except ImportError:  # clearer error before optional dependency is installed
    TextEmbedding = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    pass


class EmbeddingProvider(Protocol):
    def embed_many(self, texts: Sequence[str]) -> list[tuple[float, ...]]: ...

    def embed(self, text: str) -> tuple[float, ...]: ...


def _validated_vector(values, source: str) -> tuple[float, ...]:
    vector = tuple(float(value) for value in values)
    if not vector or any(not math.isfinite(value) for value in vector):
        raise EmbeddingError(f"{source} вернул некорректный embedding-вектор.")
    return vector


class FastEmbedEmbeddingProvider:
    """Local multilingual semantic embeddings powered by ONNX/FastEmbed.

    Model files are downloaded once on first use and then reused from the local
    cache. The default paraphrase-multilingual-MiniLM-L12-v2 model is
    multilingual and works well for Russian tender text on CPU without PyTorch.
    """

    def __init__(self, model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"):
        self.model_name = model.strip() or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        if TextEmbedding is None:
            raise EmbeddingError(
                "Не установлен FastEmbed. Выполните: python -m pip install -r requirements.txt"
            )
        try:
            self._client = TextEmbedding(model_name=self.model_name)
        except Exception:
            raise EmbeddingError(
                "Не удалось загрузить локальную embedding-модель. "
                "При первом запуске нужен интернет для скачивания модели."
            ) from None

    def _document_text(self, text: str) -> str:
        text = text.strip()
        if not text:
            raise ValueError("Тексты для embeddings не должны быть пустыми.")
        # E5 models are trained with query/passage prefixes.
        if "e5" in self.model_name.casefold():
            return f"passage: {text}"
        return text

    def _query_text(self, text: str) -> str:
        text = text.strip()
        if not text:
            raise ValueError("Текст запроса для embeddings не должен быть пустым.")
        if "e5" in self.model_name.casefold():
            return f"query: {text}"
        return text

    def embed_many(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        prepared = [self._document_text(text) for text in texts]
        if not prepared:
            raise ValueError("Тексты для embeddings не должны быть пустыми.")
        try:
            vectors = [_validated_vector(vector, "FastEmbed") for vector in self._client.embed(prepared)]
        except (EmbeddingError, ValueError):
            raise
        except Exception:
            raise EmbeddingError("Не удалось построить локальные semantic embeddings.") from None
        if len(vectors) != len(prepared):
            raise EmbeddingError("FastEmbed вернул неполный набор embedding-векторов.")
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1:
            raise EmbeddingError("Embedding-векторы имеют разную размерность.")
        return vectors

    def embed(self, text: str) -> tuple[float, ...]:
        prepared = self._query_text(text)
        try:
            iterator = self._client.embed([prepared])
            vector = next(iter(iterator))
            return _validated_vector(vector, "FastEmbed")
        except (EmbeddingError, ValueError):
            raise
        except Exception:
            raise EmbeddingError("Не удалось построить embedding для вопроса.") from None


class GigaChatEmbeddingProvider:
    """Optional paid GigaChat embedding adapter used from worker threads."""

    def __init__(self, settings: GigaChatSettings, model: str = "Embeddings-2"):
        self.settings = settings
        self.model = model.strip() or "Embeddings-2"

    def embed_many(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        clean = [text.strip() for text in texts]
        if not clean or any(not text for text in clean):
            raise ValueError("Тексты для embeddings не должны быть пустыми.")
        try:
            with GigaChat(
                credentials=self.settings.credentials,
                scope=self.settings.scope,
                model=self.settings.model,
                timeout=self.settings.timeout,
                verify_ssl_certs=True,
                ca_bundle_file=self.settings.ca_bundle_file,
                max_retries=0,
            ) as client:
                response = client.embeddings(clean, model=self.model)
            ordered = sorted(response.data, key=lambda item: item.index)
            if len(ordered) != len(clean):
                raise EmbeddingError("GigaChat вернул неполный набор embedding-векторов.")
            vectors = [_validated_vector(item.embedding, "GigaChat") for item in ordered]
            dimensions = {len(vector) for vector in vectors}
            if len(dimensions) != 1:
                raise EmbeddingError("Embedding-векторы имеют разную размерность.")
            return vectors
        except (AuthenticationError, ForbiddenError):
            error = EmbeddingError("GigaChat embeddings: проверьте ключ, scope и права доступа.")
        except (TimeoutError, httpx.TimeoutException):
            error = EmbeddingError("GigaChat embeddings: превышено время ожидания.")
        except httpx.RequestError:
            error = EmbeddingError("GigaChat embeddings: ошибка сети или TLS.")
        except EmbeddingError as exc:
            error = exc
        except GigaChatException:
            error = EmbeddingError("GigaChat embeddings: ошибка API, доступа или квоты.")
        except Exception:
            error = EmbeddingError("Не удалось получить GigaChat semantic embeddings.")
        logger.warning("Embedding request failed: %s", type(error).__name__)
        raise error from None

    def embed(self, text: str) -> tuple[float, ...]:
        return self.embed_many([text])[0]
