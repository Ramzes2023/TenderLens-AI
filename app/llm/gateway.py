"""Process-local AI policy boundary. No external calls occur at construction."""
import asyncio
import math
import os
import re
import threading
from dataclasses import dataclass, replace
from inspect import iscoroutinefunction

from dotenv import load_dotenv

from .base import (
    LLMProvider, LLMConfigurationError, LLMAuthenticationError,
    LLMNetworkError, LLMTimeoutError, LLMAPIError, LLMProviderUnavailable,
    LLMRateLimited, LLMInvalidRequest, LLMInvalidResponse,
)
from .config import ENV_FILE
from .models import LLMResponse


def _name(name):
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", name):
        raise LLMConfigurationError("Invalid AI provider name.")
    return name


@dataclass(frozen=True)
class AIGatewaySettings:
    provider: str = "gigachat"
    max_concurrency: int = 4
    request_timeout_seconds: float = 30.0
    max_attempts: int = 2
    retry_base_seconds: float = 0.25
    retry_max_seconds: float = 2.0

    def __post_init__(self):
        _name(self.provider)
        try:
            for value, upper in ((self.max_concurrency, 64), (self.max_attempts, 5)):
                if type(value) is not int or not 1 <= value <= upper:
                    raise ValueError
            for value, upper in ((self.request_timeout_seconds, 300),
                                 (self.retry_base_seconds, 30), (self.retry_max_seconds, 60)):
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= upper:
                    raise ValueError
            if self.retry_base_seconds > self.retry_max_seconds:
                raise ValueError
        except (ValueError, TypeError, OverflowError):
            raise LLMConfigurationError("Invalid AI gateway configuration.") from None


def load_gateway_settings(env_file=ENV_FILE):
    load_dotenv(env_file, override=False, encoding="utf-8-sig")
    try:
        return AIGatewaySettings(
            provider=os.environ.get("VALYQON_AI_PROVIDER", os.environ.get("LLM_PROVIDER", "gigachat")),
            max_concurrency=int(os.environ.get("VALYQON_AI_MAX_CONCURRENCY", "4")),
            request_timeout_seconds=float(os.environ.get("VALYQON_AI_REQUEST_TIMEOUT_SECONDS", "30")),
            max_attempts=int(os.environ.get("VALYQON_AI_MAX_ATTEMPTS", "2")),
            retry_base_seconds=float(os.environ.get("VALYQON_AI_RETRY_BASE_SECONDS", ".25")),
            retry_max_seconds=float(os.environ.get("VALYQON_AI_RETRY_MAX_SECONDS", "2")),
        )
    except (ValueError, TypeError, OverflowError):
        raise LLMConfigurationError("Invalid AI gateway configuration.") from None


class ProviderRegistry:
    """Explicit object registry; concurrent reads/registration are synchronized."""
    def __init__(self):
        self._providers = {}
        self._frozen = False
        self._lock = threading.Lock()

    def register(self, name: str, provider: LLMProvider):
        _name(name)
        with self._lock:
            if self._frozen or name in self._providers or not iscoroutinefunction(getattr(provider, "generate", None)):
                raise LLMConfigurationError("AI provider registration rejected.")
            self._providers[name] = provider

    def freeze(self):
        with self._lock:
            self._frozen = True

    def resolve(self, name: str) -> LLMProvider:
        _name(name)
        with self._lock:
            if name not in self._providers:
                raise LLMConfigurationError("AI provider is not registered.")
            return self._providers[name]


def _safe_error(error):
    # Even custom providers raising project exceptions cannot inject their text.
    for kind, message in (
        (LLMAuthenticationError, "AI authentication failed."),
        (LLMTimeoutError, "AI request timed out."),
        (LLMRateLimited, "AI provider rate limited."),
        (LLMProviderUnavailable, "AI provider temporarily unavailable."),
        (LLMNetworkError, "AI transport failed."),
        (LLMConfigurationError, "AI configuration unavailable."),
        (LLMInvalidRequest, "Invalid AI request."),
        (LLMInvalidResponse, "Invalid AI response."),
        (LLMAPIError, "AI provider failed."),
    ):
        if isinstance(error, kind):
            return kind(message)
    return LLMAPIError("AI provider failed.")


