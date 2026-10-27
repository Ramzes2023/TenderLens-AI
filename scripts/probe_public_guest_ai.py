"""Bounded public HTTPS diagnostic of one anonymous VALYQON product-help request.

One benign question on the user-specified public site, no credentials/cookies,
no production changes, no secrets, no response bodies in logs. This proves
a live generated reply only when a real 200 public-product response is seen.
"""
from __future__ import annotations

import ipaddress
import json
import socket
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

HOST = "valyqon.duckdns.org"
URL = f"https://{HOST}/api/v1/public/help/ask"
QUESTION = "Как работает гостевой поиск VALYQON?"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def classify(status: int, body: bytes) -> str:
    """Classify only known public API structures; never print arbitrary content."""
    data = None
    try:
        data = json.loads(body[:4096].decode("utf-8"))
    except (ValueError, UnicodeError):
        pass
    if status == 200:
        if (isinstance(data, dict)
                and data.get("scope") == "public_product_only"
                and isinstance(data.get("answer"), str)
                and bool(data["answer"].strip())):
            return "LIVE_ANSWER_VERIFIED"
        return "UNEXPECTED_SUCCESS_PAYLOAD"
    if status == 503:
        detail = data.get("detail") if isinstance(data, dict) else None
        return {
            "Public AI help is not enabled.": "FEATURE_DISABLED",
            "Public AI help is not configured.": "PROVIDER_MISSING",
            "Public AI help is temporarily unavailable.": "PROVIDER_REQUEST_FAILED",
        }.get(detail, "SERVICE_UNAVAILABLE_UNKNOWN")
    return {
        401: "AUTH_GATE_UNEXPECTED",
        403: "ORIGIN_REJECTED",
        404: "ROUTE_NOT_DEPLOYED",
        405: "METHOD_REJECTED",
        422: "REQUEST_REJECTED",
        429: "PUBLIC_RATE_LIMITED",
        502: "PROXY_BAD_GATEWAY",
        504: "PROXY_TIMEOUT",
    }.get(status, "UNEXPECTED_HTTP_STATUS")


def classify_health(status: int, body: bytes) -> str:
    """Configuration presence only; this never proves the provider can answer."""
    if status != 200:
        return "HEALTH_UNAVAILABLE"
    try:
        payload = json.loads(body[:8192].decode("utf-8"))
        value = payload.get("components", {}).get("llm")
    except (ValueError, UnicodeError, AttributeError, TypeError):
        return "HEALTH_UNAVAILABLE"
    return {
        "ready": "CONFIGURED_NOT_LIVE_VERIFIED",
        "unavailable": "PROVIDER_NOT_CONFIGURED",
    }.get(value, "UNKNOWN")


def diagnose() -> dict:
    result = {
        "target": HOST, "endpoint": "/api/v1/public/help/ask",
        "classification": "NOT_VERIFIED", "http_status": None,
        "server_llm": "NOT_VERIFIED",
        "live_generated_answer": False, "production_changed": False,
        "real_tender_data_exposed": False,
    }
    try:
        ips = socket.getaddrinfo(HOST, 443, type=socket.SOCK_STREAM)
        if not ips or any(not ipaddress.ip_address(item[4][0]).is_global for item in ips):
            result["classification"] = "PUBLIC_DNS_NOT_VERIFIED"
            return result
        client = build_opener(
            HTTPSHandler(context=ssl.create_default_context()), _NoRedirect()
        )
        # Separate read-only /health component check: the configured-model
        # state helps distinguish "just disabled" from missing credentials.
        # Never log the raw health body, version, URLs or private settings.
        try:
            with client.open(Request(f"https://{HOST}/health"), timeout=8) as health:
                result["server_llm"] = classify_health(health.status, health.read(8193))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            result["server_llm"] = "HEALTH_UNAVAILABLE"
        req = Request(
            URL, method="POST",
            data=json.dumps({"question": QUESTION}, ensure_ascii=False).encode("utf-8"),
            headers={
                "Origin": f"https://{HOST}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "VALYQON-Public-AI-Diagnostic/1.0",
            },
        )
        try:
            with client.open(req, timeout=12) as response:
                status, body = response.status, response.read(4097)
        except HTTPError as error:
            status, body = error.code, error.read(4097)
        result["http_status"] = status
        result["classification"] = classify(status, body)
        result["live_generated_answer"] = result["classification"] == "LIVE_ANSWER_VERIFIED"
    except (socket.gaierror, ssl.SSLError, URLError, TimeoutError, OSError, ValueError):
        # No exception messages: they may contain network details or request text.
        result["classification"] = "PUBLIC_NETWORK_OR_TLS_UNAVAILABLE"
    return result


def main() -> int:
    result = diagnose()
    print("PUBLIC_GUEST_AI_DIAGNOSTIC=" + json.dumps(result, sort_keys=True))
    print("AI_ANSWER_ON_LIVE_PUBLIC_HOST=" +
          ("VERIFIED" if result["live_generated_answer"] else "NOT_VERIFIED"))
    print("THIS_PROBE_DID_NOT_DEPLOY=YES")
    return 0 if result["live_generated_answer"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
