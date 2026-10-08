"""Offline exact-result cache and single-flight contracts."""
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from app.cache.backend import (Cache, MemoryBackend, RedisBackend, UnavailableBackend,
                               CacheUnavailable, CacheValueError, RELEASE_SCRIPT, encode)
from app.cache.config import CacheSettings
from app.llm.base import LLMAPIError, LLMInvalidResponse, LLMTimeoutError, LLMConfigurationError
from app.llm.cache import (AICacheSettings, CachedAI, Operation, TENDER_ANALYSIS, COMPANY_PROFILE,
                           RAG_ANSWER, fingerprint, generate_operation, load_ai_cache_settings)
from app.llm.gateway import AIGateway, AIGatewaySettings, ProviderRegistry
from app.llm.models import LLMResponse


class Provider:
    def __init__(self):
        self.calls = 0
        self.started = asyncio.Event()
        self.release = None
        self.failure = None
        self.result = LLMResponse("answer", "fake", "model", 2, 3, "stop")

    def cache_identity(self):
        return {"model": "model", "adapter": "fake-v1"}

    async def generate(self, prompt, *, max_tokens=512):
        self.calls += 1
        self.started.set()
        if self.release is not None:
            await self.release.wait()
        if self.failure:
            raise self.failure
        return self.result


def make(provider=None, cache=None, **options):
    p = provider or Provider()
    registry = ProviderRegistry()
    registry.register("fake", p)
    gateway = AIGateway(registry, AIGatewaySettings(provider="fake", max_attempts=1,
                                                   request_timeout_seconds=.5, max_concurrency=2))
    cache = cache or Cache(MemoryBackend(), "fixture")
    return p, CachedAI(gateway, cache, AICacheSettings(enabled=True, **options))


def digest(p, prompt="private document", operation=TENDER_ANALYSIS, tokens=512):
    return fingerprint(operation, "fake", p.cache_identity(), prompt, tokens)


@pytest.mark.parametrize("change", ["prompt", "tokens", "provider", "model", "adapter", "namespace", "version"])
def test_material_fingerprint_inputs(change):
    op, provider, identity, prompt, tokens = TENDER_ANALYSIS, "fake", {"model": "m", "adapter": "v1"}, "text", 512
    baseline = fingerprint(op, provider, identity, prompt, tokens)
    if change == "prompt": prompt = "text "
    if change == "tokens": tokens = 513
    if change == "provider": provider = "other"
    if change in {"model", "adapter"}: identity[change] = "changed"
    if change == "namespace": op = COMPANY_PROFILE
    if change == "version": op = replace(op, version=2)
    assert fingerprint(op, provider, identity, prompt, tokens) != baseline


