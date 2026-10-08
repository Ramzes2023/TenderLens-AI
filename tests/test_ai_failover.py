"""Ordered bounded failover and route-aware cache contracts, with no network."""
import asyncio
import os
import traceback
from unittest.mock import patch

import pytest

from app.cache.backend import Cache, MemoryBackend
from app.llm.base import (LLMAPIError, LLMAuthenticationError, LLMConfigurationError,
    LLMInvalidRequest, LLMInvalidResponse, LLMNetworkError, LLMProviderUnavailable,
    LLMRateLimited, LLMTimeoutError)
from app.llm.cache import AICacheSettings, CachedAI, TENDER_ANALYSIS, fingerprint
from app.llm.config import GigaChatSettings, GroqSettings, load_failover_settings
from app.llm.failover import FailoverGateway, fallback_eligible
from app.llm.gateway import AIGateway, AIGatewaySettings, ProviderRegistry, build_gateway
from app.llm.groq import GroqProvider
from app.llm.models import LLMResponse


class Fake:
    def __init__(self, name, error=None, model="model"):
        self.name, self.error, self.model = name, error, model
        self.calls = 0
        self.started = asyncio.Event()
        self.release = None

    def cache_identity(self): return {"model": self.model, "adapter": self.name + "-v1"}

    async def generate(self, prompt, *, max_tokens=512):
        self.calls += 1
        self.started.set()
        if self.release is not None: await self.release.wait()
        if self.error is not None: raise self.error
        return LLMResponse("answer", self.name, self.model, 1, 2, "stop")


def gateway(provider, attempts=2, timeout=.5):
    registry = ProviderRegistry(); registry.register(provider.name, provider)
    async def sleep(delay): pass
    return AIGateway(registry, AIGatewaySettings(provider=provider.name, max_attempts=attempts,
        request_timeout_seconds=timeout), sleeper=sleep)


def route(error=None, backup_error=None):
    p, b = Fake("gigachat", error), Fake("groq", backup_error)
    return p, b, FailoverGateway(gateway(p), gateway(b))


def test_primary_success():
    p, b, ai = route()
    assert asyncio.run(ai.generate("doc")).provider == "gigachat"
    assert (p.calls, b.calls) == (1, 0)


@pytest.mark.parametrize("kind", [LLMNetworkError, LLMProviderUnavailable, LLMTimeoutError, LLMRateLimited])
def test_transient_after_primary_exhaustion(kind):
    p, b, ai = route(kind("secret-groq-key"))
    result = asyncio.run(ai.generate("doc"))
    assert result.provider == "groq"
    assert p.calls == (1 if kind is LLMTimeoutError else 2)
    assert b.calls == 1
    assert fallback_eligible(kind())


@pytest.mark.parametrize("kind", [LLMAuthenticationError, LLMConfigurationError, LLMInvalidRequest,
    LLMInvalidResponse, LLMAPIError, ValueError, RuntimeError])
def test_permanent_and_unknown_no_fallback(kind):
    p, b, ai = route(kind("secret-groq-key"))
    with pytest.raises(Exception) as caught: asyncio.run(ai.generate("doc"))
    assert not fallback_eligible(caught.value)
    assert "secret-groq-key" not in "".join(traceback.format_exception(caught.value))
    assert (p.calls, b.calls) == (1, 0)


@pytest.mark.parametrize("kind", [LLMAuthenticationError, LLMConfigurationError, LLMAPIError,
    LLMInvalidResponse, LLMNetworkError, LLMTimeoutError, LLMRateLimited])
def test_backup_failure_precedence(kind):
    p, b, ai = route(LLMNetworkError("primary secret"), kind("Bearer secret"))
    with pytest.raises(kind) as caught: asyncio.run(ai.generate("doc"))
    emitted = "".join(traceback.format_exception(caught.value))
    assert "primary secret" not in emitted and "Bearer secret" not in emitted
    assert caught.value.__context__ is None
    assert p.calls == 2
    assert b.calls == (2 if kind in (LLMNetworkError, LLMRateLimited) else 1)


def test_external_cancellation_no_backup():
    async def run():
        p, b, ai = route(); p.release = asyncio.Event()
        task = asyncio.create_task(ai.generate("doc")); await p.started.wait(); task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert b.calls == 0
    asyncio.run(run())


def test_backup_cancellation_propagates():
    async def run():
        p, b, ai = route(LLMNetworkError()); b.release = asyncio.Event()
        task = asyncio.create_task(ai.generate("doc")); await b.started.wait(); task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert (p.calls, b.calls) == (2, 1)
    asyncio.run(run())


