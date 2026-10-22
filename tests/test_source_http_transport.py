"""Offline public-IP backend contract tests, with no DNS or TCP access."""
import asyncio
import socket
import ssl
from unittest.mock import patch

import anyio
import httpcore
import pytest
from httpcore._backends.base import AsyncNetworkBackend, AsyncNetworkStream

from app.sources.http_transport import PublicIPBackend, PublicIPError, resolve_addresses


@pytest.fixture(autouse=True)
def offline():
    # Windows builds asyncio's internal wakeup socketpair when creating a loop.
    # Build it before the network guard; all test activity runs under the guard.
    loop = asyncio.new_event_loop()
    run = asyncio.run
    with patch('socket.getaddrinfo', side_effect=AssertionError('Real DNS forbidden')), \
         patch('socket.socket.connect', side_effect=AssertionError('Real TCP forbidden')), \
         patch('asyncio.run', side_effect=lambda coro: run(coro, loop_factory=lambda: loop)):
        try:
            yield
        finally:
            if not loop.is_closed():
                loop.close()


class Stream(AsyncNetworkStream):
    def __init__(self, peer):
        self.peer = peer
        self.closed = 0
        self.tls = None

    def get_extra_info(self, key):
        assert key == 'server_addr'
        return self.peer

    async def aclose(self):
        await anyio.lowlevel.checkpoint()
        self.closed += 1

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        self.tls = (server_hostname, timeout)
        return self


class TCP(AsyncNetworkBackend):
    def __init__(self, outcomes=()):
        self.outcomes = list(outcomes)
        self.calls = []

    async def connect_tcp(self, host, port, **kwargs):
        self.calls.append((host, port, kwargs))
        outcome = self.outcomes.pop(0) if self.outcomes else Stream((host, port))
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def backend(addresses, tcp=None):
    calls = []

    async def resolver(host, port):
        calls.append((host, port))
        return addresses

    tcp = tcp or TCP()
    return PublicIPBackend(resolver=resolver, tcp_backend=tcp), tcp, calls


@pytest.mark.parametrize('address', ['8.8.8.8', '2606:4700:4700::1111', '::ffff:8.8.8.8'])
def test_numeric_tcp_and_original_tls_hostname(address):
    async def run():
        subject, tcp, resolutions = backend([address])
        stream = await subject.connect_tcp('origin.example', 443, timeout=5,
                                           local_address='0.0.0.0',
                                           socket_options=[(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)])
        assert resolutions == [('origin.example', 443)]
        import ipaddress
        assert tcp.calls[0][0] == str(ipaddress.ip_address(address))
        assert 0 < tcp.calls[0][2]['timeout'] <= 5
        assert tcp.calls[0][2]['local_address'] == '0.0.0.0'
        assert tcp.calls[0][2]['socket_options'] == ((socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),)
        # Exercise the real HTTPCore connection path below as well.
        assert await stream.start_tls(ssl.create_default_context(), 'origin.example', 3) is stream
        assert stream._stream.tls == ('origin.example', 3)
        await stream.aclose()
        assert stream._stream.closed == 1
    asyncio.run(run())


