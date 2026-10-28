"""Fixed diagnostic enums for blocked live probes; never render error text."""
import socket
import ssl
import httpx


def transport_category(error):
    seen = set()
    category = 'unclassified'
    while isinstance(error, BaseException) and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, ssl.SSLCertVerificationError):
            return 'tls_certificate'
        if isinstance(error, socket.gaierror):
            return 'dns'
        if isinstance(error, (httpx.TimeoutException, TimeoutError)):
            category = 'timeout'
        elif category == 'unclassified' and isinstance(error, (httpx.ConnectError, ConnectionError)):
            category = 'connect'
        error = error.__cause__ or error.__context__
    return category


def worker_failure_code(value):
    allowed = {'handler_error', 'permanent_failure', 'lease_expired', 'invalid_result'}
    return value if type(value) is str and value in allowed else 'unclassified'
