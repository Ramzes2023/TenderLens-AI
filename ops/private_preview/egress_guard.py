"""Preview-process network allowlist; installed before application startup.

The publishing bridge must be non-internal. Do not rely on absent masquerading
alone for API egress isolation. Audit hooks apply to all Python threads and cannot
be removed. Only the isolated DB, SMTP capture and loopback may be contacted.
"""
import ipaddress
import socket
import sys

_installed = False


def make_guard(endpoints):
    allowed = frozenset(endpoints)

    def guard(event, args):
        if event == "socket.getaddrinfo":
            host = args[0]
            if host in (None, "db", "mailpit", "localhost"):
                return
            try:
                if ipaddress.ip_address(host).is_loopback:
                    return
            except (ValueError, TypeError):
                pass
            raise PermissionError("Private preview external DNS is disabled")
        if event not in ("socket.connect", "socket.sendto"):
            return
        address = args[1] if event == "socket.connect" else args[-1]
        if isinstance(address, tuple) and len(address) >= 2:
            host, port = address[:2]
            try:
                if ipaddress.ip_address(host).is_loopback:
                    return
            except (ValueError, TypeError):
                pass
            if event == "socket.connect" and (host, port) in allowed:
                return
        raise PermissionError("Private preview external connections are disabled")

    return guard


def install():
    global _installed
    if _installed:
        return
    endpoints = set()
    # Fail startup if either Docker service cannot be resolved. No fallback IPs.
    for host, port in (("db", 5432), ("mailpit", 1025)):
        for record in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
            endpoints.add((record[4][0], port))
    sys.addaudithook(make_guard(endpoints))
    _installed = True