def test_no_nested_routes_and_independent_instances():
    async def run():
        p, b, first = route(); p.release = asyncio.Event()
        task = asyncio.create_task(first.generate("doc")); await p.started.wait()
        p2, b2, second = route(LLMNetworkError())
        assert (await second.generate("doc")).provider == "groq"
        assert (p.calls, b.calls, p2.calls, b2.calls) == (1, 0, 2, 1)
        with pytest.raises(LLMConfigurationError): FailoverGateway(first, second)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
    asyncio.run(run())


@pytest.mark.parametrize("fallback", [False, True])
def test_results_cached_and_twelve_duplicates_single_flight(fallback):
    async def run():
        p, b, ai = route(LLMNetworkError() if fallback else None)
        owner = b if fallback else p; owner.release = asyncio.Event()
        wrapped = CachedAI(ai, Cache(MemoryBackend(), "fixture"), AICacheSettings(enabled=True))
        tasks = [asyncio.create_task(wrapped.generate("private document", operation=TENDER_ANALYSIS))
                 for _ in range(12)]
        await owner.started.wait(); await asyncio.sleep(.03); owner.release.set()
        results = await asyncio.gather(*tasks)
        assert all(r.provider == ("groq" if fallback else "gigachat") for r in results)
        assert (p.calls, b.calls) == ((2, 1) if fallback else (1, 0))
        hit = await wrapped.generate("private document", operation=TENDER_ANALYSIS)
        assert hit.attempts == 0 and hit.provider == results[0].provider
        assert (p.calls, b.calls) == ((2, 1) if fallback else (1, 0))
    asyncio.run(run())


def test_failed_chain_not_cached():
    async def run():
        p, b, ai = route(LLMNetworkError(), LLMAuthenticationError())
        wrapped = CachedAI(ai, Cache(MemoryBackend(), "fixture"), AICacheSettings(enabled=True))
        for _ in range(2):
            with pytest.raises(LLMAuthenticationError): await wrapped.generate("doc", operation=TENDER_ANALYSIS)
        assert (p.calls, b.calls) == (4, 2)
        digest = fingerprint(TENDER_ANALYSIS, "gigachat", ai.cache_identity(), "doc", 512)
        assert wrapped.cache.get(wrapped.DOMAIN, digest) is None
    asyncio.run(run())


def test_route_identity_model_and_credentials_and_key_privacy():
    primary = gateway(Fake("gigachat"))
    def create(key, model):
        registry = ProviderRegistry(); registry.register("groq", GroqProvider(GroqSettings(key, model)))
        return FailoverGateway(primary, AIGateway(registry, AIGatewaySettings(provider="groq")))
    one, two, three = create("secret-groq-key", "fake/model"), create("other-key", "fake/model"), create("other-key", "changed/model")
    def digest(ai): return fingerprint(TENDER_ANALYSIS, "gigachat", ai.cache_identity(), "private doc", 512)
    assert digest(one) == digest(two) != digest(three)
    assert digest(primary) != digest(one)
    identity = str(one.cache_identity()); key = Cache(MemoryBackend(), "fixture").key("ai-result", digest(one))
    for private in ("secret-groq-key", "private doc", "fake/model", "Bearer secret", "https://user:password@example"):
        assert private not in identity + key


def test_lock_ttl_covers_full_route_and_primary():
    primary, backup = gateway(Fake("gigachat"), timeout=300), gateway(Fake("groq"), timeout=300)
    ai = FailoverGateway(primary, backup)
    settings = AICacheSettings(lock_ttl_seconds=1)
    cache = Cache(MemoryBackend(), "fixture")
    assert primary.maximum_generation_seconds == 300
    assert CachedAI(primary, cache, settings).lock_ttl == 310
    assert ai.maximum_generation_seconds == 600
    assert CachedAI(ai, cache, settings).lock_ttl == 610
    lease = cache.acquire_lock("ai-result", "digest", ttl=610); cache.release_lock(lease)


def test_actual_gateway_deadlines_bound_full_chain():
    async def run():
        p, b = Fake("gigachat"), Fake("groq")
        p.release = b.release = asyncio.Event()
        ai = FailoverGateway(gateway(p, timeout=.01), gateway(b, timeout=.01))
        with pytest.raises(LLMTimeoutError): await asyncio.wait_for(ai.generate("doc"), .5)
        assert (p.calls, b.calls) == (1, 1)
    asyncio.run(run())


@pytest.mark.parametrize("env", [{"VALYQON_AI_FALLBACK_ENABLED": "invalid"},
    {"VALYQON_AI_FALLBACK_PROVIDER": "unknown"},
    {"VALYQON_AI_FALLBACK_ENABLED": "true", "GROQ_API_KEY": ""}])
