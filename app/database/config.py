"""Canonical DATABASE_URL configuration for PostgreSQL and file-backed SQLite."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
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
    url: str = field(repr=False)
    path: Path | None
    backend: str = "sqlite"
    pool_min: int = 1
    pool_max: int = 10
    pool_timeout: float = 10.0


def parse_database_settings(url: str, *, require_postgres: bool = False,
                            pool_min: int = 1, pool_max: int = 10,
                            pool_timeout: float = 10.0) -> DatabaseSettings:
    """Never include input URLs or parser exceptions in diagnostics."""
    try:
        if not isinstance(url, str) or not url.strip():
            raise ValueError
        url = url.strip()
        parsed = urlparse(url)
        if not 0 <= pool_min <= pool_max <= 100 or pool_max < 1 or not 0 < pool_timeout <= 120:
            raise ValueError
        if parsed.scheme in {"postgresql", "postgres"}:
            if not parsed.hostname or not parsed.path.strip("/") or parsed.fragment:
                raise ValueError
            if parsed.port is not None and not 1 <= parsed.port <= 65535:
                raise ValueError
            return DatabaseSettings(url, None, "postgresql", pool_min, pool_max, pool_timeout)
        if require_postgres:
            raise ValueError
        if parsed.scheme == "sqlite":
            if parsed.query or parsed.fragment:
                raise ValueError
            path = _sqlite_path_from_url(url)
        elif "://" not in url and (not parsed.scheme or len(parsed.scheme) == 1):
            path = Path(url).expanduser().resolve()
        else:
            raise ValueError
        return DatabaseSettings(url, path, "sqlite", pool_min, pool_max, pool_timeout)
    except (ValueError, TypeError, OverflowError):
        raise DatabaseConfigurationError("Invalid database configuration.") from None


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
    url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    requirement = os.environ.get("VALYQON_DATABASE_REQUIRE_POSTGRES", "false").strip().lower()
    if requirement not in {"true", "false", "1", "0"}:
        raise DatabaseConfigurationError("Invalid database configuration.")
    try:
        return parse_database_settings(
            url, require_postgres=requirement in {"true", "1"},
            pool_min=int(os.environ.get("VALYQON_DB_POOL_MIN", "1")),
            pool_max=int(os.environ.get("VALYQON_DB_POOL_MAX", "10")),
            pool_timeout=float(os.environ.get("VALYQON_DB_POOL_TIMEOUT", "10")),
        )
    except ValueError:
        raise DatabaseConfigurationError("Invalid database configuration.") from None
