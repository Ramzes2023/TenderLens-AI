"""Load LLM settings separately from Telegram settings."""
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from app.network import configure_http_environment

from .base import LLMConfigurationError

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


@dataclass(frozen=True)
class GigaChatSettings:
    credentials: str = field(repr=False)
    model: str
    scope: str = "GIGACHAT_API_PERS"
    timeout: float = 30.0
    ca_bundle_file: str | None = field(default=None, repr=False)

    def __post_init__(self):
        if not self.credentials.strip():
            raise LLMConfigurationError("Не задан GIGACHAT_CREDENTIALS.")
        if not self.model.strip():
            raise LLMConfigurationError("Не задан GIGACHAT_MODEL.")
        if self.scope not in {"GIGACHAT_API_PERS", "GIGACHAT_API_B2B", "GIGACHAT_API_CORP"}:
            raise LLMConfigurationError("Недопустимый GIGACHAT_SCOPE.")
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise LLMConfigurationError("GIGACHAT_TIMEOUT должен быть положительным числом.")
        if self.ca_bundle_file and not Path(self.ca_bundle_file).is_file():
            raise LLMConfigurationError("Файл GIGACHAT_CA_BUNDLE_FILE не найден.")


def load_settings(env_file: Path = ENV_FILE) -> GigaChatSettings:
    load_dotenv(env_file, override=False, encoding="utf-8-sig")
    if os.environ.get("VALYQON_AI_PROVIDER", os.environ.get("LLM_PROVIDER", "gigachat")).strip() != "gigachat":
        raise LLMConfigurationError("Пока поддерживается только LLM_PROVIDER=gigachat.")
    try:
        timeout = float(os.environ.get("GIGACHAT_TIMEOUT", "30") or "30")
    except ValueError:
        raise LLMConfigurationError("GIGACHAT_TIMEOUT должен быть числом.") from None
    settings = GigaChatSettings(
        credentials=os.environ.get("GIGACHAT_CREDENTIALS", "").strip(),
        model=os.environ.get("GIGACHAT_MODEL", "").strip(),
        scope=os.environ.get("GIGACHAT_SCOPE", "").strip() or "GIGACHAT_API_PERS",
        timeout=timeout,
        ca_bundle_file=os.environ.get("GIGACHAT_CA_BUNDLE_FILE", "").strip() or None,
    )

    try:
        configure_http_environment()
    except ValueError as error:
        raise LLMConfigurationError(str(error)) from None
    return settings
