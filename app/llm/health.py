"""Explicit live connectivity check: python -m app.llm.health."""
import asyncio
import logging
import sys

from .base import LLMConfigurationError, LLMError
from .config import load_settings
from .gigachat import GigaChatProvider

HEALTH_PROMPT = "Ответь одним словом: работает"


def main() -> int:
    # Third-party diagnostics are not needed for this operation.
    for name in ("gigachat", "httpx", "httpcore"):
        logging.getLogger(name).disabled = True
        logging.getLogger(name).propagate = False
    try:
        settings = load_settings()
        response = asyncio.run(GigaChatProvider(settings).generate(HEALTH_PROMPT, max_tokens=32))
        print(response.text.replace(settings.credentials, "[REDACTED]"))
        return 0
    except LLMConfigurationError as error:
        print(str(error), file=sys.stderr)
        return 2
    except LLMError as error:
        print(str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Проверка остановлена.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
