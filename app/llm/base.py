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


class LLMProvider(Protocol):
    async def generate(self, prompt: str, *, max_tokens: int = 512) -> LLMResponse:
        ...
