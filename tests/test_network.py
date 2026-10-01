import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.bot.config import load_settings as bot_settings
from app.llm.config import load_settings as llm_settings
from app.network import configure_http_environment, outbound_proxy

PROXY = "http://proxy.example:8080"
OVERRIDE = "http://telegram.example:8888"
ENV = {"TELEGRAM_BOT_TOKEN": "123456789:" + "X" * 35,
       "GIGACHAT_CREDENTIALS": "synthetic", "GIGACHAT_MODEL": "test"}
MISSING = Path("nonexistent-test-config.env")


class NetworkTests(unittest.TestCase):
    def test_direct(self):
        with patch.dict(os.environ, ENV, clear=True):
            self.assertIsNone(bot_settings(MISSING).proxy_url)
            llm_settings(MISSING)
            self.assertNotIn("HTTPS_PROXY", os.environ)

    def test_general_and_override(self):
        for override, expected in (("", PROXY), (OVERRIDE, OVERRIDE)):
            with self.subTest(override=override), patch.dict(os.environ, ENV | {
                "OUTBOUND_PROXY_URL": PROXY, "TELEGRAM_PROXY_URL": override}, clear=True):
                self.assertEqual(bot_settings(MISSING).proxy_url, expected)
                llm_settings(MISSING)
                for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
                    self.assertEqual(os.environ[name], PROXY)

    def test_legacy_telegram_only(self):
        with patch.dict(os.environ, ENV | {"TELEGRAM_PROXY_URL": OVERRIDE}, clear=True):
            self.assertEqual(bot_settings(MISSING).proxy_url, OVERRIDE)
            llm_settings(MISSING)
            self.assertNotIn("HTTPS_PROXY", os.environ)

    def test_inherited_network_unchanged(self):
        original = {"HTTPS_PROXY": PROXY, "NO_PROXY": "localhost", "OUTBOUND_PROXY_URL": ""}
        with patch.dict(os.environ, original, clear=True):
            configure_http_environment()
            self.assertEqual(dict(os.environ), original)

    def test_ca_scope_timeout_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            ca = Path(directory) / "test.pem"
            ca.touch()
            with patch.dict(os.environ, ENV | {
                "OUTBOUND_PROXY_URL": PROXY, "GIGACHAT_CA_BUNDLE_FILE": str(ca),
                "GIGACHAT_SCOPE": "GIGACHAT_API_B2B", "GIGACHAT_TIMEOUT": "42",
                "NO_PROXY": "localhost"}, clear=True):
                config = llm_settings(MISSING)
                self.assertEqual(config.ca_bundle_file, str(ca))
                self.assertEqual(config.scope, "GIGACHAT_API_B2B")
                self.assertEqual(config.timeout, 42)
                self.assertEqual(os.environ["NO_PROXY"], "localhost")

    def test_invalid_proxy_safe_error(self):
        with patch.dict(os.environ, {"OUTBOUND_PROXY_URL": "http://user:secret@host:bad"}, clear=True):
            with self.assertRaises(ValueError) as error:
                outbound_proxy()
            self.assertNotIn("secret", str(error.exception))

    def test_httpx_resolves_environment_without_request(self):
        from httpx._utils import get_environment_proxies
        with patch.dict(os.environ, {"OUTBOUND_PROXY_URL": PROXY}, clear=True):
            configure_http_environment()
            mapping = get_environment_proxies()
            self.assertEqual(mapping["https://"], PROXY)
            self.assertEqual(mapping["http://"], PROXY)
