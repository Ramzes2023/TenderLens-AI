"""Procurement URL policy. DNS/proxy connection protection is a separate layer."""
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
import ipaddress
import re
import sys
import zlib
from functools import partial
from urllib.parse import urlsplit

import anyio
import httpx
import httpcore

from .http_transport import PublicIPBackend, PublicIPError, _bounded_close


class ConnectorTransportError(RuntimeError):
    def __init__(self, *, retryable=False):
        super().__init__('Connector transport failed.')
        self.retryable = retryable


def _is_public_ip_error(error):
    """HTTPX wraps HTTPCore errors; trust types in explicit causes only."""
    seen = set()
    while isinstance(error, BaseException) and id(error) not in seen:
        if isinstance(error, PublicIPError):
            return True
        seen.add(id(error))
        error = error.__cause__
    return False


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


def _validate_bounded_url(url, policy):
    # HTTPX exposes a decoded Unicode .host for an IDN even when the actual
    # origin's wire hostname is IDNA/Punycode. Match only the canonical
    # ASCII wire host against the explicit connector allowlist: this neither
    # permits lookalike hosts nor relaxes HTTPS, TLS, DNS or peer-IP controls.
    try:
        ascii_host = url.raw_host.decode('ascii').lower()
    except (AttributeError, UnicodeError):
        raise ConnectorTransportError() from None
    if (url.scheme != 'https' or ascii_host not in policy.hosts
            or url.userinfo or url.port not in (None, 443)):
        raise ConnectorTransportError()


class _RejectedProxyTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request):
        raise ConnectorTransportError()


class _PublicIPClient(httpx.AsyncClient):
    """Keep HTTPX configuration and route selection; protect direct TCP only."""

    def __init__(self, **kwargs):
        transport = kwargs.get('transport')
        mounts = kwargs.get('mounts') or {}
        if (transport is not None and type(transport) is not httpx.MockTransport
                or any(value is not None and type(value) is not httpx.MockTransport
                       for value in mounts.values())):
            raise ConnectorTransportError()
        super().__init__(**kwargs)

    async def aclose(self):
        await _bounded_close(super())

    async def __aexit__(self, exc_type, exc_value, traceback):
        # Use HTTPX's lifecycle implementation without calling ourselves again.
        class Exit:
            async def aclose(inner):
                await super(_PublicIPClient, self).__aexit__(exc_type, exc_value, traceback)
        await _bounded_close(Exit(), suppress_errors=exc_type is not None)

    def _init_transport(self, **kwargs):
        transport = super()._init_transport(**kwargs)
        if type(transport) is httpx.MockTransport:
            return transport
        # Fail closed if HTTPX changes the audited integration contract.
        if (type(transport) is not httpx.AsyncHTTPTransport
                or type(getattr(transport, '_pool', None)) is not httpcore.AsyncConnectionPool
                or not hasattr(transport._pool, '_network_backend')):
            raise ConnectorTransportError()
        transport._pool._network_backend = PublicIPBackend()
        return transport

    def _init_proxy_transport(self, proxy, **kwargs):
        # Let HTTPX retain its matching/NO_PROXY rules without constructing a
        # proxy pool (including SOCKS, which may have optional dependencies).
        return _RejectedProxyTransport()

    async def _send_single_request(self, request):
        # HTTPCore permits an extension to override TLS SNI. Keep verification
        # tied to the URL hostname even for hook/auth-generated requests.
        sni = request.extensions.get('sni_hostname')
        if sni is not None and sni != request.url.host:
            raise ConnectorTransportError()
        return await super()._send_single_request(request)


class _LimitedBoundedStream(httpx.AsyncByteStream):
    """Count wire bytes before any response consumer or decoder sees them."""

    def __init__(self, stream, response, max_bytes):
        self.stream = stream
        self.response = response
        self.max_bytes = max_bytes

    async def __aiter__(self):
        size = 0
        try:
            async for chunk in self.stream:
                await anyio.lowlevel.checkpoint()
                size += len(chunk)
                if size > self.max_bytes:
                    raise ConnectorTransportError()
                for offset in range(0, len(chunk), _LIVE_CHUNK_BYTES):
                    yield chunk[offset:offset + _LIVE_CHUNK_BYTES]
        except BaseException:
            await _close_live_response(self.response)
            raise

    async def aclose(self):
        await _bounded_close(self.stream, suppress_errors=sys.exception() is not None)