@pytest.mark.parametrize('layer', ['httpx', 'bounded', 'handler', 'handler_live'])
@pytest.mark.parametrize('failure', ['blocked_dns', 'peer_mismatch', 'connection', 'timeout', 'dns_failure'])
def test_public_ip_failure_classification_end_to_end(layer, failure):
    from types import SimpleNamespace
    import httpx
    from app.jobs.worker import PermanentJobError, RetryableJobError
    from app.sources.http import BoundedClient, ConnectorTransportError, FetchPolicy, LiveClient, bounded_fetch
    from app.sources.ingestion import ConnectorSyncHandler, SYSTEM_SCOPE, connector_version
    from app.sources.registry import SourceRegistration, SourceRegistry

    blocked = failure in {'blocked_dns', 'peer_mismatch'}
    raw = Stream(('1.1.1.1', 443))
    outcomes = {
        'peer_mismatch': raw,
        'connection': httpcore.ConnectError('ordinary connection failure'),
        'timeout': httpcore.ConnectTimeout('ordinary timeout'),
    }
    subject, tcp, resolutions = backend(
        ['8.8.8.8', '127.0.0.1'] if failure == 'blocked_dns' else ['8.8.8.8'],
        TCP([outcomes.get(failure, raw)]),
    )
    if failure == 'dns_failure':
        async def resolver(host, port):
            resolutions.append((host, port))
            raise socket.gaierror('ordinary DNS failure')
        subject._resolver = resolver

    class Source:
        name = 'ted'

        async def fetch(self, limit):
            client_type = LiveClient if layer in {'httpx', 'handler_live'} else BoundedClient
            async with client_type(trust_env=False) as client:
                await client.get('https://api.ted.europa.eu/feed')

    async def run():
        with bounded_fetch(FetchPolicy(frozenset({'api.ted.europa.eu'}), 1)):
            await Source().fetch(1)

    with patch('app.sources.http.PublicIPBackend', return_value=subject):
        if layer.startswith('handler'):
            registry = SourceRegistry([SourceRegistration('ted', 'ted', Source())])
            handler = ConnectorSyncHandler(SimpleNamespace(registry=registry), None)
            payload = {'schema': 1, 'source_id': 'ted', 'sync_window': '2026-10-08T12Z',
                       'connector_version': connector_version('ted')}
            with pytest.raises(PermanentJobError if blocked else RetryableJobError):
                handler(SimpleNamespace(job=SimpleNamespace(scope=SYSTEM_SCOPE)), payload)
        else:
            expected = (ConnectorTransportError if layer == 'bounded' else
                        httpx.ConnectTimeout if failure == 'timeout' else httpx.ConnectError)
            with pytest.raises(expected) as caught:
                asyncio.run(run())
            if layer == 'bounded':
                assert caught.value.retryable is not blocked
            else:
                # Actual HTTPX mapping retains the original HTTPCore exception.
                assert isinstance(caught.value.__cause__, httpcore.ConnectError if failure != 'timeout'
                                  else httpcore.ConnectTimeout)
                assert isinstance(caught.value.__cause__, PublicIPError) is blocked
    assert resolutions == [('api.ted.europa.eu', 443)]
    assert len(tcp.calls) == (0 if failure in {'blocked_dns', 'dns_failure'} else 1)
    if failure == 'peer_mismatch':
        assert raw.closed == 1


def test_public_ip_cause_detection_is_typed_and_cycle_safe():
    import httpx
    from app.sources.http import _is_public_ip_error

    genuine = PublicIPError('blocked')
    wrapper = httpx.ConnectError('wrapped')
    wrapper.__cause__ = RuntimeError('intermediate')
    wrapper.__cause__.__cause__ = genuine
    assert _is_public_ip_error(wrapper)
    ordinary = httpx.ConnectError('PublicIPError: unapproved IP address')
    ordinary.__context__ = genuine
    assert not _is_public_ip_error(ordinary)
    ordinary.__cause__ = RuntimeError('cycle')
    ordinary.__cause__.__cause__ = ordinary
    assert not _is_public_ip_error(ordinary)


@pytest.mark.parametrize('address', [
    '127.0.0.1', '10.0.0.1', '172.16.0.1', '192.168.1.1',
    '169.254.169.254', '100.100.100.200', '100.64.0.1', '0.0.0.0',
    '192.0.2.1', '198.18.0.1', '224.0.0.1', '255.255.255.255',
    '192.0.0.9', '192.88.99.1', '2001:3::1', '3fff::1',
    '::', '::1', 'fc00::1', 'fe80::1', 'ff02::1', '2001:db8::1',
    '::ffff:127.0.0.1', '::ffff:169.254.169.254', '::ffff:10.0.0.1',
    '64:ff9b::a00:1', '2002:0808:0808::1', '2001:0::1',
    '2606:4700::1%eth0', 'garbage', '', None,
])
def test_entire_mixed_answer_rejected_before_tcp(address):
    async def run():
        subject, tcp, _ = backend(['8.8.8.8', address])
        with pytest.raises(PublicIPError):
            await subject.connect_tcp('origin.example', 443)
        assert tcp.calls == []
    asyncio.run(run())


@pytest.mark.parametrize('addresses', [[], None, '8.8.8.8', 42, {'8.8.8.8'}])
def test_uncertain_answer_fails_closed(addresses):
    async def run():
        subject, tcp, _ = backend(addresses)
        with pytest.raises(PublicIPError):
            await subject.connect_tcp('origin.example', 443)
        assert not tcp.calls
    asyncio.run(run())


