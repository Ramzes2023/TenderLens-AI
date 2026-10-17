"""Live procurement HTTP policy regressions; all requests use MockTransport."""
import asyncio
import ssl
from unittest.mock import patch

import httpx
import pytest

from app.sources.http import (
    BoundedClient, ConnectorTransportError, FetchPolicy, LiveClient,
    bounded_fetch, source_client,
)


@pytest.fixture(autouse=True)
def no_network():
    with patch('socket.getaddrinfo', side_effect=AssertionError('Offline test: no DNS')), \
         patch.object(httpx.AsyncHTTPTransport, 'handle_async_request',
                      side_effect=AssertionError('Offline test: no HTTP connections')):
        yield


BLOCKED = [
    'http://public.example/feed', 'https://public.example:444/feed',
    'https://user:password@public.example/', 'https://@public.example/',
    'https://127.0.0.1/', 'https://10.0.0.1/', 'https://172.16.0.1/',
    'https://192.168.0.1/', 'https://169.254.169.254/', 'https://0.0.0.0/',
    'https://100.64.0.1/', 'https://192.0.2.1/', 'https://224.0.0.1/',
    'https://[::1]/', 'https://[fc00::1]/', 'https://[fe80::1]/',
    'https://[::ffff:127.0.0.1]/', 'https://localhost/',
    'https://localhost./', 'https://api.localhost/', 'https://service.internal/',
    'https://service.local/', 'https://intranet/', 'https://2130706433/',
    'https://127.1/', 'https://0x7f.0.0.1/', 'https://public.example:/',
    'https:///missing', 'https://bad_host.example/', 'https://public.example\\evil/',
    'https://public.example/ bad', 'https://public.example:bad/',
]


@pytest.mark.parametrize('url', BLOCKED)
def test_initial_url_blocked_without_request(url):
    calls = []
    async def run():
        async with source_client(transport=httpx.MockTransport(lambda r: calls.append(r))) as client:
            with pytest.raises(ConnectorTransportError):
                await client.get(url)
    asyncio.run(run())
    assert calls == []


@pytest.mark.parametrize('target', BLOCKED + ['//127.0.0.1/', 'https:/broken', ''])
def test_redirect_target_blocked_before_destination_request(target):
    calls = []
    def transport(request):
        calls.append(request)
        return httpx.Response(302, headers={'location': target})
    async def run():
        async with source_client(follow_redirects=True, transport=httpx.MockTransport(transport)) as client:
            with pytest.raises(ConnectorTransportError):
                await client.get('https://feeds.example/start')
    asyncio.run(run())
    assert len(calls) == 1


