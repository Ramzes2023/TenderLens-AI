"""Real anonymous AI must answer Russian questions in Russian, not English."""
from fastapi.testclient import TestClient

from app.api.guest_language import (
    answer_uses_question_script, output_language_for,
)
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
        return FakeReply(self.answers[min(len(self.prompts)-1, len(self.answers)-1)])


def ask(client, question):
    return client.post("/api/v1/public/help/ask", json={"question": question})


def test_russian_answers_stay_in_russian_on_first_attempt(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_AI_ENABLED", "true")
    provider = SequenceProvider("Гостевой поиск показывает сохранённые тендеры.")
    with TestClient(create_isolated_guest_app(lambda: provider)) as client:
        reply = ask(client, "Как работает гостевой поиск?")
        assert reply.status_code == 200
        assert reply.json()["scope"] == "public_product_only"
        assert "Гостевой поиск" in reply.json()["answer"]
    assert len(provider.prompts) == 1
    assert "ОБЯЗАТЕЛЬНО ОТВЕЧАЙ ПО-РУССКИ" in provider.prompts[0][0]
    assert provider.prompts[0][0].rstrip().endswith("Не отвечай по-английски.")
    assert provider.prompts[0][1] == 260


def test_wrong_language_completion_gets_single_metered_correction(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_AI_ENABLED", "true")
    provider = SequenceProvider(
        "Guest search uses stored notices and hides sensitive details.",
        "Гостевой поиск использует сохранённые извещения и скрывает детали.",
    )
    with TestClient(create_isolated_guest_app(lambda: provider)) as client:
        reply = ask(client, "Как работает гостевой поиск?")
        assert reply.status_code == 200
        assert reply.json()["answer"].startswith("Гостевой поиск")
        assert client.app.state.guest_ai_limiter.identifier_retry_after(
            "guest-ai-global", "public", "public"
        ) is None
        assert sum(len(events) for (name, _, _), events
                   in client.app.state.guest_ai_limiter._events.items()
                   if name == "guest-ai-global") == 4  # two keys x two calls
    assert len(provider.prompts) == 2
    assert "previous completion violated" in provider.prompts[1][0]


def test_two_english_replies_never_leak_english_as_success(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_AI_ENABLED", "true")
    provider = SequenceProvider("Only English answer available.")
    with TestClient(create_isolated_guest_app(lambda: provider)) as client:
        reply = ask(client, "Где ссылки на площадки?")
        assert reply.status_code == 503
        assert "Only English" not in reply.text
    assert len(provider.prompts) == 2


def test_second_provider_call_respects_global_budget(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_AI_ENABLED", "true")
    provider = SequenceProvider("The answer is in English.")
    with TestClient(create_isolated_guest_app(lambda: provider)) as client:
        limiter = client.app.state.guest_ai_limiter
        for _ in range(47):
            assert limiter.consume("guest-ai-global", "public", "public") is None
        reply = ask(client, "Как работает гостевой поиск?")
        assert reply.status_code == 429
        assert "retry-after" in reply.headers
    assert len(provider.prompts) == 1


def test_original_english_requests_are_not_rewritten(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_AI_ENABLED", "true")
    provider = SequenceProvider("Guest search uses stored public notices.")
    with TestClient(create_isolated_guest_app(lambda: provider)) as client:
        reply = ask(client, "How does guest search work?")
        assert reply.status_code == 200
        assert reply.json()["answer"] == "Guest search uses stored public notices."
    assert len(provider.prompts) == 1


def test_georgian_question_must_receive_georgian_script(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_AI_ENABLED", "true")
    provider = SequenceProvider(
        "Public search uses saved notices.",
        "სტუმრის ძებნა იყენებს უკვე შენახულ განცხადებებს.",
    )
    with TestClient(create_isolated_guest_app(lambda: provider)) as client:
        reply = ask(client, "როგორ მუშაობს სტუმრის ძებნა?")
        assert reply.status_code == 200
        assert "სტუმრის" in reply.json()["answer"]
    assert len(provider.prompts) == 2


def test_cyrillic_script_language_distinction_is_not_russian_only():
    assert output_language_for("Як працює пошук закупівель?").name == "Ukrainian"
    assert output_language_for("Как работает поиск?").name == "Russian"
    assert output_language_for("გამარჯობა როგორ ხართ?").name == "Georgian"
    assert output_language_for("How does search work?").script is None
    assert output_language_for("Nasıl çalışır?").script is None
    assert answer_uses_question_script(
        "Гостевой поиск использует сохранённые извещения.",
        output_language_for("Как работает поиск?")
    )
    assert not answer_uses_question_script(
        "Guest search uses saved notices.",
        output_language_for("Как работает поиск?")
    )