class BoundedClient(_PublicIPClient):
    async def _send_single_request(self, request):
        # Auth and request hooks can replace the URL after send() validates it.
        # Each auth exchange is a separate dispatch; hooks/URL changes are not.
        policy = _policy.get()
        _validate_bounded_url(request.url, policy)
        if policy.requests >= policy.max_requests:
            raise ConnectorTransportError()
        policy.requests += 1
        request.headers['accept-encoding'] = 'gzip, deflate, identity'
        response = await super()._send_single_request(request)
        response.stream = _LimitedBoundedStream(response.stream, response, policy.max_bytes)
        response.aiter_bytes = partial(_limited_live_bytes, response, max_bytes=policy.max_bytes)
        return response

    async def send(self, request, **kwargs):
        policy = _policy.get()
        _validate_bounded_url(request.url, policy)
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
            except BaseException:
                await _close_live_response(response)
                raise
            finally:
                if not response.is_closed:
                    await _close_live_response(response, suppress_errors=False)
        except (httpx.TransportError, OSError) as error:
            raise ConnectorTransportError(retryable=not _is_public_ip_error(error)) from error


def _validate_live_url(value):
    """Reject unsafe URL syntax and destinations without resolving DNS."""
    try:
        raw = str(value)
        if '\\' in raw or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in raw):
            raise ValueError()
        parts = urlsplit(raw)
        url = httpx.URL(raw)
        if (parts.scheme.lower() != 'https' or not parts.netloc or '@' in parts.netloc
                or url.userinfo or url.port not in (None, 443) or not url.host
                or parts.netloc.endswith(':')):
            raise ValueError()
        host = url.host.lower().rstrip('.')
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            labels = host.split('.')
            if (len(labels) < 2 or len(host) > 253
                    or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                           for label in labels)
                    or labels[-1] in {'localhost', 'local', 'internal', 'lan', 'home', 'intranet', 'localdomain'}
                    or labels[0] == 'localhost'
                    or re.fullmatch(r'[0-9.]+', host)
                    or all(re.fullmatch(r'(?:0x[0-9a-f]+|[0-9]+)', label) for label in labels)):
                raise ValueError()
        else:
            if not address.is_global or address.is_multicast:
                raise ValueError()
        return url
    except (ValueError, httpx.InvalidURL):
        raise ConnectorTransportError() from None


_LIVE_MAX_BYTES = 25 * 1024 * 1024
_LIVE_REQUEST_SECONDS = 180
_LIVE_CHUNK_BYTES = 64 * 1024
_live_request = ContextVar('live_request', default=None)


@contextmanager
def _live_deadline(deadline):
    # Absolute time survives redirects, auth exchanges and streamed reads.
    try:
        with anyio.fail_after(max(0, deadline - anyio.current_time())):
            if anyio.current_time() >= deadline:
                raise TimeoutError()
            yield
            if anyio.current_time() >= deadline:
                raise TimeoutError()
    except TimeoutError:
        raise httpx.TimeoutException('Live request exceeded its total time budget.') from None


async def _close_live_response(response, *, suppress_errors=True):
    await _bounded_close(response, suppress_errors=suppress_errors)


class _LimitedLiveStream(httpx.AsyncByteStream):
    """Bound wire bytes too, including callers using aiter_raw()."""

    def __init__(self, stream, deadline, response):
        self.stream = stream
        self.deadline = deadline
        self.response = response

    async def __aiter__(self):
        size = 0
        try:
            iterator = self.stream.__aiter__()
            while True:
                with _live_deadline(self.deadline):
                    try:
                        chunk = await iterator.__anext__()
                    except StopAsyncIteration:
                        break
                size += len(chunk)
                if size > _LIVE_MAX_BYTES:
                    raise ConnectorTransportError()
                for offset in range(0, len(chunk), _LIVE_CHUNK_BYTES):
                    yield chunk[offset:offset + _LIVE_CHUNK_BYTES]
        except BaseException:
            await _close_live_response(self.response)
            raise

    async def aclose(self):
        await _bounded_close(self.stream, suppress_errors=sys.exception() is not None)


def _live_encoding(response):
    encoding = response.headers.get('content-encoding', 'identity').strip().lower()
    if encoding not in {'identity', 'gzip', 'deflate'}:
        raise ConnectorTransportError()
    return encoding


