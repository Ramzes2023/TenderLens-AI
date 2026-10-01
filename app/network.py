"""Startup-only networking configuration. Never changes Windows settings."""
import os
from urllib.parse import urlsplit


def outbound_proxy() -> str | None:
    proxy = os.environ.get("OUTBOUND_PROXY_URL", "").strip() or None
    if proxy:
        try:
            parsed = urlsplit(proxy)
            valid = (parsed.scheme == "http" and bool(parsed.hostname)
                     and parsed.port is not None and 0 < parsed.port <= 65535
                     and parsed.path in {"", "/"} and not parsed.query
                     and not parsed.fragment and not any(c.isspace() for c in proxy))
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("OUTBOUND_PROXY_URL: требуется HTTP URL с хостом и портом.")
    return proxy


def configure_http_environment() -> None:
    """Call once at startup, before SDK clients exist; not per request.

    GigaChat 0.2.3 has no public proxy/client injection. Its HTTPX clients
    read the process environment. Empty configuration preserves inherited
    networking; changing configuration requires restarting the process.
    """
    proxy = outbound_proxy()
    if proxy:
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ[name] = proxy
    # Preserve NO_PROXY and CA configuration.
