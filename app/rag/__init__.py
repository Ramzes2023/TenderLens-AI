"""Semantic RAG components backed by GigaChat embeddings and Qdrant."""
from .config import RagConfigurationError, RagSettings, load_rag_settings
from .embedding import EmbeddingError, EmbeddingProvider, GigaChatEmbeddingProvider
from .models import DocumentChunk, RagAnswer, RetrievedChunk
from .qdrant_store import QdrantStoreError, QdrantVectorStore
from .service import RagError, RagService

# Backward-compatible alias for code that still catches RagStoreError.
RagStoreError = QdrantStoreError

__all__ = [
    "RagConfigurationError", "RagSettings", "load_rag_settings",
    "EmbeddingError", "EmbeddingProvider", "GigaChatEmbeddingProvider",
    "DocumentChunk", "RetrievedChunk", "RagAnswer",
    "RagError", "RagService", "QdrantStoreError", "RagStoreError", "QdrantVectorStore",
]
