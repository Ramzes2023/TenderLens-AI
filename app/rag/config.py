"""Configuration for Phase 8.1 semantic RAG with Qdrant local mode."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
_COLLECTION_RE = re.compile(r"^[A-Za-z0-9._-]{1,120}$")


class RagConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class RagSettings:
    enabled: bool
    qdrant_path: Path
    qdrant_collection: str
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    top_k: int
    max_context_chars: int
    embedding_provider: str = "fastembed"


def _bool(value: str | None, default: bool = True) -> bool:
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RagConfigurationError("RAG_ENABLED должен быть true или false.")


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise RagConfigurationError(f"{name} должен быть целым числом.") from None
    if not minimum <= value <= maximum:
        raise RagConfigurationError(f"{name} должен быть от {minimum} до {maximum}.")
    return value


def _project_path(raw: str, default: str) -> Path:
    value = (raw or default).strip()
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_rag_settings(env_file: Path = ENV_FILE) -> RagSettings:
    load_dotenv(env_file, override=False, encoding="utf-8-sig")
    enabled = _bool(os.environ.get("RAG_ENABLED"), True)
    qdrant_path = _project_path(os.environ.get("RAG_QDRANT_PATH", ""), "./data/qdrant")
    collection = (os.environ.get("RAG_QDRANT_COLLECTION") or "tenderlens_chunks_v2_local").strip()
    if not _COLLECTION_RE.fullmatch(collection):
        raise RagConfigurationError(
            "RAG_QDRANT_COLLECTION: используйте 1-120 символов A-Z, a-z, 0-9, '.', '_' или '-'."
        )
    embedding_provider = (os.environ.get("RAG_EMBEDDING_PROVIDER") or "fastembed").strip().lower()
    if embedding_provider not in {"fastembed", "gigachat"}:
        raise RagConfigurationError("RAG_EMBEDDING_PROVIDER должен быть fastembed или gigachat.")
    default_model = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2" if embedding_provider == "fastembed" else "Embeddings-2"
    embedding_model = (os.environ.get("RAG_EMBEDDING_MODEL") or default_model).strip()
    if not embedding_model:
        raise RagConfigurationError("RAG_EMBEDDING_MODEL не должен быть пустым.")
    chunk_size = _integer("RAG_CHUNK_SIZE", 1200, 300, 5000)
    overlap = _integer("RAG_CHUNK_OVERLAP", 180, 0, 1500)
    if overlap >= chunk_size:
        raise RagConfigurationError("RAG_CHUNK_OVERLAP должен быть меньше RAG_CHUNK_SIZE.")
    top_k = _integer("RAG_TOP_K", 5, 1, 10)
    max_context = _integer("RAG_MAX_CONTEXT_CHARS", 7000, 1000, 20000)
    return RagSettings(
        enabled=enabled,
        qdrant_path=qdrant_path,
        qdrant_collection=collection,
        embedding_model=embedding_model,
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        top_k=top_k,
        max_context_chars=max_context,
        embedding_provider=embedding_provider,
    )