def test_canonical_known_digest_and_private_keys():
    source = {"schema": "valyqon-ai-request-v1", "operation": "tender-analysis", "operation_version": 1,
              "provider": "fake", "identity": {"model": "m", "adapter": "v1"},
              "prompt": "private document", "generation": {"max_tokens": 512}}
    expected = hashlib.sha256(json.dumps(source, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    a = fingerprint(TENDER_ANALYSIS, "fake", {"adapter": "v1", "model": "m"}, "private document", 512)
    assert a == expected == fingerprint(TENDER_ANALYSIS, "fake", {"model": "m", "adapter": "v1"}, "private document", 512)
    key = Cache(MemoryBackend(), "fixture").key("ai-result", a)
    assert key == "valyqon:fixture:cache:ai-result:" + hashlib.sha256(a.encode()).hexdigest()
    assert "private document" not in key
    code = "from app.llm.cache import *; print(fingerprint(TENDER_ANALYSIS,'fake',{'model':'m','adapter':'v1'},'private document',512))"
    for seed in ("1", "932"):
        assert subprocess.check_output([sys.executable, "-c", code], env={**os.environ, "PYTHONHASHSEED": seed}, text=True).strip() == a


def test_gigachat_identity_excludes_credentials():
    from app.llm.config import GigaChatSettings
    from app.llm.gigachat import GigaChatProvider
    one = GigaChatProvider(GigaChatSettings("secret-one", "m"))
    two = GigaChatProvider(GigaChatSettings("secret-two", "m"))
    assert one.cache_identity() == two.cache_identity() == {"model": "m", "adapter": "gigachat-chat-v1"}
    assert digest(one) == digest(two)


@pytest.mark.parametrize("kwargs", [{"enabled": 1}, {"ttl_seconds": 0}, {"ttl_seconds": 604801},
    {"lock_ttl_seconds": -1}, {"wait_seconds": float('inf')}, {"poll_seconds": 0},
    {"poll_seconds": True}, {"ttl_seconds": float('nan')}, {"wait_seconds": .01, "poll_seconds": .1}])
def test_configuration_bounds(kwargs):
    with pytest.raises(LLMConfigurationError): AICacheSettings(**kwargs)


def test_env_settings(monkeypatch):
    monkeypatch.setenv("VALYQON_AI_CACHE_ENABLED", "true")
    monkeypatch.setenv("VALYQON_AI_CACHE_TTL_SECONDS", "42")
    assert load_ai_cache_settings().ttl_seconds == 42
    monkeypatch.setenv("VALYQON_AI_CACHE_ENABLED", "secret")
    with pytest.raises(LLMConfigurationError, match="Invalid AI cache configuration"):
        load_ai_cache_settings()


def test_hit_miss_expiry_invalidation_and_attempts():
    async def run():
        now = [0]
        p, ai = make(cache=Cache(MemoryBackend(clock=lambda: now[0])), ttl_seconds=1)
        a = await ai.generate("private document", operation=TENDER_ANALYSIS)
        b = await ai.generate("private document", operation=TENDER_ANALYSIS)
        assert a.text == b.text and a.attempts == 1 and b.attempts == 0 and p.calls == 1
        await ai.generate("different", operation=TENDER_ANALYSIS)
        assert p.calls == 2
        now[0] += 2
        await ai.generate("private document", operation=TENDER_ANALYSIS)
        assert p.calls == 3
        assert await ai.invalidate(digest(p))
        await ai.generate("private document", operation=TENDER_ANALYSIS)
        assert p.calls == 4
        with pytest.raises(CacheValueError): await ai.invalidate("*")
    asyncio.run(run())


@pytest.mark.parametrize("corruption", [b'pickle', b'j:{', encode([]), encode({"schema": 1}),
    encode({"schema": 1, "text": "answer", "provider": "fake", "model": "m", "input_tokens": -1,
            "output_tokens": None, "finish_reason": None})])
def test_corruption_is_miss(corruption):
    async def run():
        p, ai = make()
        key = ai.cache.key(ai.DOMAIN, digest(p))
        ai.cache.backend.set(key, corruption, 1000)
        assert (await ai.generate("private document", operation=TENDER_ANALYSIS)).text == "answer"
        assert p.calls == 1
    asyncio.run(run())


@pytest.mark.parametrize("error", [LLMAPIError("private"), LLMTimeoutError("private"), LLMInvalidResponse("private")])
def test_errors_not_cached_and_owner_recovers(error):
    async def run():
        p, ai = make(); p.failure = error
        with pytest.raises(type(error)): await ai.generate("private document", operation=TENDER_ANALYSIS)
        assert ai.cache.get(ai.DOMAIN, digest(p)) is None
        p.failure = None
        await ai.generate("private document", operation=TENDER_ANALYSIS)
        assert p.calls == 2
    asyncio.run(run())


def test_invalid_provider_response_not_cached():
    async def run():
        p, ai = make(); p.result = LLMResponse("", "fake", "m")
        with pytest.raises(LLMInvalidResponse): await ai.generate("private document", operation=TENDER_ANALYSIS)
        assert ai.cache.get(ai.DOMAIN, digest(p)) is None
    asyncio.run(run())


@pytest.mark.parametrize("mode", ["bypass", "no-operation", "disabled", "unknown-identity"])
def test_explicit_safe_bypass(mode):
    async def run():
        p, ai = make()
        if mode == "disabled": ai.settings = AICacheSettings()
        if mode == "unknown-identity": p.cache_identity = lambda: None
        for _ in range(2):
            await ai.generate("private document", operation=None if mode == "no-operation" else TENDER_ANALYSIS,
                              bypass=mode == "bypass")
        assert p.calls == 2
    asyncio.run(run())


def test_twelve_concurrent_duplicates_across_wrappers():
    async def run():
        p, ai = make(); p.release = asyncio.Event()
        _, other = make(p, ai.cache)
        tasks = [asyncio.create_task((ai if i % 2 else other).generate("private document", operation=TENDER_ANALYSIS)) for i in range(12)]
        await p.started.wait(); await asyncio.sleep(.08)
        assert p.calls == 1
        p.release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), 2)
        assert all(r.text == "answer" for r in results) and p.calls == 1
    asyncio.run(run())


