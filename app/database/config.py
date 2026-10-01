"""Database configuration for the local MVP."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_DATABASE_URL = "sqlite:///./data/tenderlens.db"


class DatabaseConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class DatabaseSettings:
    url: str
    path: Path


def _sqlite_path_from_url(url: str) -> Path:
    parsed = urlparse(url)
    if parsed.scheme != "sqlite":
        raise DatabaseConfigurationError("Phase 7 поддерживает только sqlite:/// URL.")
    if parsed.netloc not in ("", None):
        raise DatabaseConfigurationError("SQLite URL не должен содержать hostname.")
    raw = unquote(parsed.path or "")
    if not raw:
        raise DatabaseConfigurationError("В DATABASE_URL не указан путь к SQLite-файлу.")

    # sqlite:///./data/file.db -> /./data/file.db after urlparse; keep it project-relative.
    if raw.startswith("/./"):
        path = PROJECT_ROOT / raw[3:]
    elif raw.startswith("/") and len(raw) >= 3 and raw[2] == ":":  # Windows /C:/...
        path = Path(raw[1:])
    elif raw.startswith("/"):
        path = Path(raw)
    else:
        path = PROJECT_ROOT / raw
    return path.expanduser().resolve()


def load_database_settings(env_file: Path = ENV_FILE) -> DatabaseSettings:
    load_dotenv(env_file, override=False, encoding="utf-8-sig")
    url = (os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL).strip()
    if not url:
        url = DEFAULT_DATABASE_URL
    path = _sqlite_path_from_url(url)
    return DatabaseSettings(url=url, path=path)
