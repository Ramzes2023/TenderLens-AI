"""Load a versioned company profile without mixing it with secrets."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from .models import CompanyProfile

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_PROFILE_FILE = PROJECT_ROOT / "config" / "company_profile.example.json"


class ScoringConfigurationError(ValueError):
    pass


def _resolve_profile_path(value: str | None) -> Path:
    if not value:
        return DEFAULT_PROFILE_FILE
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_company_profile(env_file: Path = ENV_FILE) -> CompanyProfile:
    load_dotenv(env_file, override=False, encoding="utf-8-sig")
    path = _resolve_profile_path(os.environ.get("COMPANY_PROFILE_FILE"))
    try:
        raw = path.read_text(encoding="utf-8-sig")
        payload = json.loads(raw)
        return CompanyProfile.model_validate(payload)
    except FileNotFoundError:
        raise ScoringConfigurationError(f"Файл профиля компании не найден: {path}") from None
    except (OSError, json.JSONDecodeError, ValidationError):
        raise ScoringConfigurationError("Профиль компании повреждён или содержит недопустимые значения.") from None
