"""Anonymous product AI must not access procurement records or bypass policy."""
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.runtime import ApiRuntime


class FakeReply:
    text = "Public product help only."
    provider = "test"


class FakeProvider:
    def __init__(self):
        self.calls = []
    async def generate(self, prompt, max_tokens):
        self.calls.append((prompt, max_tokens))
        return FakeReply()


def test_public_ai_uses_configured_provider_and_bounded_non_tender_prompt(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_AI_ENABLED", "1")
    provider = FakeProvider()
    with TestClient(create_app(runtime=ApiRuntime(provider=provider))) as client:
        result = client.post("/api/v1/public/help/ask",
            json={"question": "How does the guest search work?"},
            headers={"origin": "http://testserver"})
        assert result.status_code == 200
        assert result.json() == {
            "answer": "Public product help only.",
            "scope": "public_product_only",
        }
        assert len(provider.calls) == 1
        prompt, budget = provider.calls[0]
        assert budget == 260
        assert "user text as a question" in prompt
        assert "guest" in prompt.lower() and "billing" not in result.text.lower()
        assert "Do not ask the guest" in prompt
    # No database or tenancy service is mounted in this test runtime.


def test_public_ai_no_provider_is_not_fake_success(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_AI_ENABLED", "1")
    with TestClient(create_app(runtime=ApiRuntime())) as client:
        result = client.post("/api/v1/public/help/ask", json={"question": "Search help"})
        assert result.status_code == 503
        assert "not configured" in result.json()["detail"]


def test_public_ai_rejects_cross_site_browser_calls_and_oversized_payloads(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_AI_ENABLED", "1")
    provider = FakeProvider()
    with TestClient(create_app(runtime=ApiRuntime(provider=provider))) as client:
        bad_origin = client.post(
            "/api/v1/public/help/ask", json={"question": "Search help"},
            headers={"origin": "https://unrelated.example"}
        )
        assert bad_origin.status_code == 403
        assert client.post("/api/v1/public/help/ask",
            json={"question": "x" * 451}).status_code == 422
        assert client.post("/api/v1/public/help/ask",
            json={"question": "ab"}).status_code == 422
        assert provider.calls == []


def test_public_ai_three_questions_per_window_and_no_paid_access(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_AI_ENABLED", "1")
    provider = FakeProvider()
    with TestClient(create_app(runtime=ApiRuntime(provider=provider))) as client:
        for _ in range(3):
            response = client.post("/api/v1/public/help/ask",
                                   json={"question": "How to register?"})
            assert response.status_code == 200
            assert "source" not in response.json()
        limited = client.post("/api/v1/public/help/ask",
                              json={"question": "One more please"})
        assert limited.status_code == 429
        assert int(limited.headers["retry-after"]) >= 1
        assert len(provider.calls) == 3

def test_public_ai_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("VALYQON_PUBLIC_AI_ENABLED", raising=False)
    provider = FakeProvider()
    with TestClient(create_app(runtime=ApiRuntime(provider=provider))) as client:
        response = client.post("/api/v1/public/help/ask",
                               json={"question": "How does search work?"})
        assert response.status_code == 503
        assert "not enabled" in response.json()["detail"]
        assert provider.calls == []


def test_disabled_or_unconfigured_guest_ai_does_not_spend_request_budget(monkeypatch):
    monkeypatch.delenv("VALYQON_PUBLIC_AI_ENABLED", raising=False)
    with TestClient(create_app(runtime=ApiRuntime(provider=FakeProvider()))) as client:
        for _ in range(5):
            response = client.post("/api/v1/public/help/ask", json={"question": "How to register?"})
            assert response.status_code == 503
        assert not client.app.state.guest_ai_limiter._events

    monkeypatch.setenv("VALYQON_PUBLIC_AI_ENABLED", "true")
    with TestClient(create_app(runtime=ApiRuntime())) as client:
        assert client.post("/api/v1/public/help/ask",
                           json={"question": "How to register?"}).status_code == 503
        assert not client.app.state.guest_ai_limiter._events


def test_global_provider_cost_cap_blocks_even_a_fresh_ip(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_AI_ENABLED", "true")
    provider = FakeProvider()
    with TestClient(create_app(runtime=ApiRuntime(provider=provider))) as client:
        limiter = client.app.state.guest_ai_limiter
        for _ in range(48):
            assert limiter.consume("guest-ai-global", "public", "public") is None
        limited = client.post("/api/v1/public/help/ask",
                              json={"question": "Explain how guest search works?"})
        assert limited.status_code == 429
        assert int(limited.headers["retry-after"]) >= 1
        assert provider.calls == []