@pytest.mark.parametrize('status', [301, 302, 303, 307, 308])
def test_public_redirects_and_credential_isolation(status):
    calls = []
    def transport(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(status, headers={'location': '/same'})
        if len(calls) == 2:
            return httpx.Response(status, headers={
                'location': '//cdn.example/feed',
                'set-cookie': 'shared=synthetic; Domain=.example; Path=/',
            })
        return httpx.Response(200, content=b'custom EIS feed')
    async def run():
        async with source_client(
            follow_redirects=True, auth=('fixture', 'synthetic'),
            cookies={'jar_session': 'synthetic'},
            headers={'Cookie': 'session=synthetic', 'Referer': 'https://feeds.example/?token=synthetic'},
            transport=httpx.MockTransport(transport),
        ) as client:
            response = await client.get('https://feeds.example/start')
            assert response.content == b'custom EIS feed'
            assert len(response.history) == 2
            assert all(r.is_closed for r in response.history)
    asyncio.run(run())
    assert 'authorization' in calls[1].headers and 'cookie' in calls[1].headers
    assert 'referer' in calls[1].headers
    assert all(header not in calls[2].headers for header in ('authorization', 'cookie', 'referer'))


def test_loop_is_bounded_and_responses_closed():
    responses = []
    def transport(request):
        response = httpx.Response(302, headers={'location': '/loop'})
        responses.append(response)
        return response
    async def run():
        async with source_client(follow_redirects=True, transport=httpx.MockTransport(transport)) as client:
            with pytest.raises(ConnectorTransportError):
                await client.get('https://feeds.example/loop')
    asyncio.run(run())
    assert len(responses) == 6
    assert all(r.is_closed for r in responses)


def test_every_hop_is_validated_and_blocked_response_closed():
    calls, responses = [], []
    def transport(request):
        calls.append(request)
        response = httpx.Response(302, headers={'location':
            'https://cdn.example/feed' if len(calls) == 1 else 'https://10.0.0.1/private'})
        responses.append(response)
        return response
    async def run():
        async with source_client(follow_redirects=True, transport=httpx.MockTransport(transport)) as client:
            with pytest.raises(ConnectorTransportError):
                await client.get('https://feeds.example/start')
    asyncio.run(run())
    assert [r.url.host for r in calls] == ['feeds.example', 'cdn.example']
    assert all(r.is_closed for r in responses)


def test_request_hook_cannot_bypass_validation():
    calls = []
    async def hook(request):
        request.url = httpx.URL('https://127.0.0.1/')
    async def run():
        async with source_client(event_hooks={'request': [hook]},
                                 transport=httpx.MockTransport(lambda r: calls.append(r))) as client:
            with pytest.raises(ConnectorTransportError):
                await client.get('https://feeds.example/start')
    asyncio.run(run())
    assert not calls


def test_worker_factory_and_no_follow_behavior_preserved():
    async def run():
        transport = httpx.MockTransport(lambda r: httpx.Response(302, headers={'location': '/feed'}))
        async with source_client(transport=transport) as client:
            response = await client.get('https://feeds.example/start')
            assert response.status_code == 302
            assert response.next_request.url == 'https://feeds.example/feed'
        policy = FetchPolicy(frozenset({'feeds.example'}), 2)
        with bounded_fetch(policy):
            async with source_client(follow_redirects=True, transport=transport, timeout=90) as client:
                assert isinstance(client, BoundedClient)
                assert client.timeout.read == 30
                with pytest.raises(ConnectorTransportError):
                    await client.get('https://feeds.example/start')
        assert policy.requests == 1
    asyncio.run(run())


@pytest.mark.parametrize('target', [
    'http://feeds.example/feed', 'https://feeds.example:444/feed',
    'https://user:password@feeds.example/feed', 'https://evil.example/feed',
    'https://127.0.0.1/feed',
])
@pytest.mark.parametrize('mutation', ['hook', 'auth', 'auth_replacement', 'auth_followup'])
def test_worker_final_url_mutation_blocked_before_transport(target, mutation):
    calls, responses = [], []

    async def hook(request):
        request.url = httpx.URL(target)

    class MutatingAuth(httpx.Auth):
        def auth_flow(self, request):
            if mutation == 'auth_followup':
                yield request
            if mutation == 'auth':
                request.url = httpx.URL(target)
                yield request
            else:
                yield httpx.Request('GET', target)

    def transport(request):
        calls.append(request)
        response = httpx.Response(200, content=b'fixture')
        responses.append(response)
        return response

    async def run():
        policy = FetchPolicy(frozenset({'feeds.example'}), 1)
        with bounded_fetch(policy):
            async with source_client(
                event_hooks={'request': [hook]} if mutation == 'hook' else None,
                auth=None if mutation == 'hook' else MutatingAuth(),
                transport=httpx.MockTransport(transport),
            ) as client:
                with pytest.raises(ConnectorTransportError) as error:
                    await client.get('https://feeds.example/start')
                assert not error.value.retryable
        assert policy.requests == (1 if mutation == 'auth_followup' else 0)

    asyncio.run(run())
    assert len(calls) == (1 if mutation == 'auth_followup' else 0)
    assert all(request.url == 'https://feeds.example/start' for request in calls)
    assert all(response.is_closed for response in responses)


@pytest.mark.parametrize('mutation', ['hook', 'auth'])
def test_worker_allowed_url_mutation_keeps_single_request_budget(mutation):
    calls = []
    target = 'https://feeds.example:443/changed'

    async def hook(request):
        request.url = httpx.URL(target)

    class MutatingAuth(httpx.Auth):
        def auth_flow(self, request):
            yield httpx.Request('GET', target)

    def transport(request):
        calls.append(request)
        return httpx.Response(200, content=b'12345')

    async def run():
        policy = FetchPolicy(frozenset({'feeds.example'}), 1, max_bytes=5)
        with bounded_fetch(policy):
            async with source_client(
                event_hooks={'request': [hook]} if mutation == 'hook' else None,
                auth=None if mutation == 'hook' else MutatingAuth(),
                transport=httpx.MockTransport(transport),
            ) as client:
                response = await client.get('https://feeds.example/start')
                assert response.content == b'12345' and response.is_closed
                assert policy.requests == 1
                with pytest.raises(ConnectorTransportError):
                    await client.get('https://feeds.example/start')
                assert policy.requests == 1

    asyncio.run(run())
    assert len(calls) == 1 and calls[0].url == target


@pytest.mark.parametrize('max_requests', [0, 1, 2, 3, 4])
@pytest.mark.parametrize('replacement', [False, True])
def test_worker_auth_multi_yield_dispatch_quota(max_requests, replacement):
    calls, responses, streams, hook_calls, auth_closed = [], [], [], [], []

    class MultiAuth(httpx.Auth):
        def auth_flow(self, request):
            try:
                for exchange in range(3):
                    if replacement:
                        request = httpx.Request('GET', f'https://feeds.example/auth/{exchange}')
                    response = yield request
                    assert response.status_code == (401 if exchange < 2 else 200)
            finally:
                auth_closed.append(True)

    async def hook(request):
        hook_calls.append(True)
        request.url = request.url.copy_with(query=b'hook=1')

    def transport(request):
        calls.append(str(request.url))
        stream = LiveBodyStream([b'fixture'])
        streams.append(stream)
        response = httpx.Response(401 if len(calls) < 3 else 200, stream=stream)
        responses.append(response)
        return response

    async def run():
        policy = FetchPolicy(frozenset({'feeds.example'}), max_requests)
        with bounded_fetch(policy):
            async with source_client(
                transport=httpx.MockTransport(transport), trust_env=False,
                auth=MultiAuth(), event_hooks={'request': [hook]},
            ) as client:
                if max_requests < 3:
                    with pytest.raises(ConnectorTransportError) as caught:
                        await client.get('https://feeds.example/start')
                    assert not caught.value.retryable
                else:
                    result = await client.get('https://feeds.example/start')
                    assert result.content == b'fixture' and result.is_closed
                assert policy.requests == len(calls) == min(max_requests, 3)
        assert len(hook_calls) == min(max_requests + 1, 3)

    asyncio.run(run())
    assert auth_closed == [True]
    assert all(response.is_closed for response in responses)
    assert all(stream.closed for stream in streams)


@pytest.mark.parametrize('max_requests', [0, 1, 2])
def test_worker_shared_dispatch_quota_boundary(max_requests):
    calls = []

    def transport(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError('Offline failure', request=request)
        return httpx.Response(200, content=b'fixture')

    async def run():
        policy = FetchPolicy(frozenset({'feeds.example'}), max_requests)
        with bounded_fetch(policy):
            for _ in range(max_requests):
                async with source_client(transport=httpx.MockTransport(transport), trust_env=False) as client:
                    if not calls:
                        with pytest.raises(ConnectorTransportError) as caught:
                            await client.get('https://feeds.example/start')
                        assert caught.value.retryable
                    else:
                        assert (await client.get('https://feeds.example/start')).content == b'fixture'
            async with source_client(transport=httpx.MockTransport(transport), trust_env=False) as client:
                for _ in range(2):
                    with pytest.raises(ConnectorTransportError) as caught:
                        await client.get('https://feeds.example/start')
                    assert not caught.value.retryable
                    assert policy.requests == len(calls) == max_requests

    asyncio.run(run())


def test_transport_configuration_passed_through():
    context = ssl.create_default_context()
    with patch.object(httpx.AsyncClient, '__init__', return_value=None) as init:
        client = source_client(proxy='http://proxy.example:8080', verify=context,
                               trust_env=True, timeout=42, follow_redirects=True)
    assert isinstance(client, LiveClient)
    assert init.call_args.kwargs == dict(proxy='http://proxy.example:8080', verify=context,
                                        trust_env=True, timeout=42, follow_redirects=True)


@pytest.mark.parametrize('url', ['https://8.8.8.8/', 'https://[2606:4700:4700::1111]/',
                                 'https://custom-eis.example:443/feed'])
def test_public_literals_and_custom_feeds_allowed(url):
    async def run():
        async with source_client(transport=httpx.MockTransport(lambda r: httpx.Response(200))) as client:
            assert (await client.get(url)).status_code == 200
    asyncio.run(run())


@pytest.mark.parametrize('client_type', [LiveClient, BoundedClient])
@pytest.mark.parametrize('scheme', ['http', 'https', 'socks5', 'socks5h'])
def test_selected_proxy_rejected_before_io(client_type, scheme):
    async def run():
        with bounded_fetch(FetchPolicy(frozenset({'feeds.example'}), 1)):
            async with client_type(proxy=f'{scheme}://proxy.example:8080',
                                   trust_env=False) as client:
                with pytest.raises(ConnectorTransportError) as error:
                    await client.get('https://feeds.example/feed')
                assert not error.value.retryable
    asyncio.run(run())


@pytest.mark.parametrize('client_type', [LiveClient, BoundedClient])
def test_environment_proxy_matching_and_no_proxy(client_type):
    # Replace HTTPX's environment reader rather than reading process secrets.
    with patch('httpx._utils.getproxies', return_value={
        'https': 'http://proxy.example:8080',
        'all': 'socks5://proxy.example:1080',
        'no': '.allowed.example,exact.example',
    }):
        client = client_type(trust_env=True)
    from app.sources.http import _RejectedProxyTransport
    from app.sources.http_transport import PublicIPBackend
    assert isinstance(client._transport._pool._network_backend, PublicIPBackend)
    for url in ['https://sub.allowed.example/', 'https://exact.example/',
                'https://sub.exact.example/']:
        assert client._transport_for_url(httpx.URL(url)) is client._transport
    for url in ['https://other.example/', 'https://allowed.example/']:
        assert isinstance(client._transport_for_url(httpx.URL(url)), _RejectedProxyTransport)
    asyncio.run(client.aclose())


@pytest.mark.parametrize('client_type', [LiveClient, BoundedClient])
@pytest.mark.parametrize('mounted', [False, True])
def test_unsafe_explicit_transports_rejected(client_type, mounted):
    transport = httpx.AsyncHTTPTransport(trust_env=False)
    try:
        with pytest.raises(ConnectorTransportError):
            client_type(**({'mounts': {'https://': transport}} if mounted
                           else {'transport': transport}))
    finally:
        asyncio.run(transport.aclose())


@pytest.mark.parametrize('client_type', [LiveClient, BoundedClient])
def test_mock_mount_and_none_mount_keep_httpx_routing(client_type):
    async def run():
        with bounded_fetch(FetchPolicy(frozenset({'feeds.example'}), 1)):
            mock = httpx.MockTransport(lambda r: httpx.Response(200, content=b'fixture'))
            async with client_type(proxy='http://proxy.example:8080', mounts={
                'https://feeds.example': mock, 'https://direct.example': None,
            }, trust_env=False) as client:
                assert (await client.get('https://feeds.example/')).content == b'fixture'
                assert client._transport_for_url(httpx.URL('https://direct.example')) is client._transport
    asyncio.run(run())


@pytest.mark.parametrize('client_type', [LiveClient, BoundedClient])
def test_direct_pool_keeps_httpx_tls_limits_and_timeout(client_type):
    context = ssl.create_default_context()
    limits = httpx.Limits(max_connections=7, max_keepalive_connections=3,
                          keepalive_expiry=9)
    client = client_type(verify=context, limits=limits, timeout=13,
                         http1=False, trust_env=False)
    pool = client._transport._pool
    assert pool._ssl_context is context
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    assert (pool._max_connections, pool._max_keepalive_connections,
            pool._keepalive_expiry, pool._http1) == (7, 3, 9, False)
    assert client.timeout == httpx.Timeout(13)
    asyncio.run(client.aclose())


def test_sni_override_cannot_change_verified_hostname():
    async def run():
        async with LiveClient(transport=httpx.MockTransport(lambda r: pytest.fail('dispatched'))) as client:
            with pytest.raises(ConnectorTransportError):
                await client.get('https://feeds.example/', extensions={'sni_hostname': 'other.example'})
    asyncio.run(run())


@pytest.mark.parametrize('client_type', [LiveClient, BoundedClient])
@pytest.mark.parametrize('trust_env,no_proxy', [(False, ''), (True, '*')])
def test_disabled_environment_proxies_use_protected_direct_pool(client_type, trust_env, no_proxy):
    from app.sources.http_transport import PublicIPBackend
    with patch('httpx._utils.getproxies', return_value={
        'https': 'http://proxy.example:8080', 'no': no_proxy,
    }):
        client = client_type(trust_env=trust_env)
    assert client._transport_for_url(httpx.URL('https://feeds.example')) is client._transport
    assert isinstance(client._transport._pool._network_backend, PublicIPBackend)
    asyncio.run(client.aclose())


def test_changed_httpx_pool_contract_fails_closed():
    with patch.object(httpx.AsyncClient, '_init_transport', return_value=object()):
        with pytest.raises(ConnectorTransportError):
            LiveClient(trust_env=False)


class LiveBodyStream(httpx.AsyncByteStream):
    def __init__(self, chunks, error=None):
        self.chunks = chunks
        self.error = error
        self.reads = 0
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            self.reads += 1
            yield chunk
        if self.error is not None:
            raise self.error

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize('infinite', [False, True])
@pytest.mark.parametrize('reader', ['get', 'hook', 'auth', 'raw'])
def test_live_oversized_body_is_bounded_during_reads(infinite, reader):
    import itertools
    chunk = b'x' * (1024 * 1024)
    stream = LiveBodyStream(itertools.repeat(chunk) if infinite else [chunk] * 27)
    response = httpx.Response(200, stream=stream)

    async def hook(response):
        await response.aread()

    class ReadingAuth(httpx.Auth):
        requires_response_body = True
        def auth_flow(self, request):
            yield request

    async def run():
        async with LiveClient(
            transport=httpx.MockTransport(lambda r: response),
            event_hooks={'response': [hook]} if reader == 'hook' else None,
            auth=ReadingAuth() if reader == 'auth' else None,
        ) as client:
            with pytest.raises(ConnectorTransportError):
                if reader == 'raw':
                    async with client.stream('GET', 'https://feeds.example/') as result:
                        async for _ in result.aiter_raw():
                            pass
                else:
                    await client.get('https://feeds.example/')
    asyncio.run(run())
    assert stream.reads == 26
    assert stream.closed and response.is_closed
    assert not hasattr(response, '_content')


@pytest.mark.parametrize('follow', [False, True])
def test_live_oversized_redirect_body(follow):
    import itertools
    stream = LiveBodyStream(itertools.repeat(b'x' * (1024 * 1024)))
    redirect = httpx.Response(302, headers={'location': '/final'}, stream=stream)
    calls = []
    def transport(request):
        calls.append(request)
        return redirect if len(calls) == 1 else httpx.Response(200, content=b'ok')
    async def run():
        async with LiveClient(follow_redirects=follow, transport=httpx.MockTransport(transport)) as client:
            if follow:
                response = await client.get('https://feeds.example/')
                assert response.content == b'ok' and response.is_closed
                assert response.history == [redirect]
            else:
                with pytest.raises(ConnectorTransportError):
                    await client.get('https://feeds.example/')
    asyncio.run(run())
    assert stream.reads == (0 if follow else 26)
    assert stream.closed and redirect.is_closed


@pytest.mark.parametrize('size', [0, 17, 25 * 1024 * 1024])
def test_live_normal_body_content_and_closure(size):
    body = b'x' * size
    stream = LiveBodyStream([body])
    response = httpx.Response(200, stream=stream)
    async def run():
        async with LiveClient(transport=httpx.MockTransport(lambda r: response)) as client:
            result = await client.get('https://feeds.example/')
            assert result.content == body
            assert await result.aread() == body
    asyncio.run(run())
    assert response.is_closed and stream.closed


@pytest.mark.parametrize('error', [httpx.ReadError('offline'), asyncio.CancelledError()])
def test_live_stream_error_and_cancellation_close(error):
    stream = LiveBodyStream([b'ok'], error=error)
    response = httpx.Response(200, stream=stream)
    async def run():
        async with LiveClient(transport=httpx.MockTransport(lambda r: response)) as client:
            with pytest.raises(type(error)):
                await client.get('https://feeds.example/')
    asyncio.run(run())
    assert stream.closed and response.is_closed


def test_live_gzip_decoded_body_limit():
    import gzip
    encoded = gzip.compress(b'x' * (26 * 1024 * 1024))
    stream = LiveBodyStream([encoded])
    response = httpx.Response(200, headers={'content-encoding': 'gzip'}, stream=stream)
    async def run():
        async with LiveClient(transport=httpx.MockTransport(lambda r: response)) as client:
            with pytest.raises(ConnectorTransportError):
                await client.get('https://feeds.example/')
    asyncio.run(run())
    assert stream.closed and response.is_closed
    assert not hasattr(response, '_content')


class FakeLiveClock:
    def __init__(self):
        self.now = 0

    def advance(self, seconds):
        self.now += seconds


class SlowLiveStream(LiveBodyStream):
    def __init__(self, clock, delays):
        super().__init__([])
        self.clock = clock
        self.delays = delays

    async def __aiter__(self):
        for delay in self.delays:
            await asyncio.sleep(0)
            self.clock.advance(delay)
            self.reads += 1
            yield b'x'


@pytest.mark.parametrize('reader', ['get', 'bytes', 'raw', 'hook', 'auth'])
def test_live_trickle_uses_absolute_deadline(reader):
    clock = FakeLiveClock()
    stream = SlowLiveStream(clock, [60, 60, 61, 1])
    response = httpx.Response(200, stream=stream)

    async def hook(response):
        await response.aread()

    class ReadingAuth(httpx.Auth):
        requires_response_body = True
        def auth_flow(self, request):
            yield request

    async def run():
        with patch('app.sources.http.anyio.current_time', side_effect=lambda: clock.now):
            async with LiveClient(
                transport=httpx.MockTransport(lambda r: response),
                event_hooks={'response': [hook]} if reader == 'hook' else None,
                auth=ReadingAuth() if reader == 'auth' else None,
            ) as client:
                with pytest.raises(httpx.TimeoutException):
                    if reader in ('bytes', 'raw'):
                        result = await client.send(client.build_request('GET', 'https://feeds.example/'), stream=True)
                        iterator = result.aiter_raw() if reader == 'raw' else result.aiter_bytes()
                        async for _ in iterator:
                            pass
                    else:
                        await client.get('https://feeds.example/')
    asyncio.run(run())
    assert stream.reads == 3
    assert stream.closed and response.is_closed


@pytest.mark.parametrize('stage', ['request_hook', 'auth', 'headers', 'redirect'])
def test_live_deadline_includes_entire_send(stage):
    clock = FakeLiveClock()
    responses = []
    calls = []

    async def hook(request):
        if stage == 'request_hook':
            clock.advance(181)

    class SlowAuth(httpx.Auth):
        async def async_auth_flow(self, request):
            if stage == 'auth':
                clock.advance(181)
            yield request

    async def transport(request):
        calls.append(request)
        clock.advance(100 if stage == 'redirect' else 181 if stage == 'headers' else 0)
        response = httpx.Response(
            302 if stage == 'redirect' and len(calls) == 1 else 200,
            headers={'location': '/final'}, stream=LiveBodyStream([b'ok']))
        responses.append(response)
        return response

    async def run():
        with patch('app.sources.http.anyio.current_time', side_effect=lambda: clock.now):
            async with LiveClient(transport=httpx.MockTransport(transport),
                                  follow_redirects=True, auth=SlowAuth(),
                                  event_hooks={'request': [hook]}) as client:
                with pytest.raises(httpx.TimeoutException):
                    await client.get('https://feeds.example/')
    asyncio.run(run())
    assert all(response.is_closed for response in responses)


def test_live_separate_requests_and_delayed_stream_read():
    clock = FakeLiveClock()
    streams = []
    def transport(request):
        stream = SlowLiveStream(clock, [100])
        streams.append(stream)
        return httpx.Response(200, stream=stream)

    async def run():
        with patch('app.sources.http.anyio.current_time', side_effect=lambda: clock.now):
            async with LiveClient(transport=httpx.MockTransport(transport), timeout=13) as client:
                for _ in range(3):
                    assert (await client.get('https://feeds.example/')).content == b'x'
                assert client.timeout == httpx.Timeout(13)
                result = await client.send(client.build_request('GET', 'https://feeds.example/'), stream=True)
                clock.advance(181)
                with pytest.raises(httpx.TimeoutException):
                    await result.aread()
                assert result.is_closed and streams[-1].reads == 0
    asyncio.run(run())
    assert all(stream.closed for stream in streams)


@pytest.mark.parametrize('cancel', [False, True])
def test_live_blocked_read_timeout_and_cancellation_cleanup(cancel):
    entered = asyncio.Event()
    closed = []
    class WaitingStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            entered.set()
            await asyncio.Event().wait()
            yield b'unreachable'

        async def aclose(self):
            await asyncio.sleep(0)
            closed.append(True)

    response = httpx.Response(200, stream=WaitingStream())
    async def run():
        with patch('app.sources.http._LIVE_REQUEST_SECONDS', 0.02 if not cancel else 180):
            async with LiveClient(transport=httpx.MockTransport(lambda r: response)) as client:
                task = asyncio.create_task(client.get('https://feeds.example/'))
                await entered.wait()
                if cancel:
                    task.cancel()
                with pytest.raises(asyncio.CancelledError if cancel else httpx.TimeoutException):
                    await task
    asyncio.run(run())
    assert closed and response.is_closed


@pytest.mark.parametrize('stage', ['request_hook', 'response_hook', 'auth', 'headers'])
def test_live_deadline_interrupts_stalled_lifecycle(stage):
    stream = LiveBodyStream([b'ok'])
    response = httpx.Response(200, stream=stream)
    async def stall():
        await asyncio.Event().wait()

    async def request_hook(request):
        if stage == 'request_hook':
            await stall()

    async def response_hook(response):
        if stage == 'response_hook':
            await stall()

    class WaitingAuth(httpx.Auth):
        async def async_auth_flow(self, request):
            if stage == 'auth':
                await stall()
            yield request

    async def transport(request):
        if stage == 'headers':
            await stall()
        return response

    async def run():
        with patch('app.sources.http._LIVE_REQUEST_SECONDS', 0.02):
            async with LiveClient(transport=httpx.MockTransport(transport), auth=WaitingAuth(),
                                  event_hooks={'request': [request_hook],
                                               'response': [response_hook]}) as client:
                with pytest.raises(httpx.TimeoutException):
                    await client.get('https://feeds.example/')
    asyncio.run(run())
    if stage == 'response_hook':
        assert response.is_closed and stream.closed


def test_live_operation_timeout_preserved():
    error = httpx.ReadTimeout('operation timeout')
    stream = LiveBodyStream([], error=error)
    response = httpx.Response(200, stream=stream)
    async def run():
        async with LiveClient(transport=httpx.MockTransport(lambda r: response), timeout=13) as client:
            with pytest.raises(httpx.ReadTimeout) as caught:
                await client.get('https://feeds.example/')
            assert caught.value is error
    asyncio.run(run())
    assert response.is_closed and stream.closed


def encode_live_body(body, encoding):
    import gzip
    import zlib
    if encoding == 'gzip':
        return gzip.compress(body)
    if encoding == 'deflate':
        return zlib.compress(body)
    if encoding == 'raw-deflate':
        compressor = zlib.compressobj(wbits=-15)
        return compressor.compress(body) + compressor.flush()
    return body


@pytest.mark.parametrize('encoding', ['identity', 'gzip', 'deflate', 'raw-deflate'])
@pytest.mark.parametrize('size', [0, 65536, 25 * 1024 * 1024, 25 * 1024 * 1024 + 1])
def test_live_safe_decoding_boundaries(encoding, size):
    body = b'x' * size
    wire = encode_live_body(body, encoding)
    stream = LiveBodyStream(wire[i:i + 32768] for i in range(0, len(wire), 32768))
    response = httpx.Response(200, headers={'content-encoding': encoding.replace('raw-', '')}, stream=stream)
    async def run():
        async with LiveClient(transport=httpx.MockTransport(lambda r: response)) as client:
            if size > 25 * 1024 * 1024:
                with pytest.raises(ConnectorTransportError):
                    await client.get('https://feeds.example/')
                assert not hasattr(response, '_content')
            else:
                result = await client.send(client.build_request('GET', 'https://feeds.example/'), stream=True)
                chunks = [chunk async for chunk in result.aiter_bytes()]
                assert all(len(chunk) <= 65536 for chunk in chunks)
                assert b''.join(chunks) == body
    asyncio.run(run())
    assert stream.closed and response.is_closed


@pytest.mark.parametrize('encoding', ['br', 'zstd', 'unknown', 'gzip, deflate', 'identity, gzip', 'gzip, gzip', ''])
def test_live_unsupported_encoding_rejected_before_hooks(encoding):
    stream = LiveBodyStream([b'payload'])
    response = httpx.Response(200, headers={'content-encoding': encoding}, stream=stream)
    async def hook(response):
        pytest.fail('Unsupported encoding reached hook')
    async def run():
        async with LiveClient(transport=httpx.MockTransport(lambda r: response),
                              event_hooks={'response': [hook]}) as client:
            with pytest.raises(ConnectorTransportError):
                await client.get('https://feeds.example/')
    asyncio.run(run())
    assert stream.closed and stream.reads == 0


@pytest.mark.parametrize('encoding', ['gzip', 'deflate', 'raw-deflate'])
@pytest.mark.parametrize('damage', ['truncated', 'corrupt', 'trailing', 'empty', 'checksum'])
def test_live_malformed_compression(encoding, damage):
    if damage == 'checksum' and encoding == 'raw-deflate':
        pytest.skip('Raw deflate has no checksum')
    wire = encode_live_body(b'fixture' * 100, encoding)
    if damage == 'truncated':
        wire = wire[:-1]
    elif damage == 'corrupt':
        wire = b'\xff\xff' + wire[2:]
    elif damage == 'trailing':
        wire += b'garbage'
    elif damage == 'checksum':
        wire = wire[:-1] + bytes([wire[-1] ^ 1])
    else:
        wire = b''
    stream = LiveBodyStream([wire[:1], wire[1:2], wire[2:]])
    response = httpx.Response(200, headers={'content-encoding': encoding.replace('raw-', '')}, stream=stream)
    async def run():
        async with LiveClient(transport=httpx.MockTransport(lambda r: response)) as client:
            with pytest.raises(ConnectorTransportError):
                await client.get('https://feeds.example/')
    asyncio.run(run())
    assert stream.closed and response.is_closed
    assert not hasattr(response, '_content')


@pytest.mark.parametrize('encoding', ['identity', 'gzip', 'deflate', 'raw-deflate'])
@pytest.mark.parametrize('body', [b'<feed><item>fixture</item></feed>', b'{"items": [1]}', b'id,name\n1,fixture\n', b'<html><body>fixture</body></html>'])
def test_live_small_chunks_cached_content_and_advertisement(encoding, body):
    wire = encode_live_body(body, encoding)
    stream = LiveBodyStream(wire[i:i + 1] for i in range(len(wire)))
    response = httpx.Response(200, headers={'content-encoding': encoding.replace('raw-', '')}, stream=stream)
    def transport(request):
        assert request.headers['accept-encoding'] == 'gzip, deflate, identity'
        return response
    async def hook(result):
        assert await result.aread() == body
    async def run():
        async with LiveClient(transport=httpx.MockTransport(transport),
                              headers={'accept-encoding': 'br, zstd'}, event_hooks={'response': [hook]}) as client:
            result = await client.get('https://feeds.example/')
            assert result.content == body and result.text == body.decode()
            assert await result.aread() == body
            assert b''.join([c async for c in result.aiter_bytes(3)]) == body
            assert all(len(c) <= 3 for c in [c async for c in result.aiter_bytes(3)])
    asyncio.run(run())


def test_live_concatenated_gzip_members():
    wire = encode_live_body(b'one', 'gzip') + encode_live_body(b'two', 'gzip')
    stream = LiveBodyStream([wire])
    async def run():
        async with LiveClient(transport=httpx.MockTransport(lambda r: httpx.Response(
            200, headers={'content-encoding': 'gzip'}, stream=stream))) as client:
            assert (await client.get('https://feeds.example/')).content == b'onetwo'
    asyncio.run(run())


@pytest.mark.parametrize('encoding', ['gzip', 'deflate', 'raw-deflate'])
@pytest.mark.parametrize('cancel', [False, True])
def test_live_bomb_operations_are_bounded_and_cancellable(encoding, cancel):
    import zlib
    wire = encode_live_body(b'x' * (26 * 1024 * 1024), encoding)
    stream = LiveBodyStream([wire])
    response = httpx.Response(200, headers={'content-encoding': encoding.replace('raw-', '')}, stream=stream)
    original = zlib.decompressobj
    lengths = []
    class AuditedDecoder:
        def __init__(self, *args):
            self.inner = original(*args)
        def decompress(self, data, max_length):
            assert 0 < max_length <= 65536 and len(data) <= 65538
            output = self.inner.decompress(data, max_length)
            lengths.append(len(output))
            return output
        def flush(self, *args):
            pytest.fail('Unbounded flush')
        def __getattr__(self, name):
            return getattr(self.inner, name)
    async def run():
        with patch('app.sources.http.zlib.decompressobj', AuditedDecoder):
            async with LiveClient(transport=httpx.MockTransport(lambda r: response)) as client:
                if not cancel:
                    with pytest.raises(ConnectorTransportError):
                        await client.get('https://feeds.example/')
                    assert not hasattr(response, '_content')
                    return
                result = await client.send(client.build_request('GET', 'https://feeds.example/'), stream=True)
                iterator = result.aiter_bytes(7)
                assert len(await anext(iterator)) == 7
                # Cancel the active decoder task at its next checkpoint.
                async def consume():
                    asyncio.current_task().cancel()
                    await anext(iterator)
                    while True:
                        await anext(iterator)
                task = asyncio.create_task(consume())
                with pytest.raises(asyncio.CancelledError):
                    await task
    asyncio.run(run())
    assert lengths and max(lengths) <= 65536
    assert stream.closed and response.is_closed


@pytest.mark.parametrize('encoding', ['gzip', 'deflate', 'raw-deflate'])
def test_live_decoding_buffer_obeys_deadline(encoding):
    import zlib
    clock = FakeLiveClock()
    stream = LiveBodyStream([encode_live_body(b'x' * (1024 * 1024), encoding)])
    response = httpx.Response(200, headers={'content-encoding': encoding.replace('raw-', '')}, stream=stream)
    original = zlib.decompressobj
    class SlowDecoder:
        def __init__(self, *args):
            self.inner = original(*args)
        def decompress(self, data, max_length):
            output = self.inner.decompress(data, max_length)
            clock.advance(100)
            return output
        def __getattr__(self, name):
            return getattr(self.inner, name)
    async def run():
        with patch('app.sources.http.anyio.current_time', side_effect=lambda: clock.now), \
             patch('app.sources.http.zlib.decompressobj', SlowDecoder):
            async with LiveClient(transport=httpx.MockTransport(lambda r: response)) as client:
                with pytest.raises(httpx.TimeoutException):
                    await client.get('https://feeds.example/')
    asyncio.run(run())
    assert clock.now == 200 and stream.reads == 1
    assert stream.closed and response.is_closed


@pytest.mark.parametrize('encoding', ['gzip', 'deflate', 'raw-deflate'])
def test_live_compressed_auth_response_reread(encoding):
    body = b'{"items": [1]}'
    stream = LiveBodyStream([encode_live_body(body, encoding)])
    response = httpx.Response(200, headers={'content-encoding': encoding.replace('raw-', '')}, stream=stream)
    class ReadingAuth(httpx.Auth):
        requires_response_body = True
        def auth_flow(self, request):
            result = yield request
            assert result.content == body
    async def run():
        async with LiveClient(transport=httpx.MockTransport(lambda r: response), auth=ReadingAuth()) as client:
            result = await client.get('https://feeds.example/')
            assert result.json() == {'items': [1]}
            assert await result.aread() == body
    asyncio.run(run())
    assert stream.closed and response.is_closed


@pytest.mark.parametrize('encoding', ['identity', 'gzip', 'deflate', 'raw-deflate'])
@pytest.mark.parametrize('size', [0, 65536, 65537])
@pytest.mark.parametrize('reader', ['get', 'hook', 'auth'])
def test_worker_safe_decoding_boundaries(encoding, size, reader):
    body = b'x' * size
    wire = encode_live_body(body, encoding)
    stream = LiveBodyStream(wire[i:i + 1] for i in range(len(wire)))
    response = httpx.Response(200, headers={
        'content-encoding': encoding.replace('raw-', '')}, stream=stream)
    policy = FetchPolicy(frozenset({'feeds.example'}), 1, max_bytes=65536)

    async def hook(result):
        await result.aread()

    class ReadingAuth(httpx.Auth):
        requires_response_body = True
        def auth_flow(self, request):
            yield request

    def transport(request):
        assert request.headers['accept-encoding'] == 'gzip, deflate, identity'
        return response

    async def run():
        with bounded_fetch(policy):
            async with BoundedClient(
                transport=httpx.MockTransport(transport), trust_env=False,
                event_hooks={'response': [hook]} if reader == 'hook' else None,
                auth=ReadingAuth() if reader == 'auth' else None,
            ) as client:
                if size > policy.max_bytes:
                    with pytest.raises(ConnectorTransportError) as caught:
                        await client.get('https://feeds.example/')
                    assert not caught.value.retryable
                    assert not hasattr(response, '_content')
                else:
                    result = await client.get('https://feeds.example/')
                    assert result.content == body
                    assert await result.aread() == body
        assert policy.requests == 1
    asyncio.run(run())
    assert stream.closed and response.is_closed


@pytest.mark.parametrize('encoding', ['gzip', 'deflate', 'raw-deflate'])
@pytest.mark.parametrize('damage', ['truncated', 'corrupt', 'trailing', 'empty', 'checksum'])
def test_worker_malformed_compression(encoding, damage):
    if damage == 'checksum' and encoding == 'raw-deflate':
        pytest.skip('Raw deflate has no checksum')
    wire = encode_live_body(b'fixture' * 100, encoding)
    if damage == 'truncated':
        wire = wire[:-1]
    elif damage == 'corrupt':
        wire = b'\xff\xff' + wire[2:]
    elif damage == 'trailing':
        wire += b'garbage'
    elif damage == 'checksum':
        wire = wire[:-1] + bytes([wire[-1] ^ 1])
    else:
        wire = b''
    stream = LiveBodyStream([wire[:1], wire[1:2], wire[2:]])
    response = httpx.Response(200, headers={
        'content-encoding': encoding.replace('raw-', '')}, stream=stream)
    async def run():
        with bounded_fetch(FetchPolicy(frozenset({'feeds.example'}), 1)):
            async with BoundedClient(transport=httpx.MockTransport(lambda r: response),
                                     trust_env=False) as client:
                with pytest.raises(ConnectorTransportError) as caught:
                    await client.get('https://feeds.example/')
                assert not caught.value.retryable
    asyncio.run(run())
    assert stream.closed and response.is_closed
    assert not hasattr(response, '_content')


@pytest.mark.parametrize('encoding', ['gzip', 'deflate', 'raw-deflate'])
def test_worker_bomb_operations_are_bounded(encoding):
    import zlib
    wire = encode_live_body(b'x' * (26 * 1024 * 1024), encoding)
    stream = LiveBodyStream([wire])
    response = httpx.Response(200, headers={
        'content-encoding': encoding.replace('raw-', '')}, stream=stream)
    original = zlib.decompressobj
    lengths = []

    class AuditedDecoder:
        def __init__(self, *args):
            self.inner = original(*args)
        def decompress(self, data, max_length):
            assert 0 < max_length <= 65536
            output = self.inner.decompress(data, max_length)
            lengths.append(len(output))
            return output
        def flush(self, *args):
            pytest.fail('Unbounded flush')
        def __getattr__(self, name):
            return getattr(self.inner, name)

    async def run():
        with bounded_fetch(FetchPolicy(frozenset({'feeds.example'}), 1)), \
             patch('app.sources.http.zlib.decompressobj', AuditedDecoder):
            async with BoundedClient(transport=httpx.MockTransport(lambda r: response),
                                     trust_env=False) as client:
                with pytest.raises(ConnectorTransportError) as caught:
                    await client.get('https://feeds.example/')
                assert not caught.value.retryable
    asyncio.run(run())
    assert lengths and max(lengths) <= 65536
    assert sum(lengths) == 25 * 1024 * 1024 + 65536
    assert stream.closed and response.is_closed
    assert not hasattr(response, '_content')


@pytest.mark.parametrize('status', [301, 400, 408, 429, 500, 503, 599])
def test_worker_compressed_error_status_keeps_retry_and_cleanup(status):
    stream = LiveBodyStream([b'invalid gzip'])
    response = httpx.Response(status, headers={'content-encoding': 'gzip'}, stream=stream)
    async def run():
        with bounded_fetch(FetchPolicy(frozenset({'feeds.example'}), 1)):
            async with BoundedClient(transport=httpx.MockTransport(lambda r: response),
                                     trust_env=False) as client:
                with pytest.raises(ConnectorTransportError) as caught:
                    await client.get('https://feeds.example/')
                assert caught.value.retryable == (status in (408, 429) or status >= 500)
    asyncio.run(run())
    assert stream.reads == 0
    assert stream.closed and response.is_closed


@pytest.mark.parametrize('kind', ['identity', 'empty-members', 'gzip-header', 'deflate'])
@pytest.mark.parametrize('reader', ['get', 'hook', 'auth', 'raw'])
@pytest.mark.parametrize('chunk_size', [32, 1024])
def test_worker_wire_limit_before_response_consumers(kind, reader, chunk_size):
    import gzip
    import zlib
    limit = 128
    if kind == 'empty-members':
        wire, encoding = gzip.compress(b'') * 20, 'gzip'
    elif kind == 'gzip-header':
        member = gzip.compress(b'')
        wire = member[:3] + b'\x08' + member[4:10] + b'n' * 400 + b'\0' + member[10:]
        encoding = 'gzip'
    elif kind == 'deflate':
        # Stored blocks: decoded bytes fit, while framing exceeds the wire cap.
        compressor = zlib.compressobj(level=0)
        wire = compressor.compress(b'x' * limit) + compressor.flush()
        encoding = 'deflate'
    else:
        wire, encoding = b'x' * 400, 'identity'
    stream = LiveBodyStream(wire[i:i + chunk_size] for i in range(0, len(wire), chunk_size))
    response = httpx.Response(200, headers={'content-encoding': encoding}, stream=stream)
    seen = []

    async def hook(result):
        if reader == 'raw':
            async for chunk in result.aiter_raw():
                seen.append(chunk)
        else:
            await result.aread()

    class ReadingAuth(httpx.Auth):
        requires_response_body = True
        def auth_flow(self, request):
            yield request
            pytest.fail('Oversized response reached auth body consumer')

    async def run():
        policy = FetchPolicy(frozenset({'feeds.example'}), 1, max_bytes=limit)
        with bounded_fetch(policy):
            async with BoundedClient(
                transport=httpx.MockTransport(lambda r: response), trust_env=False,
                event_hooks={'response': [hook]} if reader in ('hook', 'raw') else None,
                auth=ReadingAuth() if reader == 'auth' else None,
            ) as client:
                with pytest.raises(ConnectorTransportError) as caught:
                    await client.get('https://feeds.example/')
                assert not caught.value.retryable
        assert policy.requests == 1
    asyncio.run(run())
    assert stream.reads == limit // chunk_size + 1
    assert sum(map(len, seen)) <= limit
    assert stream.closed and response.is_closed
    assert not hasattr(response, '_content')


@pytest.mark.parametrize('reader', ['get', 'hook', 'auth'])
def test_worker_wire_limit_exact_boundary(reader):
    wire = encode_live_body(b'', 'gzip') * 4
    stream = LiveBodyStream([wire[:7], wire[7:]])
    response = httpx.Response(200, headers={'content-encoding': 'gzip'}, stream=stream)

    async def hook(result):
        assert await result.aread() == b''

    class ReadingAuth(httpx.Auth):
        requires_response_body = True
        def auth_flow(self, request):
            result = yield request
            assert result.content == b''

    async def run():
        with bounded_fetch(FetchPolicy(frozenset({'feeds.example'}), 1, max_bytes=len(wire))):
            async with BoundedClient(
                transport=httpx.MockTransport(lambda r: response), trust_env=False,
                event_hooks={'response': [hook]} if reader in ('hook', 'raw') else None,
                auth=ReadingAuth() if reader == 'auth' else None,
            ) as client:
                assert (await client.get('https://feeds.example/')).content == b''
    asyncio.run(run())
    assert stream.closed and response.is_closed


@pytest.mark.parametrize('cancel_kind', ['asyncio', 'anyio'])
@pytest.mark.parametrize('raw_hook', [False, True])
def test_worker_wire_stream_cancellation_cleanup(cancel_kind, raw_hook):
    import anyio
    closed = []

    async def run():
        entered = anyio.Event()

        class WaitingStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield encode_live_body(b'', 'gzip')
                entered.set()
                await anyio.sleep_forever()
            async def aclose(self):
                await anyio.lowlevel.checkpoint()
                closed.append(True)

        response = httpx.Response(200, headers={'content-encoding': 'gzip'}, stream=WaitingStream())
        async def hook(result):
            async for _ in result.aiter_raw():
                pass

        with bounded_fetch(FetchPolicy(frozenset({'feeds.example'}), 1, max_bytes=128)):
            async with BoundedClient(
                transport=httpx.MockTransport(lambda r: response), trust_env=False,
                event_hooks={'response': [hook]} if raw_hook else None,
            ) as client:
                if cancel_kind == 'asyncio':
                    task = asyncio.create_task(client.get('https://feeds.example/'))
                    await entered.wait()
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                else:
                    async def cancel(scope):
                        await entered.wait()
                        scope.cancel()
                    with anyio.CancelScope() as scope:
                        async with anyio.create_task_group() as group:
                            group.start_soon(cancel, scope)
                            await client.get('https://feeds.example/')
                    assert scope.cancelled_caught
        assert response.is_closed
    asyncio.run(run())
    assert closed == [True]


def test_idn_punycode_bounded_host_matches_only_exact_wire_origin():
    """Mock-only regression: Unicode .host must not defeat an exact ASCII
    allowlist, and similar Unicode or concatenated domains stay blocked.
    """
    official = 'xn--j1adc1b.xn--p1ai'
    seen = []

    def transport(request):
        seen.append((request.url.host, request.url.raw_host))
        return httpx.Response(200, text="official HTML")

    async def check():
        with bounded_fetch(FetchPolicy(frozenset({official}), 5)):
            async with source_client(transport=httpx.MockTransport(transport)) as client:
                first = await client.get('https://' + official + '/procedures')
                assert first.status_code == 200
                # The same canonical public host is valid as Unicode input.
                second = await client.get('https://нмцк.рф/procedures')
                assert second.status_code == 200
                for hostile in [
                    'http://' + official + '/procedures',
                    'https://' + official + '.evil.example/procedures',
                    'https://нмцк.рф.evil.example/procedures',
                    'https://' + official + ':444/procedures',
                    'https://user@' + official + '/procedures',
                ]:
                    with pytest.raises(ConnectorTransportError):
                        await client.get(hostile)
    asyncio.run(check())
    assert len(seen) == 2
    assert all(raw == official.encode('ascii') for _, raw in seen)
    assert all(host == 'нмцк.рф' for host, _ in seen)
