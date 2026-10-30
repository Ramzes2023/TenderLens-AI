"""Read-only bounded DNS/TCP/TLS/HEAD comparison; never a release proof.

Standard library only, fixed origins, no proxy, credentials, redirects or bodies.
Suitable for the VPS host and a mount-free copy of the exact Worker image.
"""
from __future__ import annotations

import concurrent.futures
import json
import socket
import ssl
import time
from pathlib import Path


def probe(host: str, family: int) -> dict:
    result = {"host": host, "family": 4 if family == socket.AF_INET else 6}
    try:
        addresses = socket.getaddrinfo(host, 443, family, socket.SOCK_STREAM)
    except OSError as exc:
        return {**result, "dns": type(exc).__name__}
    result["dns"] = "resolved"
    result["address_count"] = len({entry[4][0] for entry in addresses})
    # One address per family, no retries. This is a bounded route observation.
    af, kind, proto, _, address = addresses[0]
    start = time.monotonic()
    try:
        with socket.socket(af, kind, proto) as connection:
            connection.settimeout(5)
            connection.connect(address)
            result["tcp"] = "connected"
            context = ssl.create_default_context()
            ca = Path("/app/certs/russian_trusted_root_ca_pem.crt")
            if host == "zakupki.gov.ru" and ca.is_file():
                # Exact Worker image supplies the existing scoped CA; no downloads.
                context.load_verify_locations(cafile=str(ca))
                result["worker_ca"] = "loaded"
            with context.wrap_socket(connection, server_hostname=host) as tls:
                result["tls"] = "verified"
                tls.sendall((f"HEAD / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n").encode("ascii"))
                result["http_status_line"] = tls.recv(256).split(b"\r\n")[0].decode("ascii", "replace")
    except (OSError, ValueError) as exc:
        stage = "http_error" if result.get("tls") else "tls_error" if result.get("tcp") else "tcp_error"
        result[stage] = type(exc).__name__
        if isinstance(exc, OSError):
            result["errno"] = exc.errno
    result["elapsed_seconds"] = round(time.monotonic() - start, 2)
    return result


def main() -> None:
    targets = [(host, family) for host in ("zakupki.gov.ru", "example.com")
               for family in (socket.AF_INET, socket.AF_INET6)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        for result in executor.map(lambda pair: probe(*pair), targets):
            print(json.dumps(result, sort_keys=True), flush=True)
    print("EIS_ROUTE_COMPARISON=OBSERVATION_ONLY_NOT_RELEASE_PROOF")


if __name__ == "__main__":
    main()
