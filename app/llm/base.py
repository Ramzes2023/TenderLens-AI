"""Shared provider interface and safe public exceptions."""
from typing import Protocol

from .models import LLMResponse


class LLMError(Exception):
    """Public errors contain fixed messages, never upstream response bodies."""


class LLMConfigurationError(LLMError):
    pass


class LLMAuthenticationError(LLMError):
    pass


class LLMNetworkError(LLMError):
    pass


class LLMTimeoutError(LLMNetworkError):
    pass


class LLMAPIError(LLMError):
    pass


class LLMProviderUnavailable(LLMAPIError):
    pass


class LLMRateLimited(LLMProviderUnavailable):
    pass


class LLMInvalidRequest(LLMError):
    pass


class LLMInvalidResponse(LLMAPIError):
    pass


class LLMProvider(Protocol):
    """Async, cancellation-cooperative text generation; returns no vendor objects."""
    async def generate(self, prompt: str, *, max_tokens: int = 512) -> LLMResponse:
        ...


class CacheIdentityProvider(Protocol):
    """Optional safe identity: exact model and adapter configuration revision.

    No secrets or transport configuration. Change adapter revision whenever fixed
    generation options change; absent/invalid identity bypasses result caching.
    """
    def cache_identity(self) -> dict[str, str]:
        ...