def test_bad_enabled_configuration_fails_without_client(env):
    with patch.dict(os.environ, {"VALYQON_AI_PROVIDER": "gigachat", **env}, clear=True), \
         patch("app.llm.gateway.load_gateway_settings", return_value=AIGatewaySettings()), \
         patch("app.llm.gigachat.GigaChatProvider") as primary:
        with pytest.raises(LLMConfigurationError): build_gateway()
        primary.assert_not_called()


def test_canonical_builder_disabled_and_enabled():
    for enabled in ("false", "true"):
        with patch.dict(os.environ, {"VALYQON_AI_FALLBACK_ENABLED": enabled, "GROQ_API_KEY": "secret-groq-key"}, clear=True), \
             patch("app.llm.gateway.load_gateway_settings", return_value=AIGatewaySettings()), \
             patch("app.llm.config.load_settings", return_value=GigaChatSettings("synthetic", "model")), \
             patch("app.llm.gigachat.GigaChat") as client:
            ai = build_gateway()
            assert type(ai) is (FailoverGateway if enabled == "true" else AIGateway)
            client.assert_not_called()
    with patch.dict(os.environ, {}, clear=True), \
         patch("app.llm.gateway.load_gateway_settings", return_value=AIGatewaySettings()), \
         patch("app.llm.config.load_settings", return_value=GigaChatSettings("synthetic", "model")), \
         patch("app.llm.config.load_groq_settings") as backup:
        assert type(build_gateway()) is AIGateway
        backup.assert_not_called()


def test_api_bot_share_canonical_composition_and_health_is_local():
    from app.api.runtime import ApiRuntime
    p, b, ai = route()
    runtime = ApiRuntime(provider=ai)
    with patch.dict(os.environ, {"GROQ_API_KEY": "secret-groq-key"}):
        output = str(runtime.component_status())
    assert runtime.component_status()["llm"] == "ready"
    assert "secret-groq-key" not in output
    assert (p.calls, b.calls) == (0, 0)


@pytest.mark.parametrize("entrypoint", ["api", "bot"])
def test_entrypoints_receive_cached_failover_route(entrypoint, tmp_path):
    from unittest.mock import AsyncMock
    p, b, ai = route()
    env = {"DATABASE_URL": "sqlite:///" + (tmp_path / "runtime.db").as_posix(),
           "VALYQON_DATABASE_REQUIRE_POSTGRES": "false", "VALYQON_REDIS_URL": "",
           "VALYQON_REDIS_REQUIRED": "false", "VALYQON_EMAIL_MODE": "disabled",
           "VALYQON_AI_CACHE_ENABLED": "true", "RAG_ENABLED": "false"}
    with patch.dict(os.environ, env), patch("app.llm.gateway.build_gateway", return_value=ai) as builder:
        if entrypoint == "api":
            from app.api.runtime import build_runtime
            runtime = build_runtime()
            try:
                assert isinstance(runtime.provider, CachedAI)
                assert runtime.provider.gateway is ai
                assert runtime.component_status()["llm"] == "ready"
            finally:
                runtime.close()
        else:
            from app.bot.main import main
            from app.bot.config import Settings
            with patch("app.bot.main.load_settings", return_value=Settings("123456789:" + "X" * 35)), \
                 patch("app.bot.main.configure_logging"), \
                 patch("app.bot.main.run_bot", new_callable=AsyncMock) as runner:
                assert main() == 0
                wrapped = runner.await_args.args[1]
                assert isinstance(wrapped, CachedAI)
                assert wrapped.gateway is ai
        builder.assert_called_once_with()
        assert (p.calls, b.calls) == (0, 0)


def test_live_primary_diagnostic_ignores_fallback():
    from app.llm.health import main
    from unittest.mock import AsyncMock
    import io
    from contextlib import redirect_stderr
    with patch.dict(os.environ, {"VALYQON_AI_FALLBACK_ENABLED": "true"}), \
         patch("app.llm.health.load_gateway_settings", return_value=AIGatewaySettings(max_attempts=1)), \
         patch("app.llm.health.load_settings", return_value=GigaChatSettings("synthetic", "model")), \
         patch("app.llm.health.GigaChatProvider") as primary, \
         patch("app.llm.groq.GroqProvider") as backup, redirect_stderr(io.StringIO()):
        primary.return_value.generate = AsyncMock(side_effect=LLMNetworkError())
        assert main() == 1
        primary.return_value.generate.assert_awaited_once()
        backup.assert_not_called()
