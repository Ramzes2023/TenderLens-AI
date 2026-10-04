import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Phase19PublicEdgeTests(unittest.TestCase):
    def test_public_compose_exposes_only_caddy(self):
        text = (ROOT / "compose.public.yaml").read_text(
            encoding="utf-8"
        )

        api_block = text.split(
            "\n  bot:",
            1,
        )[0]

        self.assertNotIn(
            "\n    ports:",
            api_block,
        )
        self.assertIn(
            '    expose:\n      - "8000"',
            api_block,
        )

        self.assertIn(
            '      - "${TENDERLENS_HTTP_PORT:-80}:80"',
            text,
        )
        self.assertIn(
            '      - "${TENDERLENS_HTTPS_PORT:-443}:443"',
            text,
        )
        self.assertIn(
            '      - "${TENDERLENS_HTTPS_PORT:-443}:443/udp"',
            text,
        )

    def test_public_compose_pins_caddy_and_proxy_identity(self):
        text = (ROOT / "compose.public.yaml").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "image: caddy:2.11.6-alpine",
            text,
        )
        self.assertIn(
            "TENDERLENS_TRUSTED_PROXY_IPS: 172.30.19.2",
            text,
        )
        self.assertIn(
            "ipv4_address: 172.30.19.2",
            text,
        )
        self.assertIn(
            "ipv4_address: 172.30.19.3",
            text,
        )
        self.assertIn(
            "ipv4_address: 172.30.19.4",
            text,
        )
        self.assertIn(
            "subnet: 172.30.19.0/24",
            text,
        )

    def test_caddyfile_has_https_edge_security(self):
        text = (ROOT / "Caddyfile").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "{$TENDERLENS_DOMAIN}",
            text,
        )
        self.assertIn(
            "reverse_proxy api:8000",
            text,
        )
        self.assertIn(
            "Strict-Transport-Security",
            text,
        )
        self.assertIn(
            'X-Content-Type-Options "nosniff"',
            text,
        )
        self.assertIn(
            'X-Frame-Options "DENY"',
            text,
        )
        self.assertIn(
            'Referrer-Policy "no-referrer"',
            text,
        )

    def test_caddy_state_is_persistent(self):
        text = (ROOT / "compose.public.yaml").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "caddy_data:/data",
            text,
        )
        self.assertIn(
            "caddy_config:/config",
            text,
        )
        self.assertIn(
            "tenderlens_data:/app/data",
            text,
        )

    def test_public_environment_example_is_trackable_but_real_file_is_not(self):
        gitignore = (ROOT / ".gitignore").read_text(
            encoding="utf-8"
        )
        dockerignore = (ROOT / ".dockerignore").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            ".env.*",
            gitignore,
        )
        self.assertIn(
            "!.env.public.example",
            gitignore,
        )
        self.assertIn(
            ".env.*",
            dockerignore,
        )
        self.assertIn(
            "!.env.public.example",
            dockerignore,
        )

        example = (
            ROOT / ".env.public.example"
        ).read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "TENDERLENS_DOMAIN=",
            example,
        )
        self.assertIn(
            "ACME_EMAIL=",
            example,
        )


if __name__ == "__main__":
    unittest.main()
