"""Container health: require migrated DB, auth/workspace and a real SMTP handshake."""
import json
from urllib.request import ProxyHandler, build_opener


def main():
    try:
        with build_opener(ProxyHandler({})).open(
            "http://127.0.0.1:8000/private-preview/ready", timeout=6,
        ) as response:
            return 0 if response.status == 200 and json.load(response).get("status") == "ready" else 1
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
