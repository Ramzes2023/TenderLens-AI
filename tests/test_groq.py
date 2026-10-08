"""Groq wire contract and redaction, exclusively through MockTransport."""
import asyncio
import json
import traceback

import httpx
import pytest

from app.llm.base import (LLMAPIError, LLMAuthenticationError, LLMConfigurationError,
                         LLMInvalidRequest, LLMInvalidResponse, LLMNetworkError,
                         LLMProviderUnavailable, LLMRateLimited, LLMTimeoutError)
from app.llm.config import GroqSettings, load_groq_settings, load_failover_settings
from app.llm.groq import GroqProvider, ENDPOINT

SECRET = "secret-groq-key"
PROMPT = "private customer document"
BODY = "Bearer secret https://user:password@example secret-groq-key"


def valid():
    return {"model": "fake/model", "choices": [{"message": {"role": "assistant", "content": "answer"},
                                               "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 5}}


def adapter(handler):
    return GroqProvider(GroqSettings(SECRET, "fake/model"), transport=httpx.MockTransport(handler))


def test_wire_and_normalization():
    def handler(request):
        assert str(request.url) == ENDPOINT
        assert request.method == "POST"
        assert request.headers["Authorization"] == "Bearer " + SECRET
        assert json.loads(request.content) == {"model": "fake/model", "messages": [
            {"role": "user", "content": PROMPT}], "max_tokens": 32, "stream": False}
        return httpx.Response(200, json=valid())
    response = asyncio.run(adapter(handler).generate(PROMPT, max_tokens=32))
    assert (response.text, response.provider, response.model) == ("answer", "groq", "fake/model")
    assert (response.input_tokens, response.output_tokens, response.finish_reason) == (3, 5, "stop")


@pytest.mark.parametrize("status,kind", [(401, LLMAuthenticationError), (403, LLMAuthenticationError),
    (429, LLMRateLimited), (500, LLMProviderUnavailable), (502, LLMProviderUnavailable),
    (503, LLMProviderUnavailable), (400, LLMAPIError), (404, LLMAPIError), (302, LLMAPIError)])
def test_status_redacted(status, kind, caplog):
    with pytest.raises(kind) as caught:
        asyncio.run(adapter(lambda request: httpx.Response(status, text=BODY)).generate(PROMPT))
    if status in (400, 404, 302):
        assert type(caught.value) is LLMAPIError
    emitted = str(caught.value) + repr(caught.value) + "".join(traceback.format_exception(caught.value)) + caplog.text
    for private in (SECRET, PROMPT, "Bearer secret", "https://user:password@example"):
        assert private not in emitted


@pytest.mark.parametrize("kind,expected", [(httpx.ReadTimeout, LLMTimeoutError),
                                         (httpx.ConnectError, LLMNetworkError)])
def test_transport_redacted(kind, expected):
    def handler(request):
        raise kind(BODY, request=request)
    with pytest.raises(expected) as caught:
        asyncio.run(adapter(handler).generate(PROMPT))
    assert BODY not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__context__ is None


@pytest.mark.parametrize("value", [None, [], {}, {"choices": []},
    {**valid(), "model": "https://user:password@example"},
    {**valid(), "choices": [{"message": {"role": "assistant", "content": " "}}]},
    {**valid(), "choices": [{"message": {"role": "user", "content": "answer"}}]},
    {**valid(), "usage": []}, {**valid(), "usage": {"prompt_tokens": -1}},
    {**valid(), "usage": {"completion_tokens": True}},
    {**valid(), "choices": [{**valid()["choices"][0], "finish_reason": BODY}]}])
def test_invalid_response(value):
    with pytest.raises(LLMInvalidResponse):
        asyncio.run(adapter(lambda request: httpx.Response(200, json=value)).generate(PROMPT))


def test_malformed_json():
    with pytest.raises(LLMInvalidResponse) as caught:
        asyncio.run(adapter(lambda request: httpx.Response(200, text=BODY)).generate(PROMPT))
    assert BODY not in "".join(traceback.format_exception(caught.value))


def test_optional_fields():
    value = valid(); value.pop("usage"); value["choices"][0].pop("finish_reason")
    result = asyncio.run(adapter(lambda request: httpx.Response(200, json=value)).generate(PROMPT))
    assert result.input_tokens is result.output_tokens is result.finish_reason is None


@pytest.mark.parametrize("values", [{"api_key": ""}, {"api_key": "Bearer secret"},
    {"model": ""}, {"model": "m" * 257}, {"model": BODY},
    {"timeout": 0}, {"timeout": 301}, {"timeout": 10 ** 1000},
    {"timeout": float("nan")}, {"timeout": float("inf")}, {"timeout": True}])
def test_settings_validation(values):
    with pytest.raises(LLMConfigurationError) as caught:
        GroqSettings(**({"api_key": SECRET} | values))
    assert SECRET not in str(caught.value)
    assert BODY not in str(caught.value)


def test_defaults_repr_and_opt_in(monkeypatch):
    monkeypatch.delenv("VALYQON_AI_FALLBACK_ENABLED", raising=False)
    monkeypatch.delenv("VALYQON_AI_FALLBACK_PROVIDER", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", SECRET)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    assert not load_failover_settings().enabled
    assert load_groq_settings().model == "openai/gpt-oss-120b"
    assert SECRET not in repr(load_groq_settings())
    monkeypatch.setenv("GROQ_API_KEY", "")
    with pytest.raises(LLMConfigurationError): load_groq_settings()


def test_cancellation_and_invalid_input():
    async def cancelled(request): raise asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError): asyncio.run(adapter(cancelled).generate(PROMPT))
    def forbidden(request): raise AssertionError("Transport should not be called")
    for prompt, tokens in [("", 512), (PROMPT, True), (PROMPT, 4097)]:
        with pytest.raises(LLMInvalidRequest): asyncio.run(adapter(forbidden).generate(prompt, max_tokens=tokens))


def test_adapter_total_deadline():
    async def slow(request): await asyncio.Event().wait()
    provider = GroqProvider(GroqSettings(SECRET, timeout=.01), transport=httpx.MockTransport(slow))
    with pytest.raises(LLMTimeoutError): asyncio.run(provider.generate(PROMPT))