async def _limited_live_bytes(response, chunk_size=None, *, max_bytes=_LIVE_MAX_BYTES):
    # No HTTPX decoding or zlib flush: every decompression operation has a
    # hard output bound, including draining internally buffered output.
    output_size = _LIVE_CHUNK_BYTES if chunk_size is None else min(chunk_size, _LIVE_CHUNK_BYTES)
    if output_size <= 0:
        raise ValueError('chunk_size must be positive')
    if hasattr(response, '_content'):
        for offset in range(0, len(response._content), output_size):
            yield response._content[offset:offset + output_size]
        return
    size, prefix = 0, b''
    decoder = None
    deadline = getattr(response.stream, 'deadline', None)
    try:
        encoding = _live_encoding(response)
        if encoding == 'gzip':
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        async for raw in response.aiter_raw():
            if encoding == 'deflate' and decoder is None:
                # Two-byte RFC1950 header detection avoids retaining input for
                # an unbounded replay, or retrying corrupt wrapped data as raw.
                take = min(2 - len(prefix), len(raw))
                prefix += raw[:take]
                raw = raw[take:]
                if len(prefix) < 2:
                    continue
                cmf, flg = prefix
                wrapped = cmf & 15 == 8 and cmf >> 4 <= 7 and (cmf * 256 + flg) % 31 == 0
                decoder = zlib.decompressobj(zlib.MAX_WBITS if wrapped else -zlib.MAX_WBITS)
                raw = prefix + raw
                prefix = b''
            pending = raw
            while True:
                with _live_deadline(deadline) if deadline is not None else nullcontext():
                    await anyio.lowlevel.checkpoint()
                    if decoder is None:
                        decoded, pending = pending, b''
                    else:
                        if decoder.eof and pending:
                            if encoding != 'gzip':
                                raise ConnectorTransportError()
                            # Each concatenated gzip member checks CRC/size.
                            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
                        decoded = decoder.decompress(pending, _LIVE_CHUNK_BYTES)
                        pending = decoder.unused_data if decoder.eof else decoder.unconsumed_tail
                    size += len(decoded)
                    if size > max_bytes:
                        raise ConnectorTransportError()
                for offset in range(0, len(decoded), output_size):
                    yield decoded[offset:offset + output_size]
                if not pending and (decoder is None or decoder.eof or len(decoded) < _LIVE_CHUNK_BYTES):
                    break
        if encoding != 'identity' and (decoder is None or not decoder.eof):
            raise ConnectorTransportError()
    except zlib.error:
        await _close_live_response(response)
        raise ConnectorTransportError() from None
    except BaseException:
        await _close_live_response(response)
        raise


class LiveClient(_PublicIPClient):
    """Manual redirects, retaining HTTPX transport, auth and TLS configuration."""

    async def send(self, request, **kwargs):
        deadline = anyio.current_time() + _LIVE_REQUEST_SECONDS
        responses = []
        token = _live_request.set((deadline, responses))
        try:
            with _live_deadline(deadline):
                return await super().send(request, **kwargs)
        except BaseException:
            for response in responses:
                await _close_live_response(response)
            raise
        finally:
            _live_request.reset(token)

    def build_request(self, method, url, **kwargs):
        # Validate before HTTPX can normalize malformed input.
        _validate_live_url(url)
        return super().build_request(method, url, **kwargs)

    async def _send_single_request(self, request):
        # Runs after request hooks and for auth-generated requests as well.
        _validate_live_url(request.url)
        request.headers['accept-encoding'] = 'gzip, deflate, identity'
        response = await super()._send_single_request(request)
        deadline, responses = _live_request.get()
        responses.append(response)
        response.stream = _LimitedLiveStream(response.stream, deadline, response)
        response.aiter_bytes = partial(_limited_live_bytes, response)
        _live_encoding(response)
        return response

    def _redirect_url(self, request, response):
        location = response.headers['location']
        try:
            parts = urlsplit(location)
            if (not location or '\\' in location
                    or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in location)
                    or (parts.scheme and not parts.netloc)):
                raise ValueError()
            if parts.netloc:
                _validate_live_url('https:' + location if location.startswith('//') else location)
            return _validate_live_url(request.url.join(location))
        except (ValueError, httpx.InvalidURL):
            raise ConnectorTransportError() from None

    async def _send_handling_redirects(self, request, follow_redirects, history):
        while True:
            if len(history) > min(self.max_redirects, 5):
                raise ConnectorTransportError()
            for hook in self._event_hooks['request']:
                await hook(request)
            response = await self._send_single_request(request)
            try:
                for hook in self._event_hooks['response']:
                    await hook(response)
                response.history = list(history)
                if not response.has_redirect_location:
                    return response
                next_request = self._build_redirect_request(request, response)
                if request.url.host != next_request.url.host:
                    for header in ('authorization', 'cookie', 'referer'):
                        next_request.headers.pop(header, None)
                history = history + [response]
                if not follow_redirects:
                    response.next_request = next_request
                    return response
                await _close_live_response(response, suppress_errors=False)
                request = next_request
            except BaseException:
                await _close_live_response(response)
                raise


def source_client(**kwargs):
    if _policy.get() is None:
        return LiveClient(**kwargs)
    kwargs['follow_redirects'] = False
    kwargs['timeout'] = min(float(kwargs.get('timeout', 30)), 30)
    return BoundedClient(**kwargs)


def page_limit(existing):
    policy = _policy.get()
    return min(existing, policy.max_requests) if policy is not None else existing
