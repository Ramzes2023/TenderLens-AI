"""Fixed-field transport evidence; never log exception messages or request data."""
import ssl

import httpx


def transport_failure(error):
    pending = [error]
    seen = set()
    kinds = []
    category = "unclassified"
    verify_code = None
    while pending and len(seen) < 16:
        item = pending.pop(0)
        if id(item) in seen:
            continue
        seen.add(id(item))
        kinds.append(type(item).__name__)
        if isinstance(item, ssl.SSLCertVerificationError):
            category = "tls_certificate_verification"
            if type(item.verify_code) is int:
                verify_code = item.verify_code
        elif category != "tls_certificate_verification":
            if isinstance(item, httpx.ReadTimeout):
                category = "response_read_timeout"
            elif isinstance(item, httpx.ReadError):
                category = "response_read_failure"
            elif isinstance(item, httpx.ConnectTimeout):
                category = "connection_or_tls_handshake_timeout"
            elif isinstance(item, httpx.ConnectError) and category == "unclassified":
                category = "connection_failure_unspecified"
        for nested in (item.__cause__, item.__context__):
            if nested is not None:
                pending.append(nested)
    return {"failure_class": type(error).__name__, "cause_types": kinds[1:],
            "category": category, "certificate_verify_code": verify_code,
            "retryable": bool(getattr(error, "retryable", False))}
