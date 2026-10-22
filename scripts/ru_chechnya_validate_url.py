"""Strict official Chechnya EIS URL preflight for Windows and GitHub Actions.

No network, no Telegram, no production state. The full URL travels only via
a process-local environment variable. Never echo it into logs or tracebacks.
"""
from __future__ import annotations

import os

def main() -> int:
    try:
        from app.sources.ru_chechnya_eis_rss import validate_chechnya_feed_urls

        original = os.environ.get("VALYQON_CHECHNYA_URL_VALIDATE", "")
        validate_chechnya_feed_urls((original,))
    except Exception as error:
        # Includes failures while importing dependencies. Never leak the URL,
        # exception message or traceback into operator logs.
        name = type(error).__name__
        if name in ("ValueError", "SourceError"):
            print("CHECHNYA_URL_PREFLIGHT=REJECTED")
            print("CHECHNYA_URL_PREFLIGHT_REASON=" + name)
            return 2
        print("CHECHNYA_URL_PREFLIGHT=RUNTIME_ERROR")
        print("CHECHNYA_URL_PREFLIGHT_REASON=" + name)
        return 3
    print("CHECHNYA_URL_PREFLIGHT=ACCEPTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
