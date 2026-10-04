"""Configuration for the local FastAPI service."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


class ApiConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ApiSettings:
    host: str
    port: int
    reload: bool
    api_key: str | None = field(default=None, repr=False)
    forwarded_allow_ips: str = "127.0.0.1"


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "true" if default else "false").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ApiConfigurationError(f"{name} должен быть true/false.")


def load_api_settings(env_file: Path = ENV_FILE) -> ApiSettings:
    load_dotenv(env_file, override=False, encoding="utf-8-sig")
    host = (os.environ.get("API_HOST") or "127.0.0.1").strip()
    if not host:
        raise ApiConfigurationError("API_HOST не должен быть пустым.")
    try:
        port = int(os.environ.get("API_PORT", "8000") or "8000")
    except ValueError:
        raise ApiConfigurationError("API_PORT должен быть целым числом.") from None
    if not 1 <= port <= 65535:
        raise ApiConfigurationError("API_PORT должен быть от 1 до 65535.")
    key = (os.environ.get("TENDERLENS_API_KEY") or "").strip() or None
    forwarded_allow_ips = (
        os.environ.get("TENDERLENS_TRUSTED_PROXY_IPS")
        or "127.0.0.1"
    ).strip()
    if not forwarded_allow_ips:
        forwarded_allow_ips = "127.0.0.1"

    return ApiSettings(
        host=host,
        port=port,
        reload=_bool("API_RELOAD", False),
        api_key=key,
        forwarded_allow_ips=forwarded_allow_ips,
    )
