"""Load LLM settings separately from Telegram settings."""
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from app.network import configure_http_environment

from .base import LLMConfigurationError

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def safe_model(value):
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,255}", value) is not None


@dataclass(frozen=True)
class GroqSettings:
    api_key: str = field(repr=False)
    model: str = "openai/gpt-oss-120b"
    timeout: float = 30.0

    def __post_init__(self):
        if (type(self.api_key) is not str or not self.api_key.strip()
                or any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in self.api_key)
                or len(self.api_key) > 4096):
            raise LLMConfigurationError("Invalid Groq credentials.")
        if not safe_model(self.model):
            raise LLMConfigurationError("Invalid Groq model.")
        if (type(self.timeout) not in (int, float) or not 0 < self.timeout <= 300
                or not math.isfinite(self.timeout)):
            raise LLMConfigurationError("Invalid Groq timeout.")


@dataclass(frozen=True)
class FailoverSettings:
    enabled: bool = False
    provider: str = "groq"

    def __post_init__(self):
        if type(self.enabled) is not bool or self.provider != "groq":
            raise LLMConfigurationError("Invalid AI fallback configuration.")


def load_failover_settings():
    value = os.environ.get("VALYQON_AI_FALLBACK_ENABLED", "false").strip().lower()
    if value not in {"true", "false", "1", "0"}:
        raise LLMConfigurationError("Invalid AI fallback configuration.")
    return FailoverSettings(value in {"true", "1"},
                            os.environ.get("VALYQON_AI_FALLBACK_PROVIDER", "groq").strip())


def load_groq_settings():
    try:
        timeout = float(os.environ.get("GROQ_TIMEOUT", "30"))
    except (ValueError, OverflowError):
        raise LLMConfigurationError("Invalid Groq timeout.") from None
    return GroqSettings(os.environ.get("GROQ_API_KEY", "").strip(),
                        os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"), timeout)


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