class AIGateway:
    # Large enough for existing 50k documents plus JSON escaping and schema,
    # while imposing a finite boundary on all callers, including RAG questions.
    MAX_PROMPT_CHARS = 400000
    MAX_RESPONSE_CHARS = 100000

    def __init__(self, registry: ProviderRegistry, settings=None, *, sleeper=asyncio.sleep):
        self.settings = settings or AIGatewaySettings()
        self._provider = registry.resolve(self.settings.provider)
        registry.freeze()
        self._semaphore = asyncio.Semaphore(self.settings.max_concurrency)
        self._loop = None
        self._loop_lock = threading.Lock()
        self._sleep = sleeper

    def cache_identity(self):
        identity = getattr(self._provider, 'cache_identity', None)
        return identity() if callable(identity) else None

    @property
    def maximum_generation_seconds(self):
        return self.settings.request_timeout_seconds

    @property
    def result_providers(self):
        return frozenset((self.settings.provider,))

    async def generate(self, prompt: str, *, max_tokens: int = 512) -> LLMResponse:
        if (not isinstance(prompt, str) or not prompt.strip() or len(prompt) > self.MAX_PROMPT_CHARS
                or type(max_tokens) is not int or not 1 <= max_tokens <= 4096):
            raise LLMInvalidRequest("Invalid AI request.")
        loop = asyncio.get_running_loop()
        with self._loop_lock:
            if self._loop is None:
                self._loop = loop
            elif self._loop is not loop:
                raise LLMConfigurationError("AI gateway belongs to another event loop.")
        try:
            async with asyncio.timeout(self.settings.request_timeout_seconds):
                for attempt in range(1, self.settings.max_attempts + 1):
                    failure = None
                    async with self._semaphore:
                        try:
                            result = await self._provider.generate(prompt, max_tokens=max_tokens)
                        except Exception as error:
                            failure = _safe_error(error)
                        else:
                            # Require the exact project type; copy validated primitive fields.
                            if not self._valid_response(result):
                                failure = LLMInvalidResponse("Invalid AI response.")
                            else:
                                return LLMResponse(
                                    text=result.text, provider=self.settings.provider, model=result.model,
                                    input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                                    finish_reason=result.finish_reason, attempts=attempt,
                                )
                    if (not isinstance(failure, (LLMNetworkError, LLMProviderUnavailable))
                            or isinstance(failure, LLMTimeoutError)
                            or attempt == self.settings.max_attempts):
                        raise failure from None
                    await self._sleep(min(self.settings.retry_max_seconds,
                                          self.settings.retry_base_seconds * 2 ** (attempt - 1)))
        except TimeoutError:
            raise LLMTimeoutError("AI request timed out.") from None

    @classmethod
    def _valid_response(cls, result):
        return (type(result) is LLMResponse
                and type(result.text) is str and bool(result.text.strip())
                and len(result.text) <= cls.MAX_RESPONSE_CHARS
                and type(result.model) is str and len(result.model) <= 256
                and (result.finish_reason is None or
                     (type(result.finish_reason) is str and len(result.finish_reason) <= 64))
                and all(v is None or (type(v) is int and v >= 0)
                        for v in (result.input_tokens, result.output_tokens)))


def build_gateway():
    """Sole API/bot composition; explicitly approved providers only."""
    from .config import load_settings, load_failover_settings, load_groq_settings
    from .gigachat import GigaChatProvider
    settings = load_gateway_settings()
    registry = ProviderRegistry()
    # Reject unknown selection before even loading credentials.
    if settings.provider != "gigachat":
        raise LLMConfigurationError("AI provider is not registered.")
    policy = load_failover_settings()
    groq_settings = load_groq_settings() if policy.enabled else None
    registry.register("gigachat", GigaChatProvider(load_settings()))
    primary = AIGateway(registry, settings)
    if not policy.enabled:
        return primary
    from .groq import GroqProvider
    from .failover import FailoverGateway
    backup_registry = ProviderRegistry()
    backup_registry.register("groq", GroqProvider(groq_settings))
    return FailoverGateway(primary, AIGateway(backup_registry, replace(settings, provider="groq")))
