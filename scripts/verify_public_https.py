"""Non-destructive public HTTPS read-only launch probe.

Never deploys, never fetches private endpoints or credentials. Passing this
network smoke is only an HTTPS edge check; billing, source-to-user evidence and
production readiness require *separate* acceptance.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import socket
import ssl
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener


def validate_target(url: str) -> tuple[str, int]:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("HTTPS domain without credentials is mandatory.")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.port not in (None, 443):
        raise ValueError("Use a bare HTTPS hostname, with no path, query or custom port.")
    hostname = parsed.hostname.lower().rstrip(".")
    if (len(hostname) > 253 or "." not in hostname or hostname.endswith(".example.com")
            or hostname.endswith(".invalid") or hostname in {"localhost","127.0.0.1"}
            or not re.fullmatch(r"[a-z0-9][a-z0-9.-]*[a-z0-9]",hostname)):
        raise ValueError("A real public DNS hostname is required.")
    if any(not 1 <= len(label) <= 63 or label.startswith("-") or label.endswith("-")
           for label in hostname.split(".")):
        raise ValueError("Invalid DNS label.")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError("A verified DNS hostname, not an IP literal, is required.")
    return hostname, 443


class _NoRedirect(HTTPRedirectHandler):
    """A public health check must not follow redirects to another host."""
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _https_client():
    return build_opener(HTTPSHandler(context=ssl.create_default_context()), _NoRedirect())


def _is_public_landing(html: str) -> bool:
    """Require current public procurement landing, not legacy 200 OK login."""
    return (
        "VALYQON" in html.upper()
        and '<body class="landing premium"' in html
        and 'id="guestSearchForm"' in html
        and 'id="guestSearchResults"' in html
    )


def verify(url: str, timeout: float = 8.0) -> dict:
    host, port = validate_target(url)
    result = {
        "kind": "VALYQON_PUBLIC_HTTPS_READ_ONLY",
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "host": host, "dns": "NOT_VERIFIED", "tls": "NOT_VERIFIED",
        "homepage": "NOT_VERIFIED", "health": "NOT_VERIFIED",
        "security_headers": "NOT_VERIFIED",
        "real_source_worker_to_user": "NOT_TESTED",
        "billing_entitlements": "NOT_TESTED",
        "outbound_email_telegram": "NOT_TESTED",
        "postgres_backup_restore": "NOT_TESTED",
        "ready_for_commercial_launch": False,
    }
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        if not addresses:
            raise OSError("No DNS addresses found.")
        for address in addresses:
            parsed_ip = ipaddress.ip_address(address[4][0])
            if not parsed_ip.is_global:
                raise OSError("DNS record resolves outside globally routable address space.")
        result["dns"] = "PASS"
        # TLS validates the public certificate. Redirects are rejected to
        # prevent a health-probe input from reaching any unrelated host.
        client = _https_client()
        with client.open(Request(f"https://{host}/", headers={
                "User-Agent": "VALYQON-ReleaseReadiness/1.0"
        }), timeout=timeout) as response:
            result["tls"] = "PASS"
            payload = response.read(131072).decode("utf-8",errors="replace")
            result["homepage"] = (
                "PASS" if response.status == 200 and _is_public_landing(payload)
                else "FAIL"
            )
            headers = response.headers
            result["security_headers"] = ("PASS" if "max-age=" in
                headers.get("Strict-Transport-Security","").lower()
                and headers.get("X-Content-Type-Options","").lower()=="nosniff"
                else "FAIL")
        with client.open(Request(f"https://{host}/health", headers={
                "User-Agent": "VALYQON-ReleaseReadiness/1.0"
        }), timeout=timeout) as response:
            data = response.read(16384)
            health = json.loads(data)
            # HTTP 200 with any JSON object is not proof the API is ready:
            # /health deliberately returns "degraded" with 200 when the
            # database/scoring or cache is unavailable.
            valid_health = (
                response.status == 200 and isinstance(health, dict)
                and health.get("status") == "ok"
                and health.get("service") == "VALYQON AI"
                and isinstance(health.get("components"), dict)
                and health["components"].get("database") == "ready"
                and health["components"].get("scoring") == "ready"
                and health["components"].get("cache") != "unavailable"
            )
            result["health"] = "PASS" if valid_health else "FAIL"
    except (socket.gaierror,ssl.SSLError,HTTPError,URLError,TimeoutError,
            ConnectionError,OSError,ValueError) as exc:
        # Never leak request headers, cookies, credentials or raw upstream body.
        result["blocker_type"] = type(exc).__name__
    result["public_edge_pass"] = all(result[k]=="PASS" for k in (
        "dns","tls","homepage","health","security_headers"))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only VALYQON HTTPS edge readiness.")
    parser.add_argument("--url", required=True,help="Bare public HTTPS URL; no credentials.")
    parser.add_argument("--timeout",type=float,default=8.0)
    args=parser.parse_args(argv)
    if not 1 <= args.timeout <= 20:
        parser.error("Timeout must be between 1 and 20 seconds.")
    try:
        results=verify(args.url, args.timeout)
    except ValueError as exc:
        print(json.dumps({"public_edge_pass":False,"error":str(exc),
                          "ready_for_commercial_launch":False}))
        return 2
    print(json.dumps(results,ensure_ascii=False,sort_keys=True))
    return 0 if results["public_edge_pass"] else 1


if __name__=="__main__":
    sys.exit(main())
