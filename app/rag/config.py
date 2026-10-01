"""Configuration for the local Phase 8 RAG index."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_RAG_DATABASE_URL = "sqlite:///./data/tenderlens_rag.db"


class RagConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class RagSettings:
    enabled: bool
    database_path: Path
    chunk_size: int
    chunk_overlap: int
    vector_dimensions: int
    top_k: int
    max_context_chars: int


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


def _sqlite_path(url: str) -> Path:
    parsed = urlparse(url)
    if parsed.scheme != "sqlite" or parsed.netloc not in ("", None):
        raise RagConfigurationError("RAG_DATABASE_URL должен быть sqlite:/// URL.")
    raw = unquote(parsed.path or "")
    if not raw:
        raise RagConfigurationError("В RAG_DATABASE_URL не указан путь к SQLite-файлу.")
    if raw.startswith("/./"):
        path = PROJECT_ROOT / raw[3:]
    elif raw.startswith("/") and len(raw) >= 3 and raw[2] == ":":
        path = Path(raw[1:])
    elif raw.startswith("/"):
        path = Path(raw)
    else:
        path = PROJECT_ROOT / raw
    return path.expanduser().resolve()


def load_rag_settings(env_file: Path = ENV_FILE) -> RagSettings:
    load_dotenv(env_file, override=False, encoding="utf-8-sig")
    enabled = _bool(os.environ.get("RAG_ENABLED"), True)
    url = (os.environ.get("RAG_DATABASE_URL") or DEFAULT_RAG_DATABASE_URL).strip()
    chunk_size = _integer("RAG_CHUNK_SIZE", 1200, 300, 5000)
    overlap = _integer("RAG_CHUNK_OVERLAP", 180, 0, 1500)
    if overlap >= chunk_size:
        raise RagConfigurationError("RAG_CHUNK_OVERLAP должен быть меньше RAG_CHUNK_SIZE.")
    dimensions = _integer("RAG_VECTOR_DIMENSIONS", 512, 64, 4096)
    top_k = _integer("RAG_TOP_K", 5, 1, 10)
    max_context = _integer("RAG_MAX_CONTEXT_CHARS", 7000, 1000, 20000)
    return RagSettings(
        enabled=enabled,
        database_path=_sqlite_path(url),
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        vector_dimensions=dimensions,
        top_k=top_k,
        max_context_chars=max_context,
    )
