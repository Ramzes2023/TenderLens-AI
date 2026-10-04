import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.api.config import ApiSettings, load_api_settings
from app.api import __main__ as api_main


class Phase19TrustedProxyTests(unittest.TestCase):
    def test_default_trusted_proxy_is_localhost(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("TENDERLENS_TRUSTED_PROXY_IPS", None)
                settings = load_api_settings(
                    Path(tmp) / "missing.env"
                )

        self.assertEqual(
            settings.forwarded_allow_ips,
            "127.0.0.1",
        )

    def test_trusted_proxy_networks_can_be_configured(self):
        value = "10.0.0.0/8,172.16.0.0/12"

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(
                os.environ,
                {"TENDERLENS_TRUSTED_PROXY_IPS": value},
                clear=False,
            ):
                settings = load_api_settings(
                    Path(tmp) / "missing.env"
                )

        self.assertEqual(
            settings.forwarded_allow_ips,
            value,
        )

    def test_uvicorn_receives_explicit_proxy_configuration(self):
        settings = ApiSettings(
            host="0.0.0.0",
            port=8000,
            reload=False,
            api_key=None,
            forwarded_allow_ips="172.16.0.0/12",
        )

        with (
            patch(
                "app.api.__main__.load_api_settings",
                return_value=settings,
            ),
            patch(
                "app.api.__main__.uvicorn.run"
            ) as run,
        ):
            result = api_main.main()

        self.assertEqual(result, 0)
        run.assert_called_once()

        kwargs = run.call_args.kwargs

        self.assertTrue(kwargs["proxy_headers"])
        self.assertEqual(
            kwargs["forwarded_allow_ips"],
            "172.16.0.0/12",
        )


if __name__ == "__main__":
    unittest.main()
