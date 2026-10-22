"""Strict official Chechnya EIS URL preflight for Windows and GitHub Actions.

No network, no Telegram, no production state. The full URL travels only via
a process-local environment variable. Never echo it into logs or tracebacks.
"""
from __future__ import annotations

import os

def main() -> int:
    try:
        from app.sources.ru_chechnya_eis_rss import validate_chechnya_feed_urls
        from app.sources.eis_rss import SourceError

        original = os.environ.get("VALYQON_CHECHNYA_URL_VALIDATE", "")
        validate_chechnya_feed_urls((original,))
    except (ValueError, SourceError) as error:
        # These are known locally generated, safe validation exceptions. The
        # source validator never includes the operator's raw URL in messages.
        print("CHECHNYA_URL_PREFLIGHT=REJECTED")
        print("CHECHNYA_URL_PREFLIGHT_REASON=" + type(error).__name__)
        return 2
    except Exception as error:
        # An import/platform failure is NOT an invalid procurement URL.
        print("CHECHNYA_URL_PREFLIGHT=RUNTIME_ERROR")
        print("CHECHNYA_URL_PREFLIGHT_REASON=" + type(error).__name__)
        return 3
    print("CHECHNYA_URL_PREFLIGHT=ACCEPTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