def test_fallback_and_deduplication():
    async def run():
        tcp = TCP([httpcore.ConnectError('unreachable')])
        subject, _, _ = backend(['2606:4700:4700::1111'] * 2 + ['8.8.8.8'], tcp)
        stream = await subject.connect_tcp('origin.example', 443)
        assert [call[0] for call in tcp.calls] == ['2606:4700:4700::1111', '8.8.8.8']
        assert all(call[2]['timeout'] is None for call in tcp.calls)
        await stream.aclose()
    asyncio.run(run())


def test_dns_rebinding_between_connections():
    async def run():
        answers = iter([['8.8.8.8'], ['169.254.169.254']])
        async def resolver(host, port):
            return next(answers)
        tcp = TCP()
        subject = PublicIPBackend(resolver=resolver, tcp_backend=tcp)
        stream = await subject.connect_tcp('origin.example', 443)
        await stream.aclose()
        with pytest.raises(PublicIPError):
            await subject.connect_tcp('origin.example', 443)
        assert len(tcp.calls) == 1
        assert stream._stream.closed == 1
    asyncio.run(run())


@pytest.mark.parametrize('peer', [None, ('1.1.1.1', 443), ('8.8.8.8', 80),
                                  ('127.0.0.1', 443), ('bad', 443)])
def test_peer_mismatch_closes_without_fallback(peer):
    async def run():
        stream = Stream(peer)
        tcp = TCP([stream])
        subject, _, _ = backend(['8.8.8.8', '1.1.1.1'], tcp)
        with pytest.raises(PublicIPError):
            await subject.connect_tcp('origin.example', 443)
        assert stream.closed == 1
        assert len(tcp.calls) == 1
    asyncio.run(run())


def test_resolver_uses_all_a_and_aaaa():
    async def fake(host, port, **kwargs):
        assert kwargs == dict(family=socket.AF_UNSPEC, type=socket.SOCK_STREAM,
                              proto=socket.IPPROTO_TCP)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', port)),
                (socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('2606:4700::1111', port, 0, 0))]
    async def run():
        with patch('anyio.getaddrinfo', fake):
            assert await resolve_addresses('origin.example', 443) == ['8.8.8.8', '2606:4700::1111']
    asyncio.run(run())


def test_dns_timeout_and_cancellation_propagate():
    async def run():
        started = anyio.Event()
        async def resolver(host, port):
            started.set()
            await anyio.sleep_forever()
        tcp = TCP()
        subject = PublicIPBackend(resolver=resolver, tcp_backend=tcp)
        with pytest.raises(httpcore.ConnectTimeout):
            await subject.connect_tcp('origin.example', 443, timeout=0.01)
        task = asyncio.create_task(subject.connect_tcp('origin.example', 443))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not tcp.calls
    asyncio.run(run())


def test_cancellation_after_tcp_closes_stream():
    async def run():
        stream = Stream(('8.8.8.8', 443))
        class CancellingTCP(TCP):
            async def connect_tcp(self, *args, **kwargs):
                scope.cancel()
                return stream
        subject, _, _ = backend(['8.8.8.8'], CancellingTCP())
        with anyio.CancelScope() as scope:
            await subject.connect_tcp('origin.example', 443)
        assert scope.cancel_called
        assert stream.closed == 1
    asyncio.run(run())


def test_timeout_budget_includes_dns_and_fallback(monkeypatch):
    # Model elapsed DNS/TCP time deterministically. Windows monotonic clock ticks
    # can coalesce two short sleeps; cancellation still uses the real AnyIO timer.
    elapsed = [0.0]

    class BudgetClock:
        def __getattr__(self, name):
            return getattr(anyio, name)

        def current_time(self):
            return elapsed[0]

        def current_effective_deadline(self):
            return 0.1

    monkeypatch.setattr('app.sources.http_transport.anyio', BudgetClock())
    async def run():
        async def resolver(host, port):
            elapsed[0] += 0.02
            return ['8.8.8.8', '1.1.1.1']
        class SlowTCP(TCP):
            async def connect_tcp(self, host, port, **kwargs):
                self.calls.append((host, port, kwargs))
                if len(self.calls) == 1:
                    elapsed[0] += 0.03
                    raise httpcore.ConnectError('unreachable')
                await anyio.sleep_forever()
        tcp = SlowTCP()
        subject = PublicIPBackend(resolver=resolver, tcp_backend=tcp)
        with pytest.raises(httpcore.ConnectTimeout):
            await subject.connect_tcp('origin.example', 443, timeout=0.1)
        assert len(tcp.calls) == 2
        assert 0 < tcp.calls[1][2]['timeout'] < tcp.calls[0][2]['timeout'] < 0.1
    asyncio.run(run())


