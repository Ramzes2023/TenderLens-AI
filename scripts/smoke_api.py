"""Small dependency-free smoke check for a running TenderLens API."""
from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REQUIRED_PATHS = {
    "/health",
    "/api/v1/companies",
    "/api/v1/tenders",
    "/api/v1/scoring/evaluate",
    "/api/v1/rag/ask",
    "/api/v1/monitoring/status",
}


def fetch_json(url: str, *, api_key: str | None = None, timeout: float = 10.0) -> dict:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator supplies URL
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}: {url}")
        return json.loads(response.read().decode("utf-8"))


def run(base_url: str, *, api_key: str | None = None) -> None:
    base = base_url.rstrip("/")
    health = fetch_json(f"{base}/health", timeout=10.0)
    if health.get("status") != "ok":
        raise RuntimeError(f"Health is not ok: {health.get('status')!r}")
    if health.get("version") != "1.2.0":
        raise RuntimeError(f"Unexpected API version: {health.get('version')!r}")

    openapi = fetch_json(f"{base}/openapi.json", timeout=10.0)
    paths = set((openapi.get("paths") or {}).keys())
    missing = REQUIRED_PATHS - paths
    if missing:
        raise RuntimeError("OpenAPI missing endpoints: " + ", ".join(sorted(missing)))

    components = health.get("components") or {}
    print("TenderLens API smoke check: OK")
    print(f"version={health.get('version')} status={health.get('status')}")
    print("components=" + ", ".join(f"{k}:{v}" for k, v in sorted(components.items())))
    print(f"openapi_paths={len(paths)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()
    try:
        run(args.base_url, api_key=args.api_key)
    except (HTTPError, URLError, OSError, ValueError, RuntimeError) as error:
        print(f"Smoke check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