def test_different_fingerprints_execute_independently_with_gateway_limit():
    async def run():
        p, ai = make(); p.release = asyncio.Event()
        tasks = [asyncio.create_task(ai.generate(str(i), operation=TENDER_ANALYSIS)) for i in range(4)]
        await p.started.wait(); await asyncio.sleep(.08)
        assert p.calls == 2
        p.release.set(); await asyncio.wait_for(asyncio.gather(*tasks), 2)
        assert p.calls == 4
    asyncio.run(run())


def test_waiter_cancellation_preserves_owner_and_owner_cancellation_releases():
    async def run():
        p, ai = make(); p.release = asyncio.Event()
        owner = asyncio.create_task(ai.generate("private document", operation=TENDER_ANALYSIS))
        await p.started.wait()
        waiter = asyncio.create_task(ai.generate("private document", operation=TENDER_ANALYSIS))
        await asyncio.sleep(.02); waiter.cancel()
        with pytest.raises(asyncio.CancelledError): await waiter
        assert not owner.done() and p.calls == 1
        owner.cancel()
        with pytest.raises(asyncio.CancelledError): await owner
        assert ai.cache.get(ai.DOMAIN, digest(p)) is None
        p.release.set()
        await ai.generate("private document", operation=TENDER_ANALYSIS)
        assert p.calls == 2
    asyncio.run(run())


def test_wait_is_bounded_and_not_busy_spinning():
    async def run():
        p, ai = make(wait_seconds=.08, poll_seconds=.02)
        lease = ai.cache.acquire_lock(ai.DOMAIN, digest(p), ttl=1)
        original = ai.cache.acquire_lock
        ai.cache.acquire_lock = MagicMock(wraps=original)
        with pytest.raises(LLMTimeoutError): await ai.generate("private document", operation=TENDER_ANALYSIS)
        assert 2 <= ai.cache.acquire_lock.call_count <= 6 and p.calls == 0
        ai.cache.release_lock(lease)
    asyncio.run(run())


def test_expired_orphan_lock_recovery_and_safe_effective_lease():
    async def run():
        now = [0]
        p, ai = make(cache=Cache(MemoryBackend(clock=lambda: now[0])), lock_ttl_seconds=1)
        assert ai.lock_ttl == 10.5
        lease = ai.cache.acquire_lock(ai.DOMAIN, digest(p), ttl=1)
        now[0] = 2
        await ai.generate("private document", operation=TENDER_ANALYSIS)
        assert not ai.cache.release_lock(lease) and p.calls == 1
    asyncio.run(run())


def test_second_check_after_acquisition():
    async def run():
        p, ai = make()
        original = ai.cache.acquire_lock
        def acquire(*args, **kwargs):
            lease = original(*args, **kwargs)
            ai.cache.set(ai.DOMAIN, digest(p), {"schema": 1, "text": "other owner", "provider": "fake",
                "model": "model", "input_tokens": None, "output_tokens": None, "finish_reason": None}, ttl=5)
            return lease
        ai.cache.acquire_lock = acquire
        assert (await ai.generate("private document", operation=TENDER_ANALYSIS)).text == "other owner"
        assert p.calls == 0
    asyncio.run(run())


@pytest.mark.parametrize("required", [False, True])
def test_backend_unavailable_policy(required):
    async def run():
        p, ai = make(cache=Cache(UnavailableBackend())); ai.required = required
        if required:
            with pytest.raises(CacheUnavailable): await ai.generate("private document", operation=TENDER_ANALYSIS)
            assert p.calls == 0
        else:
            await ai.generate("private document", operation=TENDER_ANALYSIS)
            assert p.calls == 1
    asyncio.run(run())