def test_real_httpcore_preserves_origin_sni():
    async def run():
        stream = Stream(('8.8.8.8', 443))
        subject, tcp, _ = backend(['8.8.8.8'], TCP([stream]))
        connection = httpcore.AsyncHTTPConnection(
            origin=httpcore.Origin(b'https', b'origin.example', 443),
            network_backend=subject,
        )
        request = httpcore.Request('GET', 'https://origin.example/')
        wrapped = await connection._connect(request)
        assert stream.tls[0] == 'origin.example'
        assert tcp.calls[0][0] == '8.8.8.8'
        await wrapped.aclose()
        await wrapped.aclose()
        assert stream.closed == 1
    asyncio.run(run())


@pytest.mark.parametrize('cancel_kind', ['anyio', 'asyncio'])
def test_httpcore_tls_cancellation_closes_stream(cancel_kind):
    async def run():
        started = anyio.Event()

        class PendingTLS(Stream):
            async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
                started.set()
                await anyio.sleep_forever()

        raw = PendingTLS(('8.8.8.8', 443))
        subject, tcp, _ = backend(['8.8.8.8'], TCP([raw]))
        connection = httpcore.AsyncHTTPConnection(
            origin=httpcore.Origin(b'https', b'origin.example', 443),
            network_backend=subject,
        )
        request = httpcore.Request('GET', 'https://origin.example/')
        if cancel_kind == 'asyncio':
            task = asyncio.create_task(connection._connect(request))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            async def cancel_when_started(scope):
                await started.wait()
                scope.cancel()

            with anyio.CancelScope() as scope:
                async with anyio.create_task_group() as group:
                    group.start_soon(cancel_when_started, scope)
                    await connection._connect(request)
            assert scope.cancelled_caught
        assert raw.closed == 1
        assert len(tcp.calls) == 1
        await connection.aclose()
        assert raw.closed == 1
    asyncio.run(run())


@pytest.mark.parametrize('error', [httpcore.ConnectError('TLS failed'),
                                   httpcore.ConnectTimeout('TLS timeout'),
                                   ssl.SSLError('handshake failed')])
def test_httpcore_tls_failure_closes_stream(error):
    async def run():
        class FailedTLS(Stream):
            async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
                raise error

        raw = FailedTLS(('8.8.8.8', 443))
        subject, _, _ = backend(['8.8.8.8'], TCP([raw]))
        connection = httpcore.AsyncHTTPConnection(
            origin=httpcore.Origin(b'https', b'origin.example', 443),
            network_backend=subject,
        )
        with pytest.raises(type(error)) as caught:
            await connection._connect(httpcore.Request('GET', 'https://origin.example/'))
        assert caught.value is error
        assert raw.closed == 1
        await connection.aclose()
        assert raw.closed == 1
    asyncio.run(run())


def test_successful_tls_delegates_to_upgraded_stream_and_double_close():
    async def run():
        class TLSStream(Stream):
            async def read(self, max_bytes, timeout=None):
                assert (max_bytes, timeout) == (10, 2)
                return b'response'

            async def write(self, buffer, timeout=None):
                assert (buffer, timeout) == (b'request', 3)

        upgraded = TLSStream(('8.8.8.8', 443))

        class UpgradingStream(Stream):
            async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
                self.tls = (server_hostname, timeout)
                return upgraded

        raw = UpgradingStream(('8.8.8.8', 443))
        subject, _, _ = backend(['8.8.8.8'], TCP([raw]))
        connection = httpcore.AsyncHTTPConnection(
            origin=httpcore.Origin(b'https', b'origin.example', 443),
            network_backend=subject,
        )
        stream = await connection._connect(httpcore.Request(
            'GET', 'https://origin.example/', extensions={'timeout': {'connect': 4}},
        ))
        assert raw.tls == ('origin.example', 4)
        assert raw.closed == upgraded.closed == 0
        assert await stream.read(10, 2) == b'response'
        await stream.write(b'request', 3)
        assert stream.get_extra_info('server_addr') == upgraded.peer
        await stream.aclose()
        await stream.aclose()
        assert upgraded.closed == 1
        assert raw.closed == 0
    asyncio.run(run())


