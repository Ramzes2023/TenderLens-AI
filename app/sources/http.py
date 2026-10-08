"""Worker-only HTTP policy; live adapter behavior remains compatible."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

import httpx


class ConnectorTransportError(RuntimeError):
    def __init__(self, *, retryable=False):
        super().__init__('Connector transport failed.')
        self.retryable = retryable


@dataclass
class FetchPolicy:
    hosts: frozenset[str]
    max_requests: int
    requests: int = 0
    max_bytes: int = 25 * 1024 * 1024


_policy = ContextVar('connector_fetch_policy', default=None)


@contextmanager
def bounded_fetch(policy):
    token = _policy.set(policy)
    try:
        yield
    finally:
        _policy.reset(token)


class BoundedClient(httpx.AsyncClient):
    async def send(self, request, **kwargs):
        policy = _policy.get()
        url = request.url
        if (url.scheme != 'https' or url.host not in policy.hosts
                or url.userinfo or url.port not in (None, 443)):
            raise ConnectorTransportError()
        policy.requests += 1
        if policy.requests > policy.max_requests:
            raise ConnectorTransportError()
        kwargs.update(stream=True, follow_redirects=False)
        try:
            response = await super().send(request, **kwargs)
            try:
                status = response.status_code
                if status == 429 or status == 408 or 500 <= status <= 599:
                    raise ConnectorTransportError(retryable=True)
                if not 200 <= status < 300:
                    raise ConnectorTransportError()
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > policy.max_bytes:
                        raise ConnectorTransportError()
                    chunks.append(chunk)
                response._content = b''.join(chunks)
                return response
            finally:
                await response.aclose()
        except (httpx.TransportError, OSError):
            raise ConnectorTransportError(retryable=True) from None


def source_client(**kwargs):
    if _policy.get() is None:
        return httpx.AsyncClient(**kwargs)
    kwargs['follow_redirects'] = False
    kwargs['timeout'] = min(float(kwargs.get('timeout', 30)), 30)
    return BoundedClient(**kwargs)


def page_limit(existing):
    policy = _policy.get()
    return min(existing, policy.max_requests) if policy is not None else existing