def test_optional_write_outage_never_reexecutes_provider():
    async def run():
        p, ai = make()
        ai.cache.set = MagicMock(side_effect=CacheUnavailable("safe"))
        assert (await ai.generate("private document", operation=TENDER_ANALYSIS)).text == "answer"
        assert p.calls == 1
    asyncio.run(run())


def test_large_valid_uncacheable_response_returned():
    async def run():
        p, ai = make(); ai.MAX_VALUE_BYTES = 10
        await ai.generate("private document", operation=TENDER_ANALYSIS)
        assert ai.cache.get(ai.DOMAIN, digest(p)) is None and p.calls == 1
    asyncio.run(run())


def test_redis_commands_reuse_ttl_and_token_release():
    async def run():
        memory = MemoryBackend()
        client = MagicMock()
        client.ping.return_value = True
        client.get.side_effect = memory.get
        client.set.side_effect = lambda key, value, px, nx: memory.set(key, value, px, nx)
        client.eval.side_effect = lambda script, count, key, token: memory.compare_delete(key, token)
        backend = RedisBackend(CacheSettings(url="redis://synthetic/0"), client_factory=lambda **kw: client,
                               pool_factory=lambda *a, **kw: MagicMock())
        p, ai = make(cache=Cache(backend, "fixture"))
        await ai.generate("private document", operation=TENDER_ANALYSIS)
        await ai.generate("private document", operation=TENDER_ANALYSIS)
        assert p.calls == 1
        writes = client.set.call_args_list
        assert writes[0].kwargs == {"px": 60000, "nx": True}
        assert writes[0].args[0].startswith("valyqon:fixture:lock:ai-result:")
        assert writes[1].kwargs == {"px": 3600000, "nx": False}
        assert client.eval.call_args.args[:2] == (RELEASE_SCRIPT, 1)
        assert client.eval.call_args.args[3] == writes[0].args[1]
    asyncio.run(run())


def test_operation_helper_preserves_injected_provider():
    async def run():
        p = Provider()
        await generate_operation(p, RAG_ANSWER, "question", max_tokens=700)
        assert p.calls == 1
    asyncio.run(run())


def test_cache_hit_skips_gateway_admission():
    async def run():
        p, ai = make()
        await ai.generate("private document", operation=TENDER_ANALYSIS)
        await ai.gateway._semaphore.acquire(); await ai.gateway._semaphore.acquire()
        try:
            response = await asyncio.wait_for(ai.generate("private document", operation=TENDER_ANALYSIS), .1)
            assert response.attempts == 0 and p.calls == 1
        finally:
            ai.gateway._semaphore.release(); ai.gateway._semaphore.release()
    asyncio.run(run())


def test_waiter_becomes_owner_after_failure():
    async def run():
        p, ai = make(); p.release = asyncio.Event(); p.failure = LLMAPIError("safe")
        owner = asyncio.create_task(ai.generate("private document", operation=TENDER_ANALYSIS))
        await p.started.wait()
        waiter = asyncio.create_task(ai.generate("private document", operation=TENDER_ANALYSIS))
        await asyncio.sleep(.02); p.release.set()
        with pytest.raises(LLMAPIError): await owner
        p.failure = None
        assert (await asyncio.wait_for(waiter, 1)).text == "answer" and p.calls == 2
    asyncio.run(run())


@pytest.mark.parametrize("field,value", [("text", ""), ("text", 3), ("text", "x" * 100001),
    ("model", "x" * 257), ("model", None), ("provider", "wrong"), ("finish_reason", "x" * 65),
    ("finish_reason", []), ("input_tokens", True), ("output_tokens", 1000000001),
    ("schema", True), ("extra", "private")], ids=["empty-text", "text-type", "text-bound", "model-bound", "model-type", "provider-match", "finish-bound", "finish-type", "token-bool", "token-bound", "schema-type", "extra-field"])
