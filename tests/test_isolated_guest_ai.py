"""The isolated AI pod cannot open or migrate the VALYQON production database."""
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.isolated_guest_ai import create_isolated_guest_app
from app.llm.base import LLMConfigurationError


class FakeReply:
    text = "VALYQON public guest search uses already stored notices."


class FakeProvider:
    def __init__(self):
        self.calls = []

    async def generate(self, prompt, *, max_tokens):
        self.calls.append((prompt, max_tokens))
        return FakeReply()


def test_standalone_has_only_product_help_and_local_health(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_AI_ENABLED", "true")
    provider = FakeProvider()
    with TestClient(create_isolated_guest_app(lambda: provider)) as client:
        assert not hasattr(client.app.state.runtime, "database")
        assert not hasattr(client.app.state.runtime, "tender_repository")
        # Exercise exposed HTTP paths; newer FastAPI uses lazy _IncludedRouter metadata.
        for endpoint in ("/login", "/api/v1/tenders", "/api/v1/companies",
                         "/dashboard", "/openapi.json", "/docs"):
            assert client.get(endpoint).status_code == 404
        good = client.post("/api/v1/public/help/ask",
            json={"question": "Explain guest search."},
            headers={"origin": "http://testserver"})
        assert good.status_code == 200
        assert good.json()["scope"] == "public_product_only"
        assert "public" in good.json()["answer"]
        assert len(provider.calls) == 1
        assert provider.calls[0][1] == 260


def test_isolated_guest_ai_stays_disabled_unless_opted_in(monkeypatch):
    monkeypatch.delenv("VALYQON_PUBLIC_AI_ENABLED", raising=False)
    fake = FakeProvider()
    with TestClient(create_isolated_guest_app(lambda: fake)) as client:
        result = client.post("/api/v1/public/help/ask",
            json={"question": "How to search?"})
        assert result.status_code == 503
        assert fake.calls == []


def test_missing_credentials_fail_closed_without_db(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_AI_ENABLED", "true")

    def invalid():
        raise LLMConfigurationError("redacted")

    with TestClient(create_isolated_guest_app(invalid)) as client:
        assert client.get("/_internal/health").json() == {
            "service": "valyqon-guest-ai-only",
            "provider_initialized": False,
            "provider_inference_verified": False,
        }
        assert client.post("/api/v1/public/help/ask",
            json={"question": "How to search?"}).status_code == 503


def test_isolated_ai_same_origin_and_cost_cap(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_AI_ENABLED", "true")
    fake = FakeProvider()
    with TestClient(create_isolated_guest_app(lambda: fake)) as client:
        assert client.post("/api/v1/public/help/ask",
            json={"question": "Search help?"},
            headers={"origin": "https://untrusted.example"}).status_code == 403
        for _ in range(48):
            assert client.app.state.guest_ai_limiter.consume(
                "guest-ai-global", "public", "public"
            ) is None
        r = client.post("/api/v1/public/help/ask",
            json={"question": "Search help?"})
        assert r.status_code == 429
        assert fake.calls == []


def test_isolated_compose_cannot_touch_existing_api_or_db():
    compose = Path("compose.isolated-guest-ai.yaml").read_text(encoding="utf-8")
    assert "services:\n  guest-ai:" in compose
    for invalid in ("  api:", "  bot:", "  caddy:", "    ports:", "    volumes:",
                    "DATABASE_URL:", "GROQ_API_KEY:", "GIGACHAT_CREDENTIALS:"):
        assert invalid not in compose
    assert "external: true" in compose
    assert "tenderlens-vps_edge" in compose
    assert "VALYQON_GUEST_AI_ENV_FILE:?" in compose
    assert "VALYQON_PUBLIC_AI_ENABLED: \"true\"" in compose
    assert "--workers\n      - \"1\"" in compose
    assert "read_only: true" in compose
