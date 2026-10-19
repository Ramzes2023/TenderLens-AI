"""Offline configuration guards; these are never real Telegram delivery proof."""
import asyncio

import pytest

from scripts.ru_ingushetia_telegram_test import check_real_telegram


@pytest.mark.parametrize('contents', [
    '',
    'TELEGRAM_BOT_TOKEN=production-must-not-be-used\nTELEGRAM_CHAT_ID=123\n',
    'INGUSHETIA_TEST_TELEGRAM_BOT_TOKEN=test\n',
    'INGUSHETIA_TEST_TELEGRAM_BOT_TOKEN=test\nINGUSHETIA_TEST_TELEGRAM_CHAT_ID=not-a-chat\n',
    'INGUSHETIA_TEST_TELEGRAM_BOT_TOKEN=test\nINGUSHETIA_TEST_TELEGRAM_CHAT_ID=0\n',
])
def test_test_destination_must_be_explicit_before_any_bot_or_subscription(tmp_path, monkeypatch, contents):
    import aiogram

    def forbidden_bot(*args, **kwargs):
        pytest.fail('Invalid test settings must not construct a Telegram client')

    monkeypatch.setattr(aiogram, 'Bot', forbidden_bot)
    config = tmp_path / 'dedicated-test.env'
    config.write_text(contents, encoding='utf-8')
    db = tmp_path / 'must-not-exist.sqlite'
    with pytest.raises(ValueError):
        asyncio.run(check_real_telegram(None, None, (), db, config))
    assert not db.exists()