def test_untrusted_response_field_bounds(field, value):
    async def run():
        p, ai = make()
        data = {"schema": 1, "text": "answer", "provider": "fake", "model": "model",
                "input_tokens": None, "output_tokens": None, "finish_reason": None}
        data[field] = value
        ai.cache.set(ai.DOMAIN, digest(p), data, ttl=1)
        assert (await ai.generate("private document", operation=TENDER_ANALYSIS)).text == "answer"
        assert p.calls == 1
    asyncio.run(run())


def test_serialization_failure_returns_valid_result_without_caching():
    async def run():
        p, ai = make()
        p.result = LLMResponse("answer\ud800", "fake", "model")
        assert (await ai.generate("private document", operation=TENDER_ANALYSIS)).text == p.result.text
        assert ai.cache.get(ai.DOMAIN, digest(p)) is None
    asyncio.run(run())


def test_composition_enabled_and_default_disabled(monkeypatch):
    from app.llm.cache import compose_cached_ai
    async def run():
        p, ai = make()
        monkeypatch.setenv("VALYQON_REDIS_REQUIRED", "false")
        monkeypatch.setenv("VALYQON_AI_CACHE_ENABLED", "false")
        wrapped = compose_cached_ai(ai.gateway, ai.cache)
        assert not wrapped.settings.enabled
        monkeypatch.setenv("VALYQON_AI_CACHE_ENABLED", "true")
        wrapped = compose_cached_ai(ai.gateway, ai.cache)
        for _ in range(2): await generate_operation(wrapped, COMPANY_PROFILE, "company", max_tokens=2048)
        assert p.calls == 1
        for _ in range(2): await wrapped.generate("live support", max_tokens=700)
        assert p.calls == 3
    asyncio.run(run())


def test_required_write_outage_fails_without_reexecuting():
    async def run():
        p, ai = make(); ai.required = True
        ai.cache.set = MagicMock(side_effect=CacheUnavailable("safe"))
        with pytest.raises(CacheUnavailable): await ai.generate("private document", operation=TENDER_ANALYSIS)
        assert p.calls == 1
    asyncio.run(run())


def test_cancellation_during_lock_acquisition_releases():
    import threading
    async def run():
        p, ai = make()
        entered, finish = threading.Event(), threading.Event()
        original = ai.cache.acquire_lock
        def acquire(*args, **kwargs):
            lease = original(*args, **kwargs)
            entered.set(); assert finish.wait(2)
            return lease
        ai.cache.acquire_lock = acquire
        request = asyncio.create_task(ai.generate("private document", operation=TENDER_ANALYSIS))
        assert await asyncio.to_thread(entered.wait, 1)
        request.cancel(); finish.set()
        with pytest.raises(asyncio.CancelledError): await request
        assert p.calls == 0
        lease = original(ai.DOMAIN, digest(p), ttl=1)
        ai.cache.release_lock(lease)
    asyncio.run(run())


def test_cancellation_during_cache_write_invalidates_and_preserves_cancel():
    import threading
    async def run():
        p, ai = make()
        entered, finish = threading.Event(), threading.Event()
        original = ai.cache.set
        def write(*args, **kwargs):
            entered.set(); assert finish.wait(2)
            return original(*args, **kwargs)
        ai.cache.set = write
        request = asyncio.create_task(ai.generate("private document", operation=TENDER_ANALYSIS))
        assert await asyncio.to_thread(entered.wait, 1)
        request.cancel(); finish.set()
        with pytest.raises(asyncio.CancelledError): await request
        assert ai.cache.get(ai.DOMAIN, digest(p)) is None
        assert p.calls == 1
    asyncio.run(run())


@pytest.mark.parametrize("required", [False, True])
def test_release_outage_does_not_duplicate_execution(required):
    async def run():
        p, ai = make(); ai.required = required
        ai.cache.release_lock = MagicMock(side_effect=CacheUnavailable("safe"))
        if required:
            with pytest.raises(CacheUnavailable): await ai.generate("private document", operation=TENDER_ANALYSIS)
        else:
            assert (await ai.generate("private document", operation=TENDER_ANALYSIS)).text == "answer"
        assert p.calls == 1
    asyncio.run(run())
