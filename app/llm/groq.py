"""Fixed-endpoint Groq text adapter; no SDK or persistent client ownership."""
import asyncio

import httpx

from .base import (LLMAPIError, LLMAuthenticationError, LLMInvalidRequest,
                   LLMInvalidResponse, LLMNetworkError, LLMProviderUnavailable,
                   LLMRateLimited, LLMTimeoutError)
from .config import GroqSettings, safe_model
from .models import LLMResponse

ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider:
    def __init__(self, settings: GroqSettings, *, transport=None):
        self.settings = settings
        # Deterministic transport injection for offline tests, never environment loading.
        self._transport = transport

    def cache_identity(self):
        return {"model": self.settings.model, "adapter": "groq-chat-v1"}

    async def generate(self, prompt, *, max_tokens=512):
        if (type(prompt) is not str or not prompt.strip() or len(prompt) > 400000
                or type(max_tokens) is not int or not 1 <= max_tokens <= 4096):
            raise LLMInvalidRequest("Invalid AI request.")
        try:
            async with asyncio.timeout(self.settings.timeout):
                async with httpx.AsyncClient(timeout=self.settings.timeout,
                                            transport=self._transport, follow_redirects=False) as client:
                    response = await client.post(
                        ENDPOINT, headers={"Authorization": "Bearer " + self.settings.api_key},
                        json={"model": self.settings.model,
                              "messages": [{"role": "user", "content": prompt}],
                              "max_tokens": max_tokens, "stream": False})
            status = response.status_code
            if status in (401, 403):
                error = LLMAuthenticationError("AI authentication failed.")
            elif status == 429:
                error = LLMRateLimited("AI provider rate limited.")
            elif 500 <= status <= 599:
                error = LLMProviderUnavailable("AI provider temporarily unavailable.")
            elif not 200 <= status <= 299:
                error = LLMAPIError("AI provider rejected request.")
            else:
                try:
                    return self._parse(response.json())
                except (ValueError, TypeError, KeyError, IndexError):
                    error = LLMInvalidResponse("Invalid AI response.")
        except (TimeoutError, httpx.TimeoutException):
            error = LLMTimeoutError("AI request timed out.")
        except httpx.RequestError:
            error = LLMNetworkError("AI transport failed.")
        # Raise outside upstream exception handlers: traceback contains no vendor context.
        raise error from None

    @staticmethod
    def _parse(value):
        if type(value) is not dict:
            raise ValueError
        choices = value.get("choices")
        if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
            raise ValueError
        choice = choices[0]
        message = choice.get("message")
        if type(message) is not dict or message.get("role") != "assistant":
            raise ValueError
        text, model, finish = message.get("content"), value.get("model"), choice.get("finish_reason")
        if (type(text) is not str or not text.strip() or len(text) > 100000
                or not safe_model(model)
                or (finish is not None and (type(finish) is not str or not finish
                    or len(finish) > 64 or not all(c.isalnum() or c in "_-" for c in finish)))):
            raise ValueError
        usage = value.get("usage")
        if usage is not None and type(usage) is not dict:
            raise ValueError
        usage = usage or {}
        tokens = [usage.get("prompt_tokens"), usage.get("completion_tokens")]
        if any(v is not None and (type(v) is not int or v < 0) for v in tokens):
            raise ValueError
        return LLMResponse(text, "groq", model, *tokens, finish)