def test_dns_failure_and_exhausted_tcp_fallback():
    async def run():
        async def failing_resolver(host, port):
            raise socket.gaierror('unresolved')
        tcp = TCP()
        subject = PublicIPBackend(resolver=failing_resolver, tcp_backend=tcp)
        with pytest.raises(httpcore.ConnectError):
            await subject.connect_tcp('origin.example', 443)
        assert not tcp.calls
        tcp = TCP([httpcore.ConnectError('first'), OSError('second')])
        subject, _, _ = backend(['8.8.8.8', '1.1.1.1'], tcp)
        with pytest.raises(httpcore.ConnectError):
            await subject.connect_tcp('origin.example', 443)
        assert len(tcp.calls) == 2
        with pytest.raises(PublicIPError):
            await subject.connect_unix_socket('/socket')
    asyncio.run(run())


def test_peer_inspection_error_closes_stream():
    async def run():
        class BrokenStream(Stream):
            def get_extra_info(self, key):
                raise RuntimeError('peer unavailable')
        stream = BrokenStream(None)
        subject, _, _ = backend(['8.8.8.8'], TCP([stream]))
        with pytest.raises(RuntimeError):
            await subject.connect_tcp('origin.example', 443)
        assert stream.closed == 1
    asyncio.run(run())


@pytest.mark.parametrize('worker', [False, True])
@pytest.mark.parametrize('addresses,peer,blocked', [
    (['8.8.8.8'], ('8.8.8.8', 443), False),
    (['8.8.8.8', '127.0.0.1'], ('8.8.8.8', 443), True),
    (['8.8.8.8'], ('1.1.1.1', 443), True),
])
def test_source_clients_use_pinned_tcp_and_original_tls(worker, addresses, peer, blocked):
    from app.sources.http import (
        ConnectorTransportError, FetchPolicy, bounded_fetch, source_client,
    )
    from contextlib import nullcontext
    import httpx

    async def run():
        class HTTPStream(Stream):
            def get_extra_info(self, key):
                return self.peer if key == 'server_addr' else None

            async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
                self.context = ssl_context
                return await super().start_tls(ssl_context, server_hostname, timeout)

            async def write(self, buffer, timeout=None):
                self.request = buffer

            async def read(self, max_bytes, timeout=None):
                return b'HTTP/1.1 200 OK\r\nContent-Length: 7\r\nConnection: close\r\n\r\nfixture'

        raw = HTTPStream(peer)
        subject, tcp, resolutions = backend(addresses, TCP([raw]))
        context = ssl.create_default_context()
        scope = bounded_fetch(FetchPolicy(frozenset({'origin.example'}), 1)) if worker else nullcontext()
        with scope, patch('app.sources.http.PublicIPBackend', return_value=subject):
            async with source_client(verify=context, trust_env=False, timeout=4) as client:
                if blocked:
                    with pytest.raises(ConnectorTransportError if worker else httpx.ConnectError):
                        await client.get('https://origin.example/feed')
                else:
                    assert (await client.get('https://origin.example/feed')).content == b'fixture'
                    assert raw.context is context
                    assert raw.tls == ('origin.example', 4)
        assert resolutions == [('origin.example', 443)]
        assert [call[0] for call in tcp.calls] == ([] if len(addresses) > 1 else ['8.8.8.8'])
        if tcp.calls:
            assert raw.closed == 1
    asyncio.run(run())


def test_first_public_address_timeout_falls_back_to_next_within_total_deadline():
    """Real AnyIO timeouts, synthetic DNS/TCP. No external network or TLS bypass."""
    async def run():
        class SlowFirstTCP(TCP):
            async def connect_tcp(self, host, port, **kwargs):
                self.calls.append((host, port, kwargs))
                if host == '2606:4700:4700::1111':
                    # Mimic a first resolved address that blackholes SYNs
                    # until its per-address connect timeout expires.
                    try:
                        with anyio.fail_after(kwargs['timeout']):
                            await anyio.sleep_forever()
                    except TimeoutError:
                        raise httpcore.ConnectTimeout('public first IP timed out') from None
                return Stream((host, port))

        tcp = SlowFirstTCP()
        subject, _, _ = backend(['2606:4700:4700::1111', '8.8.8.8'], tcp)
        stream = await subject.connect_tcp('origin.example', 443, timeout=0.12)
        assert [call[0] for call in tcp.calls] == ['2606:4700:4700::1111', '8.8.8.8']
        assert 0 < tcp.calls[0][2]['timeout'] <= 0.06
        assert 0 < tcp.calls[1][2]['timeout'] <= 0.12
        assert tcp.calls[1][2]['timeout'] > 0
        await stream.aclose()
    asyncio.run(run())
