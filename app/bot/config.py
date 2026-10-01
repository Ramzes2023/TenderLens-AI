"""Environment configuration. No network access or import-time side effects."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from aiogram.utils.token import TokenValidationError, validate_token
from dotenv import load_dotenv

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class ConfigurationError(ValueError):
    """Configuration cannot be used to start the bot."""


@dataclass(frozen=True)
class Settings:
    token: str = field(repr=False)
    log_level: str = "INFO"
    proxy_url: str | None = field(default=None, repr=False)


def load_settings(env_file: Path = ENV_FILE) -> Settings:
    load_dotenv(dotenv_path=env_file, override=False, encoding="utf-8-sig")
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ConfigurationError("Не задан TELEGRAM_BOT_TOKEN. Укажите его в окружении или локальном .env.")
    try:
        validate_token(token)
    except TokenValidationError:
        raise ConfigurationError("Неверный формат TELEGRAM_BOT_TOKEN. Проверьте ключ BotFather.") from None
    level = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigurationError("LOG_LEVEL должен быть DEBUG, INFO, WARNING, ERROR или CRITICAL.")
    proxy = os.environ.get("TELEGRAM_PROXY_URL", "").strip() or None
    if proxy:
        try:
            parsed = urlsplit(proxy)
            valid = (parsed.scheme in {"http", "socks4", "socks5"}
                     and bool(parsed.hostname) and parsed.port is not None
                     and 0 < parsed.port <= 65535
                     and not parsed.query and not parsed.fragment
                     and parsed.path in {"", "/"}
                     and not any(c.isspace() for c in proxy))
        except ValueError:
            valid = False
        if not valid:
            raise ConfigurationError("Неверный TELEGRAM_PROXY_URL: укажите http/socks4/socks5 URL с хостом и портом.")
    return Settings(token=token, log_level=level, proxy_url=proxy)
