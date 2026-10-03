from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from app.deployment.healthcheck import check

ROOT = Path(__file__).resolve().parents[1]


class FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


class DeploymentHealthcheckTests(unittest.TestCase):
    def test_healthcheck_accepts_ok_payload(self):
        body = json.dumps({"status": "ok"}).encode("utf-8")
        with patch("app.deployment.healthcheck.urlopen", return_value=FakeResponse(body)):
            self.assertTrue(check("http://example.test/health"))

    def test_healthcheck_rejects_degraded_payload(self):
        body = json.dumps({"status": "degraded"}).encode("utf-8")
        with patch("app.deployment.healthcheck.urlopen", return_value=FakeResponse(body)):
            self.assertFalse(check("http://example.test/health"))

    def test_healthcheck_rejects_network_error(self):
        with patch("app.deployment.healthcheck.urlopen", side_effect=OSError("offline")):
            self.assertFalse(check("http://example.test/health"))


class DeploymentAssetsTests(unittest.TestCase):
    def test_dockerfile_runs_non_root_with_healthcheck(self):
        text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("USER tenderlens", text)
        self.assertIn("HEALTHCHECK", text)
        self.assertIn('CMD ["python", "-m", "app.api"]', text)
        self.assertIn("FASTEMBED_CACHE_PATH=/app/data/fastembed_cache", text)

    def test_dockerignore_excludes_secrets_and_local_data(self):
        lines = set((ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())
        self.assertIn(".env", lines)
        self.assertIn("data", lines)
        self.assertIn(".venv", lines)

    def test_compose_binds_locally_and_persists_data(self):
        text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn("TENDERLENS_DOCKER_BIND:-127.0.0.1", text)
        self.assertIn("tenderlens_data:/app/data", text)
        self.assertIn("DATABASE_URL: sqlite:////app/data/tenderlens.db", text)
        self.assertIn("RAG_QDRANT_PATH: /app/data/qdrant", text)
        self.assertIn("image: tenderlens-ai:1.6.0", text)
        self.assertIn("  bot:", text)
        self.assertIn('command: ["python", "-m", "app.bot"]', text)
        self.assertIn("RAG_QDRANT_PATH: /app/data/qdrant-bot", text)
        self.assertIn('OUTBOUND_PROXY_URL: "${DOCKER_OUTBOUND_PROXY_URL:-}"', text)
        self.assertIn('TELEGRAM_PROXY_URL: "${DOCKER_TELEGRAM_PROXY_URL:-}"', text)
        self.assertIn("healthcheck:", text)
        self.assertIn("disable: true", text)


if __name__ == "__main__":
    unittest.main()
