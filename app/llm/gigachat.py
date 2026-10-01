"""Official GigaChat SDK adapter. No Telegram or PDF dependencies."""
import asyncio
import logging

import httpx
from gigachat import GigaChat
from gigachat.exceptions import AuthenticationError, ForbiddenError, GigaChatException
from gigachat.models.chat_completions import ChatCompletionRequest

from .base import (
    LLMAPIError, LLMAuthenticationError, LLMNetworkError, LLMTimeoutError,
)
from .config import GigaChatSettings
from .models import LLMResponse

logger = logging.getLogger(__name__)


class GigaChatProvider:
    def __init__(self, settings: GigaChatSettings):
        self.settings = settings

    async def generate(self, prompt: str, *, max_tokens: int = 512) -> LLMResponse:
        if not prompt.strip():
            raise ValueError("Промпт не должен быть пустым.")
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens < 1:
            raise ValueError("max_tokens должен быть положительным целым числом.")
        try:
            # One total deadline covers OAuth, generation and session cleanup.
            async with asyncio.timeout(self.settings.timeout):
                async with GigaChat(
                    credentials=self.settings.credentials,
                    scope=self.settings.scope,
                    model=self.settings.model,
                    timeout=self.settings.timeout,
                    verify_ssl_certs=True,
                    ca_bundle_file=self.settings.ca_bundle_file,
                    max_retries=0,
                ) as client:
                    response = await client.achat.create(ChatCompletionRequest(
                        model=self.settings.model,
                        messages=[{"role": "user", "content": [{"text": prompt}]}],
                        model_options={"max_tokens": max_tokens},
                        storage=False,
                    ))
            text = "\n".join(
                part.text for message in response.messages
                if message.role == "assistant"
                for part in (message.content or []) if part.text
            ).strip()
            if not text:
                raise LLMAPIError("GigaChat не вернул текстовый ответ.")
            usage = response.usage
            return LLMResponse(
                text=text, provider="gigachat",
                model=response.model or self.settings.model,
                input_tokens=usage.input_tokens if usage else None,
                output_tokens=usage.output_tokens if usage else None,
                finish_reason=response.finish_reason,
            )
        except (AuthenticationError, ForbiddenError):
            error = LLMAuthenticationError("GigaChat: проверьте ключ, scope и права доступа.")
        except (TimeoutError, httpx.TimeoutException):
            error = LLMTimeoutError("GigaChat: превышено время ожидания.")
        except httpx.RequestError:
            error = LLMNetworkError("GigaChat: ошибка сети или TLS; проверьте подключение и сертификаты.")
        except LLMAPIError as exc:
            error = exc
        except GigaChatException:
            error = LLMAPIError("GigaChat: ошибка API; проверьте доступность модели и квоту.")
        except Exception:
            error = LLMAPIError("GigaChat: не удалось обработать запрос или ответ.")
        # Never log exception bodies, headers, prompts, settings or tracebacks.
        logger.warning("LLM request failed: %s", type(error).__name__)
        raise error from None
