import asyncio
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from gigachat.exceptions import AuthenticationError, ServerError
from gigachat.models.chat_completions import ChatCompletionResponse

from app.llm.base import LLMAPIError, LLMAuthenticationError, LLMConfigurationError, LLMNetworkError, LLMTimeoutError
from app.llm.config import GigaChatSettings, load_settings
from app.llm.gigachat import GigaChatProvider
from app.llm.health import main

SECRET = "synthetic-secret-not-real"


class ConfigurationTests(unittest.TestCase):
    def test_environment_and_defaults(self):
        with patch.dict(os.environ, {"GIGACHAT_CREDENTIALS": SECRET, "GIGACHAT_MODEL": "test-model"}, clear=True):
            settings = load_settings(Path("does-not-exist.env"))
        self.assertEqual(settings.scope, "GIGACHAT_API_PERS")
        self.assertEqual(settings.timeout, 30)
        self.assertNotIn(SECRET, repr(settings))

    def test_missing_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(LLMConfigurationError):
                load_settings(Path("does-not-exist.env"))

    def test_invalid_configuration(self):
        for extra in ({"model": ""}, {"scope": "bad"}, {"timeout": 0}, {"timeout": float("nan")}, {"ca_bundle_file": "missing.pem"}):
            with self.subTest(extra=extra), self.assertRaises(LLMConfigurationError):
                GigaChatSettings(**({"credentials": SECRET, "model": "test"} | extra))

    def test_dotenv_and_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("GIGACHAT_CREDENTIALS=synthetic\nGIGACHAT_MODEL=file-model\nGIGACHAT_SCOPE=GIGACHAT_API_B2B\n", encoding="utf-8")
            with patch.dict(os.environ, {"GIGACHAT_MODEL": "env-model"}, clear=True):
                settings = load_settings(path)
        self.assertEqual(settings.model, "env-model")
        self.assertEqual(settings.scope, "GIGACHAT_API_B2B")

    def test_unsupported_provider_and_bad_timeout(self):
        for extra in ({"LLM_PROVIDER": "unknown"}, {"GIGACHAT_TIMEOUT": "bad"}):
            with patch.dict(os.environ, extra, clear=True), self.assertRaises(LLMConfigurationError):
                load_settings(Path("missing.env"))

    def test_health_missing_settings_no_request(self):
        with patch("app.llm.health.load_settings", side_effect=LLMConfigurationError("Missing configuration")), patch("app.llm.health.GigaChatProvider") as provider, redirect_stderr(io.StringIO()):
            self.assertEqual(main(), 2)
            provider.assert_not_called()

    def test_health_success(self):
        with patch("app.llm.health.load_settings", return_value=GigaChatSettings(SECRET, "test")), patch("app.llm.health.GigaChatProvider") as provider, redirect_stdout(io.StringIO()) as output:
            provider.return_value.generate = AsyncMock(return_value=type("Result", (), {"text": "работает"})())
            self.assertEqual(main(), 0)
            self.assertEqual(output.getvalue().strip(), "работает")


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.provider = GigaChatProvider(GigaChatSettings(SECRET, "test-model"))
        self.patcher = patch("app.llm.gigachat.GigaChat")
        self.factory = self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.client = self.factory.return_value.__aenter__.return_value
        self.client.achat.create = AsyncMock(return_value=ChatCompletionResponse(
            messages=[{"role": "assistant", "content": [{"text": "работает"}]}],
            model="resolved-model", usage={"input_tokens": 5, "output_tokens": 1},
            finish_reason="stop",
        ))

    async def test_success_and_sdk_configuration(self):
        result = await self.provider.generate("test prompt", max_tokens=32)
        self.assertEqual(result.text, "работает")
        self.assertEqual(result.model, "resolved-model")
        self.assertEqual(result.input_tokens, 5)
        self.assertEqual(result.output_tokens, 1)
        kwargs = self.factory.call_args.kwargs
        self.assertTrue(kwargs["verify_ssl_certs"])
        self.assertEqual(kwargs["max_retries"], 0)
        self.assertEqual(kwargs["timeout"], 30)
        payload = self.client.achat.create.call_args.args[0]
        self.assertEqual(payload.messages[0].content[0].text, "test prompt")
        self.assertEqual(payload.model_options.max_tokens, 32)
        self.assertFalse(payload.storage)
        self.factory.return_value.__aexit__.assert_awaited_once()

    async def test_safe_error_mapping(self):
        cases = [
            (AuthenticationError("https://example.invalid", 401, SECRET.encode(), None), LLMAuthenticationError),
            (ServerError("https://example.invalid", 500, SECRET.encode(), None), LLMAPIError),
            (httpx.ConnectError(SECRET), LLMNetworkError),
            (httpx.ReadTimeout(SECRET), LLMTimeoutError),
            (ValueError(SECRET), LLMAPIError),
        ]
        for upstream, expected in cases:
            with self.subTest(expected=expected):
                self.client.achat.create.side_effect = upstream
                with self.assertLogs("app.llm.gigachat", level="WARNING") as logs:
                    with self.assertRaises(expected) as caught:
                        await self.provider.generate("test")
                self.assertNotIn(SECRET, str(caught.exception))
                self.assertNotIn(SECRET, str(logs.output))
        self.assertEqual(self.factory.return_value.__aexit__.await_count, len(cases))

    async def test_empty_response(self):
        self.client.achat.create.return_value = ChatCompletionResponse(messages=[])
        with self.assertRaises(LLMAPIError):
            await self.provider.generate("test")

    async def test_total_timeout(self):
        self.provider = GigaChatProvider(GigaChatSettings(SECRET, "test", timeout=0.01))
        async def slow(*args):
            await asyncio.sleep(1)
        self.client.achat.create.side_effect = slow
        with self.assertRaises(LLMTimeoutError):
            await self.provider.generate("test")
        self.factory.return_value.__aexit__.assert_awaited_once()

    async def test_cancellation_propagates(self):
        self.client.achat.create.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.provider.generate("test")
        self.factory.return_value.__aexit__.assert_awaited_once()

    async def test_invalid_input_no_client(self):
        with self.assertRaises(ValueError):
            await self.provider.generate(" ")
        with self.assertRaises(ValueError):
            await self.provider.generate("test", max_tokens=0)
        self.factory.assert_not_called()


class SDKCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_sdk_constructs_and_closes_without_network(self):
        from gigachat import GigaChat
        with patch.dict(os.environ, {}, clear=True):
            async with GigaChat(credentials="c3ludGhldGlj", model="test",
                                timeout=30, verify_ssl_certs=True, max_retries=0) as client:
                self.assertTrue(callable(client.achat.create))
