"""Manual semantic embedding/Qdrant health check. Does not print secrets."""
from __future__ import annotations

from app.network import configure_http_environment

from .config import load_rag_settings
from .embedding import FastEmbedEmbeddingProvider, GigaChatEmbeddingProvider
from app.llm.config import load_settings as load_llm_settings


def main() -> int:
    # Needed only for first local model download or optional GigaChat embeddings.
    configure_http_environment()
    rag = load_rag_settings()
    if rag.embedding_provider == "fastembed":
        embedder = FastEmbedEmbeddingProvider(rag.embedding_model)
    else:
        llm = load_llm_settings()
        embedder = GigaChatEmbeddingProvider(llm, rag.embedding_model)
    vectors = embedder.embed_many([
        "срок поставки оборудования",
        "доставка товара должна быть выполнена в течение тридцати дней",
    ])
    print(
        f"Semantic embeddings: OK | provider={rag.embedding_provider} "
        f"| model={rag.embedding_model} | dimensions={len(vectors[0])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
