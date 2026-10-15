"""Narrow adapter error contract; parser/configuration SourceError stays permanent."""
import ssl

import httpx

from .eis_rss import SourceError
from .http import ConnectorTransportError, _is_public_ip_error


class SourceTransportError(SourceError):
    """A sanitized, explicitly transient retrieval failure."""


def transient_transport(error):
    if _is_public_ip_error(error):
        return False
    seen = set()
    cause = error
    while isinstance(cause, BaseException) and id(cause) not in seen:
        if isinstance(cause, ssl.SSLError):
            return False
        seen.add(id(cause))
        cause = cause.__cause__
    # Unknown HTTP/network/OS errors are deliberately fail-closed. The existing
    # transport layer may explicitly mark a known temporary failure retryable.
    if isinstance(error, ConnectorTransportError) and error.__cause__ is not None:
        return error.retryable is True and transient_transport(error.__cause__)
    return (isinstance(error, httpx.TimeoutException)
            or isinstance(error, ConnectorTransportError) and error.retryable is True)
