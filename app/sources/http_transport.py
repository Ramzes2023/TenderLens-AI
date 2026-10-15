"""Public-IP TCP protection for source clients using HTTPCore 1.0.9.

Resolvers return the complete sequence of numeric A/AAAA addresses, never a
filtered subset. Each connection resolves afresh before any TCP attempt.
"""
from collections.abc import Awaitable, Callable, Sequence
import ipaddress
from contextvars import ContextVar
import socket

import anyio
import httpcore
from httpcore._backends.auto import AutoBackend
from httpcore._backends.base import AsyncNetworkBackend, AsyncNetworkStream, SOCKET_OPTION


Resolver = Callable[[str, int], Awaitable[Sequence[str]]]


_CLEANUP_SECONDS = 1.0
_cleanup_deadline = ContextVar('http_cleanup_deadline', default=None)


async def _bounded_close(resource, *, suppress_errors=False):
    """Share one finite, shielded budget across nested close operations."""
    deadline = _cleanup_deadline.get()
    if deadline is None:
        deadline = anyio.current_time() + _CLEANUP_SECONDS
    token = _cleanup_deadline.set(deadline)
    try:
        with anyio.move_on_after(max(0, deadline - anyio.current_time()), shield=True):
            try:
                await resource.aclose()
            except Exception:
                if not suppress_errors:
                    raise
    finally:
        _cleanup_deadline.reset(token)


class PublicIPError(httpcore.ConnectError):
    """The destination or actual peer cannot be proven safe."""


async def resolve_addresses(host: str, port: int) -> Sequence[str]:
    records = await anyio.getaddrinfo(
        host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    addresses = []
    for family, kind, protocol, _, address in records:
        if family not in (socket.AF_INET, socket.AF_INET6):
            raise PublicIPError('Unexpected DNS address family')
        addresses.append(address[0])
    return addresses


def _public_address(value: str):
    try:
        if not isinstance(value, str) or '%' in value:
            raise ValueError()
        address = ipaddress.ip_address(value)
        effective = address.ipv4_mapped if address.version == 6 else None
        effective = effective or address
        if (not effective.is_global or effective.is_multicast
                or effective.is_reserved or effective.is_unspecified
                or effective.is_loopback or effective.is_link_local):
            raise ValueError()
        if effective.version == 4 and any(
            effective in ipaddress.ip_network(network)
            for network in ('192.0.0.0/24', '192.88.99.0/24')
        ):
            raise ValueError()
        if address.version == 6 and address.ipv4_mapped is None:
            # Fail closed on translation/tunnelling and non-global-unicast space.
            if (address not in ipaddress.ip_network('2000::/3')
                    or address.sixtofour is not None or address.teredo is not None
                    or address in ipaddress.ip_network('2001::/23')
                    or address in ipaddress.ip_network('3fff::/20')):
                raise ValueError()
        return address
    except (ValueError, TypeError):
        raise PublicIPError('Unapproved IP address') from None


class _PublicIPStream(AsyncNetworkStream):
    """Own the validated stream through TLS upgrade and cancellation cleanup."""

    def __init__(self, stream: AsyncNetworkStream):
        self._stream = stream
        self._closed = False

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return await self._stream.read(max_bytes, timeout)

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        await self._stream.write(buffer, timeout)

    def get_extra_info(self, info: str):
        return self._stream.get_extra_info(info)

    async def aclose(self) -> None:
        if not self._closed:
            self._closed = True
            await _bounded_close(self._stream)

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        try:
            self._stream = await self._stream.start_tls(
                ssl_context, server_hostname=server_hostname, timeout=timeout,
            )
        except BaseException:
            try:
                await self.aclose()
            except Exception:
                # Cleanup must not replace the handshake failure or cancellation.
                pass
            raise
        return self


class PublicIPBackend(AsyncNetworkBackend):
    def __init__(self, *, resolver: Resolver = resolve_addresses,
                 tcp_backend: AsyncNetworkBackend | None = None):
        self._resolver = resolver
        self._tcp_backend = tcp_backend if tcp_backend is not None else AutoBackend()

    async def connect_tcp(
        self, host: str, port: int, timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Sequence[SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream:
        try:
            with anyio.fail_after(timeout):
                try:
                    raw = await self._resolver(host, port)
                except OSError as exc:
                    raise httpcore.ConnectError('DNS resolution failed') from exc
                if (not isinstance(raw, Sequence) or not raw
                        or isinstance(raw, (str, bytes))):
                    raise PublicIPError('Empty or invalid DNS result')
                # Validate the whole answer before connecting, including late entries.
                addresses = list(dict.fromkeys(_public_address(item) for item in raw))
                options = tuple(socket_options) if socket_options is not None else None
                last_error = None
                for address in addresses:
                    remaining = anyio.current_effective_deadline() - anyio.current_time()
                    try:
                        stream = await self._tcp_backend.connect_tcp(
                            str(address), port,
                            timeout=None if timeout is None else max(0.0, remaining),
                            local_address=local_address, socket_options=options,
                        )
                    except PublicIPError:
                        raise
                    except (httpcore.ConnectError, httpcore.ConnectTimeout, OSError) as exc:
                        last_error = exc
                        continue
                    try:
                        peer = stream.get_extra_info('server_addr')
                        if (not isinstance(peer, tuple) or len(peer) < 2
                                or _public_address(peer[0]) != address or peer[1] != port):
                            raise PublicIPError('TCP peer does not match approved destination')
                        await anyio.lowlevel.checkpoint()
                    except BaseException:
                        await _bounded_close(stream, suppress_errors=True)
                        raise
                    # HTTPCore still supplies the original origin hostname to TLS.
                    return _PublicIPStream(stream)
                if isinstance(last_error, OSError):
                    raise httpcore.ConnectError('TCP connection failed') from last_error
                raise last_error or PublicIPError('No approved addresses')
        except TimeoutError as exc:
            raise httpcore.ConnectTimeout('Connection deadline exceeded') from exc

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise PublicIPError('Unix sockets are outside the public IP policy')

    async def sleep(self, seconds: float) -> None:
        await self._tcp_backend.sleep(seconds)
