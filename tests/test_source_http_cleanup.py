"""Finite HTTP cleanup regressions: mock streams only, no DNS or sockets."""
import asyncio
from unittest.mock import patch

import anyio
import httpcore
import httpx
import pytest

from app.sources import http_transport as transport
from app.sources.http import BoundedClient, LiveClient, FetchPolicy, bounded_fetch, ConnectorTransportError
from tests.test_source_http_transport import Stream, TCP, backend


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(transport, '_CLEANUP_SECONDS', 0.02)
    loop = asyncio.new_event_loop()
    original = asyncio.run
    with patch('socket.getaddrinfo', side_effect=AssertionError('DNS forbidden')), \
         patch('socket.socket.connect', side_effect=AssertionError('TCP forbidden')), \
         patch('asyncio.run', side_effect=lambda coro: original(coro, loop_factory=lambda: loop)):
        yield
    if not loop.is_closed():
        loop.close()


class Stalled(httpx.AsyncByteStream):
    def __init__(self, *, read_stalls=False, close_error=None):
        self.started = self.finished = 0
        self.read_stalls = read_stalls
        self.close_error = close_error

    async def __aiter__(self):
        if self.read_stalls:
            await anyio.sleep_forever()
        yield b'body'

    async def aclose(self):
        self.started += 1
        try:
            if self.close_error:
                raise self.close_error
            await anyio.sleep_forever()
        finally:
            self.finished += 1


@pytest.mark.parametrize('client_type', [LiveClient, BoundedClient])
@pytest.mark.parametrize('mode', ['success', 'security', 'cancel', 'close_error'])
def test_response_cleanup(client_type, mode):
    async def run():
        stream = Stalled(read_stalls=mode == 'cancel',
                         close_error=OSError('cleanup failed') if mode == 'close_error' else None)
        def handle(request):
            return httpx.Response(200, stream=stream, headers={
                'content-encoding': 'unsupported' if mode in ('security', 'close_error') else 'identity'})
        with bounded_fetch(FetchPolicy(frozenset({'public.example'}), 4)):
            async with client_type(transport=httpx.MockTransport(handle)) as client:
                with anyio.fail_after(0.5):
                    if mode in ('security', 'close_error'):
                        with pytest.raises(ConnectorTransportError) as exc:
                            await client.get('https://public.example/')
                        assert not exc.value.retryable
                    elif mode == 'cancel':
                        cancelled = False
                        with anyio.move_on_after(0.005) as scope:
                            try:
                                await client.get('https://public.example/')
                            except anyio.get_cancelled_exc_class():
                                cancelled = True
                                raise
                        assert cancelled
                    else:
                        assert (await client.get('https://public.example/')).content == b'body'
        assert stream.started == stream.finished
        assert stream.started == 1
    asyncio.run(run())


@pytest.mark.parametrize('client_type', [LiveClient, BoundedClient])
@pytest.mark.parametrize('exit_context', [False, True])
def test_client_cleanup_deadline(client_type, exit_context):
    async def run():
        stalled = Stalled()
        client = client_type(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
        # Patch the owned transport, preserving the audited constructor contract.
        client._transport.aclose = stalled.aclose
        with anyio.fail_after(0.5):
            if exit_context:
                async with client:
                    pass
            else:
                await client.aclose()
        assert stalled.started == stalled.finished == 1
    asyncio.run(run())


@pytest.mark.parametrize('failure', ['peer', 'tls', 'cancel', 'connect'])
@pytest.mark.parametrize('close_error', [False, True])
def test_tcp_failure_cleanup(failure, close_error):
    async def run():
        stalled = Stalled(close_error=OSError('cleanup failed') if close_error else None)
        raw = Stream(('127.0.0.1' if failure == 'peer' else '8.8.8.8', 443))
        raw.aclose = stalled.aclose
        original = httpcore.ConnectError('connection failed')
        async def tls(*args, **kwargs):
            if failure == 'cancel':
                raise asyncio.CancelledError()
            raise original
        raw.start_tls = tls
        subject, tcp, _ = backend(['8.8.8.8'], TCP([original if failure == 'connect' else raw]))
        with anyio.fail_after(0.5):
            if failure == 'peer':
                with pytest.raises(transport.PublicIPError):
                    await subject.connect_tcp('public.example', 443)
            elif failure == 'connect':
                with pytest.raises(httpcore.ConnectError) as exc:
                    await subject.connect_tcp('public.example', 443)
                assert exc.value is original
            else:
                stream = await subject.connect_tcp('public.example', 443)
                with pytest.raises(asyncio.CancelledError if failure == 'cancel' else httpcore.ConnectError) as exc:
                    await stream.start_tls(None)
                if failure == 'tls':
                    assert exc.value is original
                await stream.aclose()
        assert stalled.started == stalled.finished == (0 if failure == 'connect' else 1)
    asyncio.run(run())


@pytest.mark.parametrize('client_type', [LiveClient, BoundedClient])
def test_hook_error_survives_httpx_cleanup(client_type):
    async def run():
        original = ConnectorTransportError()
        stream = Stalled(close_error=OSError('cleanup failed'))
        async def hook(response):
            raise original
        with bounded_fetch(FetchPolicy(frozenset({'public.example'}), 4)):
            async with client_type(
                transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=stream)),
                event_hooks={'response': [hook]},
            ) as client:
                with pytest.raises(ConnectorTransportError) as exc:
                    await client.get('https://public.example/')
                assert exc.value is original
        assert stream.started == stream.finished == 1
    asyncio.run(run())
