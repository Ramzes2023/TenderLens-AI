"""Official TEK-Torg public API availability only, no procurement ingestion.

The platform publishes https://api.tektorg.ru and /procedures/wsdl in
its API documentation. Fixed read-only GETs cannot prove any source card,
authorized customer scoring, or Telegram delivery.
No cookies, credentials, redirects, proxies, insecure TLS or arbitrary URLs.
"""
from __future__ import annotations

import json
import ssl
import xml.etree.ElementTree as ET

from scripts.ru_trusted_live_probe import (
    VerifiedIPHTTPSConnection, checked_ips,
)

HOST = "api.tektorg.ru"
MAX_BYTES = 512_000
# Never take public network paths or response endpoints from user content.
TARGETS = {
    "directory": ("/", "json"),
    "sections": ("/lists/sections", "json"),
    "procedures_wsdl": ("/procedures/wsdl", "xml"),
}


def authentic_document(kind: str, payload: bytes, media_type: str) -> bool:
    """Media shape is an API *availability* signal, never a tender count."""
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_BYTES:
        return False
    if type(media_type) is not str:
        return False
    if kind == "json":
        if "json" not in media_type.lower():
            return False
        try:
            item = json.loads(payload)
            return type(item) in (list, dict)
        except (ValueError, UnicodeDecodeError):
            return False
    if kind == "xml":
        upper = payload.upper()
        if (not any(x in media_type.lower() for x in ("xml", "wsdl"))
                or b"<!DOCTYPE" in upper or b"<!ENTITY" in upper):
            return False
        try:
            root = ET.fromstring(payload)
            return root.tag.rsplit("}", 1)[-1] == "definitions"
        except ET.ParseError:
            return False
    return False


def observe(label: str, *, resolver=checked_ips, connection=VerifiedIPHTTPSConnection):
    if type(label) is not str or label not in TARGETS:
        raise ValueError("Only three documented immutable TEK-Torg API paths allowed")
    path, kind = TARGETS[label]
    # Validate ALL DNS replies as public before attempting even one TCP
    # connection; SNI and TLS hostname remain the original allowlisted host.
    ips = resolver(HOST)
    last_error = "UNAVAILABLE"
    for ip in ips[:2]:
        conn = connection(HOST, ip)
        try:
            conn.request("GET", path, headers={
                "Accept": "application/json,application/xml,text/xml",
                "Accept-Encoding": "identity",
                "User-Agent": "VALYQON-ReadOnlyOfficialAPI/1.0",
                "Connection": "close",
            })
            response = conn.getresponse()
            status = int(response.status)
            if status != 200:
                # Never follow redirects, auto-solve challenges, or use an
                # HTTP 2xx as proof that a single procurement was fetched.
                return {"status": "HTTP_STATUS_ONLY", "http_status": status}
            data = response.read(MAX_BYTES + 1)
            mime = response.getheader("content-type", "")
            return {
                "status": "API_DOCUMENT_VISIBLE_ONLY"
                          if authentic_document(kind, data, mime)
                          else "HTTP_200_NON_API_DOCUMENT",
                "http_status": 200,
                "bytes": len(data) if len(data) <= MAX_BYTES else None,
            }
        except (OSError, TimeoutError, ssl.SSLError) as exc:
            last_error = type(exc).__name__
        finally:
            conn.close()
    return {"status": "NETWORK_BLOCKED", "failure_class": last_error}


def report():
    result = {}
    for key in TARGETS:
        try:
            result[key] = observe(key)
        except (OSError, ValueError, ssl.SSLError) as exc:
            result[key] = {
                "status": "DNS_OR_POLICY_BLOCKED",
                "failure_class": type(exc).__name__,
            }
    return result


def main():
    print("RU_TEK_OFFICIAL_API_READONLY=" + json.dumps(report(), sort_keys=True))
    print("RU_TEK_VERIFIED_NATIVE_TENDER_DETAILS=0")
    print("RU_TEK_WORKER_SQL_ACCEPTED=NO")
    print("RU_TEK_CUSTOMER_NOTIFIED=NO")
    print("PRODUCTION_CHANGED=NO")
    # Observational diagnostics never make source acceptance green:
    # the separate strict, actual original -> Worker -> SQL CI is mandatory.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
