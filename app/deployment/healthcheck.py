"""Strict container healthcheck for TenderLens AI.

The public `/health` endpoint intentionally returns HTTP 200 even when some
optional components are unavailable so operators can inspect the degraded
state. Docker needs a stricter signal, therefore this probe exits successfully
only when the JSON payload reports ``status == \"ok\"``.
"""
from __future__ import annotations

import json
import os
import sys
from urllib.error import URLError
from urllib.request import urlopen

DEFAULT_URL = "http://127.0.0.1:8000/health"


def check(url: str | None = None, timeout: float = 5.0) -> bool:
    target = (url or os.environ.get("TENDERLENS_HEALTHCHECK_URL") or DEFAULT_URL).strip()
    if not target:
        target = DEFAULT_URL
    try:
        with urlopen(target, timeout=timeout) as response:  # noqa: S310 - URL is operator-controlled.
            if getattr(response, "status", 200) != 200:
                return False
            payload = json.load(response)
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("status") == "ok"


def main() -> int:
    healthy = check()
    if not healthy:
        print("TenderLens healthcheck failed", file=sys.stderr)
        return 1
    print("TenderLens healthcheck OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
