"""Prevent a repeat of the observed LIVE English-question/Chinese-answer failure."""
from fastapi.testclient import TestClient

from app.api.guest_language import output_language_for, answer_uses_question_script
from app.api.isolated_guest_ai import create_isolated_guest_app


class FakeReply:
    def __init__(self, text):
        self.text = text


class SequenceProvider:
    def __init__(self, *answers):
        self.answers = answers
        self.prompts = []

    async def generate(self, prompt, *, max_tokens):
        self.prompts.append((prompt, max_tokens))
        return FakeReply(self.answers[min(len(self.prompts) - 1, len(self.answers) - 1)])


def ask(client, question):
    return client.post("/api/v1/public/help/ask", json={"question": question})


def test_live_regression_chinese_reply_to_english_is_corrected(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_AI_ENABLED", "true")
    provider = SequenceProvider(
        "VALYQON AI 使用已保存的采购公告，不直接访问实时采购平台。",
        "Guest search uses stored public notices and hides details.",
    )
    with TestClient(create_isolated_guest_app(lambda: provider)) as client:
        response = ask(client, "How does guest search work?")
        assert response.status_code == 200
        assert response.json()["scope"] == "public_product_only"
        assert response.json()["answer"].startswith("Guest search")
        assert sum(len(events) for (name, _, _), events
                   in client.app.state.guest_ai_limiter._events.items()
                   if name == "guest-ai-global") == 4
    assert len(provider.prompts) == 2
    assert "REPLY ONLY IN ENGLISH" in provider.prompts[0][0]
    assert "All explanatory sentences MUST be in the question's original" in provider.prompts[1][0]
    assert "no English explanatory sentences" not in provider.prompts[1][0]


def test_chinese_reply_twice_fails_closed_instead_of_returning_200(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_AI_ENABLED", "true")
    provider = SequenceProvider("您可以在 VALYQON AI 查看公开采购标题和价格。")
    with TestClient(create_isolated_guest_app(lambda: provider)) as client:
        reply = ask(client, "How does guest search work?")
        assert reply.status_code == 503
        assert "VALYQON" not in reply.text
        assert "您可以" not in reply.text
    assert len(provider.prompts) == 2


def test_english_chinese_retry_respects_global_provider_budget(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_AI_ENABLED", "true")
    provider = SequenceProvider("采购公告的资料在系统中。",
                                "Guest search uses stored notices.")
    with TestClient(create_isolated_guest_app(lambda: provider)) as client:
        limiter = client.app.state.guest_ai_limiter
        for _ in range(47):
            assert limiter.consume("guest-ai-global", "public", "public") is None
        response = ask(client, "How does guest search work?")
        assert response.status_code == 429
        assert int(response.headers["retry-after"]) >= 1
    assert len(provider.prompts) == 1


def test_clear_wrong_latin_language_retries_once(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_AI_ENABLED", "true")
    provider = SequenceProvider(
        "La ricerca funziona usando gli avvisi memorizzati.",
        "Guest search uses saved procurement notices.",
    )
    with TestClient(create_isolated_guest_app(lambda: provider)) as client:
        response = ask(client, "How does guest search work?")
        assert response.status_code == 200
        assert response.json()["answer"].startswith("Guest search")
    assert len(provider.prompts) == 2


def test_italian_question_english_reply_then_italian_reply(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_AI_ENABLED", "true")
    provider = SequenceProvider(
        "Guest search uses stored notices.",
        "La ricerca funziona mostrando avvisi già salvati.",
    )
    with TestClient(create_isolated_guest_app(lambda: provider)) as client:
        response = ask(client, "Come funziona la ricerca ospite?")
        assert response.status_code == 200
        assert response.json()["answer"].startswith("La ricerca")
    assert len(provider.prompts) == 2


def test_latin_response_contract_blocks_foreign_scripts_and_obvious_language_switches():
    english = output_language_for("How does guest search work?")
    assert english.script == "latin" and english.name == "English"
    assert not answer_uses_question_script("采购公告查询方法。", english)
    assert not answer_uses_question_script("VALYQON AI 使用已保存的采购公告。", english)
    assert not answer_uses_question_script("La ricerca funziona con dati salvati.", english)
    assert answer_uses_question_script("Guest search reads stored notices.", english)
    italian = output_language_for("Come funziona la ricerca ospite?")
    assert not answer_uses_question_script("Guest search uses stored notices.", italian)
    assert answer_uses_question_script("La ricerca funziona con avvisi salvati.", italian)
