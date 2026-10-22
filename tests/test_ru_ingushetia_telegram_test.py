"""Offline Bot API contracts. No real Telegram request or delivery claim."""
import asyncio
import json

import httpx
import pytest

from scripts.ru_ingushetia_telegram_test import TestDeliveryError, load_config, deliver, main


def env():
    return {"TEST_TELEGRAM_SEND_AUTHORIZED": "YES_TEST_CHAT_ONLY",
            "TEST_TELEGRAM_BOT_TOKEN": "12345:" + "a" * 35,
            "TEST_TELEGRAM_BOT_ID": "12345", "TEST_TELEGRAM_CHAT_ID": "-100987654321"}


@pytest.mark.parametrize("change", [
    {"TEST_TELEGRAM_SEND_AUTHORIZED": ""}, {"TEST_TELEGRAM_BOT_TOKEN": ""},
    {"TEST_TELEGRAM_CHAT_ID": "@customer"}, {"TEST_TELEGRAM_BOT_ID": "67890"},
])
def test_missing_or_mismatched_test_configuration_fails_closed(change):
    with pytest.raises(TestDeliveryError):
        load_config(env() | change, send=True, confirmed_chat=env()["TEST_TELEGRAM_CHAT_ID"])


def test_production_names_and_absent_cli_consent_never_authorize_send(monkeypatch, capsys):
    with pytest.raises(TestDeliveryError):
        load_config({"BOT_TOKEN": env()["TEST_TELEGRAM_BOT_TOKEN"], "TELEGRAM_CHAT_ID": "1"}, send=True)
    with pytest.raises(TestDeliveryError):
        load_config(env(), confirmed_chat=env()["TEST_TELEGRAM_CHAT_ID"])
    with pytest.raises(TestDeliveryError):
        load_config(env(), send=True, confirmed_chat="1")
    monkeypatch.setattr(httpx.AsyncClient, "__init__", lambda *a, **k: pytest.fail("Network client created"))
    assert main([]) == 0
    assert "NETWORK_REQUESTS=0" in capsys.readouterr().out


@pytest.mark.parametrize("failure", [None, "bot", "chat", "channel", "api", "receipt", "timeout", "redirect"])
def test_one_allowlisted_send_only_after_identity_checks_and_no_retry(failure):
    cfg = load_config(env(), send=True, confirmed_chat=env()["TEST_TELEGRAM_CHAT_ID"])
    assert cfg.token not in repr(cfg)
    calls = []

    def respond(request):
        assert request.url.host == "api.telegram.org" and request.url.scheme == "https"
        assert request.method == "POST" and not request.url.query
        method = request.url.path.rsplit("/", 1)[-1]
        calls.append(method)
        data = json.loads(request.content)
        if method == "getMe":
            result = {"id": 99 if failure == "bot" else cfg.bot_id, "is_bot": True}
        elif method == "getChat":
            assert data == {"chat_id": cfg.chat_id}
            result = {"id": 99 if failure == "chat" else cfg.chat_id,
                      "type": "channel" if failure == "channel" else "supergroup"}
        else:
            assert method == "sendMessage"
            assert data["chat_id"] == cfg.chat_id
            assert "ТЕСТ" in data["text"] and "не новая закупка" in data["text"]
            assert data["disable_notification"] is True
            if failure == "timeout":
                raise httpx.ReadTimeout("secret " + cfg.token)
            if failure == "redirect":
                return httpx.Response(302, headers={"Location": "https://attacker.invalid"})
            if failure == "api":
                return httpx.Response(200, json={"ok": False, "description": cfg.token})
            result = {"message_id": 42, "chat": {"id": 99 if failure == "receipt" else cfg.chat_id},
                      "text": data["text"]}
        return httpx.Response(200, json={"ok": True, "result": result})

    if failure:
        with pytest.raises(TestDeliveryError) as error:
            asyncio.run(deliver(cfg, transport=httpx.MockTransport(respond)))
        assert cfg.token not in str(error.value)
        assert "no automatic retry" in str(error.value)
        assert calls.count("sendMessage") == (0 if failure in {"bot", "chat", "channel"} else 1)
    else:
        result = asyncio.run(deliver(cfg, transport=httpx.MockTransport(respond)))
        assert result["state"] == "BOT_API_ACKNOWLEDGED" and result["message_id"] == 42
        assert result["recipient_confirmation"] == "PENDING"
        assert cfg.token not in json.dumps(result)
        assert calls == ["getMe", "getChat", "sendMessage"]


def test_optin_telegram_workflow_cannot_autosend_on_git_push_or_pr():
    """Static deployment safety: dedicated Bot API workflow is manual-only."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/ru-ingushetia-test-telegram-optin.yml").read_text(
        encoding="utf-8"
    )
    assert "  workflow_dispatch:" in workflow
    assert "  push:" not in workflow
    assert "  pull_request:" not in workflow
    assert "  schedule:" not in workflow
    assert "authorize_test_send:" in workflow
    assert "default: false" in workflow
    assert "confirm_test_chat:" in workflow
    assert "dedicated-bot-api-test:" in workflow
    assert "inputs.authorize_test_send == true" in workflow
    assert "TEST_TELEGRAM_SEND_AUTHORIZED: YES_TEST_CHAT_ONLY" in workflow
    assert "secrets.VALYQON_INGUSHETIA_TEST_BOT_TOKEN" in workflow
    assert "secrets.VALYQON_INGUSHETIA_TEST_CHAT_ID" in workflow
    assert "vars.VALYQON_INGUSHETIA_TEST_BOT_ID" in workflow
    assert "secrets.TELEGRAM_BOT_TOKEN" not in workflow
    assert "BOT_TOKEN:" not in workflow.replace("TEST_TELEGRAM_BOT_TOKEN:", "")
