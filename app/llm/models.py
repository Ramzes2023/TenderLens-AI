"""Internal response contract, independent of any vendor SDK."""
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
