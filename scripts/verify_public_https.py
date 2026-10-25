"""Non-destructive public HTTPS read-only launch probe.

Never deploys, never fetches private endpoints or credentials. Passing this
network smoke is only an HTTPS edge check; billing, source-to-user evidence and
production readiness require *separate* acceptance.
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import ssl
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


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
    return hostname, 443


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
        result["dns"] = "PASS"
        # HTTPS must validate the remote certificate with normal trust anchors.
        context = ssl.create_default_context()
        with urlopen(Request(f"https://{host}/", headers={
                "User-Agent": "VALYQON-ReleaseReadiness/1.0"
        }), context=context, timeout=timeout) as response:
            result["tls"] = "PASS"
            payload = response.read(131072).decode("utf-8",errors="replace")
            result["homepage"] = ("PASS" if response.status==200
                                  and "VALYQON" in payload.upper() else "FAIL")
            headers = response.headers
            result["security_headers"] = ("PASS" if "max-age=" in
                headers.get("Strict-Transport-Security","").lower()
                and headers.get("X-Content-Type-Options","").lower()=="nosniff"
                else "FAIL")
        with urlopen(Request(f"https://{host}/health", headers={
                "User-Agent": "VALYQON-ReleaseReadiness/1.0"
        }), context=context, timeout=timeout) as response:
            data = response.read(16384)
            result["health"] = ("PASS" if response.status==200
                and isinstance(json.loads(data),dict) else "FAIL")
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
