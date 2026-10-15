"""Canonical, credential-free Redis configuration."""
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import load_dotenv


class CacheConfigurationError(ValueError):
    pass


def segment(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", value):
        raise CacheConfigurationError("Invalid cache namespace or domain.")
    return value


@dataclass(frozen=True)
class CacheSettings:
    url: str = field(default="", repr=False)
    required: bool = False
    pool_max: int = 10
    connect_timeout: float = 2.0
    socket_timeout: float = 2.0
    namespace: str = "local"

    def __post_init__(self):
        try:
            segment(self.namespace)
            if type(self.required) is not bool or type(self.pool_max) is not int or not 1 <= self.pool_max <= 100:
                raise ValueError
            for value in (self.connect_timeout, self.socket_timeout):
                if isinstance(value, bool) or not math.isfinite(value) or not 0 < value <= 120:
                    raise ValueError
            if not isinstance(self.url, str) or self.url != self.url.strip():
                raise ValueError
            if self.url:
                u = urlsplit(self.url)
                # URL query options could bypass pool/timeout bounds.
                if u.scheme not in {"redis", "rediss"} or not u.hostname or u.query or u.fragment:
                    raise ValueError
                if u.port is not None and not 1 <= u.port <= 65535:
                    raise ValueError
                if u.path not in {"", "/"} and not re.fullmatch(r"/[0-9]{1,4}", u.path):
                    raise ValueError
                if any(c.isspace() for c in self.url):
                    raise ValueError
            elif self.required:
                raise ValueError
        except (ValueError, TypeError, OverflowError):
            raise CacheConfigurationError("Invalid cache configuration.") from None


def load_cache_settings(env_file=Path(__file__).resolve().parents[2] / ".env"):
    load_dotenv(env_file, override=False, encoding="utf-8-sig")
    try:
        required = os.environ.get("VALYQON_REDIS_REQUIRED", "false").strip().lower()
        if required not in {"true", "false", "1", "0"}:
            raise ValueError
        return CacheSettings(
            url=os.environ.get("VALYQON_REDIS_URL", ""), required=required in {"true", "1"},
            pool_max=int(os.environ.get("VALYQON_REDIS_POOL_MAX", "10")),
            connect_timeout=float(os.environ.get("VALYQON_REDIS_CONNECT_TIMEOUT", "2")),
            socket_timeout=float(os.environ.get("VALYQON_REDIS_SOCKET_TIMEOUT", "2")),
            namespace=os.environ.get("VALYQON_CACHE_NAMESPACE", "local"))
    except (ValueError, TypeError, OverflowError):
        raise CacheConfigurationError("Invalid cache configuration.") from None
