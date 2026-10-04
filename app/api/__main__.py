"""Run Phase 10 API with: python -m app.api"""
from __future__ import annotations

import sys

import uvicorn

from .config import ApiConfigurationError, load_api_settings


def main() -> int:
    try:
        settings = load_api_settings()
    except ApiConfigurationError as error:
        print(f"Ошибка конфигурации API: {error}", file=sys.stderr)
        return 2
    uvicorn.run(
        "app.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        proxy_headers=True,
        forwarded_allow_ips=settings.forwarded_allow_ips,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
