"""Deterministic gateway tests: no real provider/client is used."""
import asyncio
import os
import tempfile
import traceback
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from app.llm.base import (
    LLMAPIError, LLMAuthenticationError, LLMConfigurationError,
    LLMInvalidRequest, LLMInvalidResponse, LLMNetworkError,
    LLMProviderUnavailable, LLMRateLimited, LLMTimeoutError,
)
from app.llm.gateway import AIGateway, AIGatewaySettings, ProviderRegistry, load_gateway_settings
from app.llm.models import LLMResponse


class FakeProvider:
    def __init__(self, failures=(), result=None):
        self.failures = list(failures)
        self.result = result if result is not None else LLMResponse("ok", "fake", "model")
        self.calls = 0

    async def generate(self, prompt, *, max_tokens=512):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return self.result


def gateway(provider, **settings):
    registry = ProviderRegistry()
    registry.register("fake", provider)
    return AIGateway(registry, AIGatewaySettings(provider="fake", **settings))


class ConfigurationTests(unittest.TestCase):
    def test_bounds(self):
        for values in ({"max_concurrency": 0}, {"max_concurrency": 65},
                       {"max_concurrency": True}, {"max_attempts": 6},
                       {"request_timeout_seconds": float("nan")},
                       {"request_timeout_seconds": 301}, {"retry_base_seconds": 0},
                       {"retry_max_seconds": float("inf")},
                       {"retry_base_seconds": 3, "retry_max_seconds": 2},
                       {"provider": "package.Class"}):
            with self.subTest(values=values), self.assertRaises(LLMConfigurationError):
                AIGatewaySettings(**values)

    def test_dotenv_precedence_and_safe_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("VALYQON_AI_MAX_CONCURRENCY=3\nVALYQON_AI_MAX_ATTEMPTS=4\n")
            with patch.dict(os.environ, {"VALYQON_AI_MAX_CONCURRENCY": "2"}, clear=True):
                settings = load_gateway_settings(path)
                self.assertEqual((settings.max_concurrency, settings.max_attempts), (2, 4))
            with patch.dict(os.environ, {"VALYQON_AI_MAX_ATTEMPTS": "secret-token"}, clear=True):
                with self.assertRaises(LLMConfigurationError) as caught:
                    load_gateway_settings(path)
                self.assertNotIn("secret-token", str(caught.exception))

    def test_registry_security_and_freeze(self):
        registry = ProviderRegistry()
        for name in ("os.system", "__import__('os')", "../module", "secret://key@host", ""):
            with self.assertRaises(LLMConfigurationError):
                registry.register(name, FakeProvider())
        registry.register("fake", FakeProvider())
        with self.assertRaises(LLMConfigurationError):
            registry.register("fake", FakeProvider())
        with self.assertRaises(LLMConfigurationError):
            registry.resolve("unknown")
        class SyncProvider:
            def generate(self, prompt, *, max_tokens=512):
                return LLMResponse("ok", "fake", "model")
        with self.assertRaises(LLMConfigurationError):
            registry.register("sync", SyncProvider())
        registry.freeze()
        registry.freeze()
        with self.assertRaises(LLMConfigurationError):
            registry.register("other", FakeProvider())

    def test_registry_concurrent_registration_and_resolution(self):
        registry = ProviderRegistry()
        def register(_):
            try:
                registry.register("fake", FakeProvider())
                return True
            except LLMConfigurationError:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(register, range(20))), 1)
            providers = list(pool.map(lambda _: registry.resolve("fake"), range(20)))
        self.assertTrue(all(p is providers[0] for p in providers))

    def test_production_composition_and_unknown_provider_no_client(self):
        from app.llm.gateway import build_gateway
        with patch.dict(os.environ, {"VALYQON_AI_PROVIDER": "unknown"}), \
                patch("app.llm.gigachat.GigaChatProvider") as adapter:
            with self.assertRaises(LLMConfigurationError):
                build_gateway()
            adapter.assert_not_called()
        from app.llm.config import GigaChatSettings
        with patch.dict(os.environ, {"VALYQON_AI_PROVIDER": "gigachat"}), \
                patch("app.llm.config.load_settings", return_value=GigaChatSettings("synthetic", "test")), \
                patch("app.llm.gigachat.GigaChat") as client:
            self.assertIsInstance(build_gateway(), AIGateway)
            client.assert_not_called()

    def test_health_reports_local_readiness_without_inference(self):
        from app.api.runtime import ApiRuntime
        provider = FakeProvider()
        runtime = ApiRuntime(provider=gateway(provider))
        self.assertEqual(runtime.component_status()["llm"], "ready")
        self.assertEqual(provider.calls, 0)
        runtime.close()
        runtime.close()
        self.assertEqual(provider.calls, 0)


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_tender_business_flow_and_schema_failure_not_retried(self):
        from app.services.tender_analysis import analyze_tender, AnalysisError
        provider = FakeProvider(result=LLMResponse('{"title":"Supply"}', "fake", "model"))
        ai = gateway(provider)
        result = await analyze_tender("Customer tender document", ai)
        self.assertEqual(result.analysis.title, "Supply")
        self.assertEqual(provider.calls, 1)
        provider.result = LLMResponse('not JSON', "fake", "model")
        with self.assertRaises(AnalysisError):
            await analyze_tender("Customer tender document", ai)
        self.assertEqual(provider.calls, 2)

    async def test_transient_then_success_and_metadata(self):
        for failure in (LLMNetworkError("secret"), LLMProviderUnavailable("secret"), LLMRateLimited("secret")):
            provider = FakeProvider([failure])
            ai = gateway(provider)
            sleeps = []
            async def sleep(delay):
                sleeps.append(delay)
            ai._sleep = sleep
            result = await ai.generate("document")
            self.assertEqual((result.text, result.provider, result.attempts), ("ok", "fake", 2))
            self.assertEqual(sleeps, [.25])
            self.assertEqual(provider.calls, 2)

    async def test_max_attempts_and_bounded_backoff(self):
        provider = FakeProvider([LLMNetworkError("secret")] * 5)
        ai = gateway(provider, max_attempts=5, retry_base_seconds=1, retry_max_seconds=2)
        sleeps = []
        async def sleep(delay):
            sleeps.append(delay)
        ai._sleep = sleep
        with self.assertRaises(LLMNetworkError):
            await ai.generate("document")
        self.assertEqual(provider.calls, 5)
        self.assertEqual(sleeps, [1, 2, 2, 2])

    async def test_permanent_errors_and_redaction(self):
        secret = "https://user:password@host Bearer token Authorization: key customer-document"
        for kind in (LLMAuthenticationError, LLMAPIError, LLMConfigurationError,
                     LLMInvalidRequest, LLMInvalidResponse, LLMTimeoutError, ValueError):
            provider = FakeProvider([kind(secret)])
            with self.assertRaises(Exception) as caught:
                await gateway(provider).generate("document")
            self.assertIsInstance(caught.exception, LLMAPIError if kind is ValueError else kind)
            self.assertEqual(provider.calls, 1)
            self.assertNotIn(secret, "".join(traceback.format_exception(caught.exception)))
            self.assertIsNone(caught.exception.__cause__)
            self.assertIsNone(caught.exception.__context__)

    async def test_invalid_response_never_retried(self):
        for result in (object(), LLMResponse("", "fake", "model"),
                       LLMResponse("ok", "fake", object()),
                       LLMResponse("ok", "fake", "model", input_tokens="raw")):
            provider = FakeProvider(result=result)
            with self.assertRaises(LLMInvalidResponse):
                await gateway(provider).generate("document")
            self.assertEqual(provider.calls, 1)

    async def test_invalid_request_no_provider(self):
        provider = FakeProvider()
        ai = gateway(provider)
        for prompt, tokens in (("", 512), (" ", 512), (None, 512),
                               ("x" * (ai.MAX_PROMPT_CHARS + 1), 512),
                               ("ok", True), ("ok", 4097)):
            with self.assertRaises(LLMInvalidRequest):
                await ai.generate(prompt, max_tokens=tokens)
        self.assertEqual(provider.calls, 0)

    async def test_timeout_cancels_and_releases(self):
        class Slow(FakeProvider):
            cancelled = False
            async def generate(self, *args, **kwargs):
                try:
                    await asyncio.Event().wait()
                finally:
                    self.cancelled = True
        provider = Slow()
        ai = gateway(provider, request_timeout_seconds=.02, max_concurrency=1)
        with self.assertRaises(LLMTimeoutError):
            await ai.generate("document")
        self.assertTrue(provider.cancelled)
        ai._provider = FakeProvider()
        self.assertEqual((await ai.generate("document")).text, "ok")

    async def test_concurrency_progress_failure_retry_and_instance_isolation(self):
        class Recording(FakeProvider):
            active = 0
            peak = 0
            async def generate(self, *args, **kwargs):
                self.active += 1
                self.peak = max(self.peak, self.active)
                try:
                    await asyncio.sleep(0)
                    return await super().generate(*args, **kwargs)
                finally:
                    self.active -= 1
        provider = Recording([LLMNetworkError("safe"), LLMAuthenticationError("safe")])
        ai = gateway(provider, max_concurrency=2, retry_base_seconds=.001)
        results = await asyncio.gather(*(ai.generate("document") for _ in range(12)), return_exceptions=True)
        self.assertEqual(sum(isinstance(r, LLMResponse) for r in results), 11)
        self.assertEqual(provider.peak, 2)
        self.assertEqual(provider.active, 0)
        self.assertEqual((await ai.generate("next")).text, "ok")
        self.assertIsNot(ai._semaphore, gateway(FakeProvider())._semaphore)

    async def test_admission_timeout_and_external_cancellation(self):
        entered = asyncio.Event()
        release = asyncio.Event()
        class Blocking(FakeProvider):
            async def generate(self, *args, **kwargs):
                entered.set()
                await release.wait()
                return self.result
        ai = gateway(Blocking(), max_concurrency=1, request_timeout_seconds=.1)
        first = asyncio.create_task(ai.generate("first"))
        await entered.wait()
        # Cancel a queued admission, then the active call; neither leaks permits.
        second = asyncio.create_task(ai.generate("second"))
        await asyncio.sleep(0)
        second.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await second
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        release.set()
        self.assertEqual((await ai.generate("next")).text, "ok")
        # A deadline also applies while waiting for admission.
        await ai._semaphore.acquire()
        try:
            with self.assertRaises(LLMTimeoutError):
                await ai.generate("waiting")
        finally:
            ai._semaphore.release()

    async def test_cross_loop_use_fails_safely(self):
        ai = gateway(FakeProvider())
        await ai.generate("first")
        def other_loop():
            return asyncio.run(ai.generate("second"))
        with self.assertRaises(LLMConfigurationError):
            await asyncio.to_thread(other_loop)

    async def test_backoff_uses_total_deadline_and_releases_admission(self):
        provider = FakeProvider([LLMNetworkError("safe")])
        ai = gateway(provider, max_concurrency=1, request_timeout_seconds=.02)
        backoff = asyncio.Event()
        async def sleep(delay):
            backoff.set()
            await asyncio.Event().wait()
        ai._sleep = sleep
        request = asyncio.create_task(ai.generate("document"))
        await backoff.wait()
        # A separate request progresses while the original is in backoff.
        self.assertEqual((await ai.generate("other")).text, "ok")
        with self.assertRaises(LLMTimeoutError):
            await request
        self.assertEqual(provider.calls, 2)
        self.assertEqual((await ai.generate("next")).text, "ok")

    async def test_instances_progress_independently(self):
        entered = asyncio.Event()
        class Blocking(FakeProvider):
            async def generate(self, *args, **kwargs):
                entered.set()
                await asyncio.Event().wait()
        first = gateway(Blocking(), max_concurrency=1)
        active = asyncio.create_task(first.generate("document"))
        await entered.wait()
        second = gateway(FakeProvider(), max_concurrency=1)
        self.assertEqual((await second.generate("document")).text, "ok")
        active.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await active
