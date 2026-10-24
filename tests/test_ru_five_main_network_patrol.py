"""Main-only trusted RU five-source watch: safety, not source-ingestion proof."""
from pathlib import Path
import unittest

from scripts.ru_trusted_live_probe import (
    ON_DEMAND_TARGETS, RECOVERY_FIVE, TARGETS, Target,
)

ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / ".github/workflows/ru-five-trusted-network-patrol.yml"


class TrustedPublisherWatchContracts(unittest.TestCase):
    def test_five_fixed_independent_official_origins_not_user_urls(self):
        self.assertEqual(tuple(RECOVERY_FIVE), (
            "ingushetia", "chechnya", "roseltorg", "gpb", "tektorg",
        ))
        self.assertEqual(RECOVERY_FIVE["ingushetia"], TARGETS["fabrikant_44_mirror"])
        self.assertEqual(RECOVERY_FIVE["chechnya"], ON_DEMAND_TARGETS["eis_official_home"])
        self.assertEqual(RECOVERY_FIVE["roseltorg"], TARGETS["roseltorg"])
        self.assertEqual(RECOVERY_FIVE["gpb"], Target(
            "etpgpb.ru", "/procedures.rss", "rss",
        ))
        self.assertEqual(RECOVERY_FIVE["tektorg"], TARGETS["tektorg"])
        self.assertEqual(len({(v.host, v.path) for v in RECOVERY_FIVE.values()}), 5)
        for target in RECOVERY_FIVE.values():
            self.assertTrue(target.path.startswith("/"))
            self.assertNotIn("?", target.path)
            self.assertNotIn("#", target.path)
            self.assertNotIn("\\", target.path)
            self.assertIn(target.mode, ("html", "rss"))

    def test_automatic_watch_cannot_run_unreviewed_pr_code_on_ru_runner(self):
        raw = WATCH.read_text(encoding="utf-8")
        self.assertIn("on:\n  push:\n    branches: [main]\n", raw)
        self.assertIn("  schedule:\n    - cron:", raw)
        self.assertIn("  workflow_dispatch:\n", raw)
        self.assertNotIn("  pull_request:", raw)
        self.assertNotIn("  pull_request_target:", raw)
        self.assertNotIn("  workflow_run:", raw)
        self.assertIn("if: github.ref == 'refs/heads/main'", raw)
        self.assertIn("runs-on: [self-hosted, Linux, X64]", raw)
        self.assertIn('test "$ACTUAL_RUNNER_NAME" = "VALYQON-RU-01"', raw)
        self.assertLess(
            raw.index('test "$ACTUAL_RUNNER_NAME" = "VALYQON-RU-01"'),
            raw.index("uses: actions/checkout@v4"),
        )
        self.assertIn("ref: ${{ github.sha }}", raw)
        self.assertIn("persist-credentials: false", raw)
        self.assertIn("permissions:\n  contents: read\n", raw)
        self.assertIn("cancel-in-progress: false", raw)
        self.assertNotIn("secrets.", raw)
        self.assertNotIn("github.event.pull_request", raw)

    def test_watch_can_only_run_the_fixed_no_ingestion_safe_probe(self):
        raw = WATCH.read_text(encoding="utf-8")
        self.assertIn(
            "python -B -m scripts.ru_trusted_live_probe priority_five_network",
            raw,
        )
        for prohibited in (
            "curl -k", "verify=False", "git checkout HEAD",
            "git pull", "pip install -e", "docker ", "telegram",
            "run_leased_connector", "actions/upload-artifact",
        ):
            self.assertNotIn(prohibited, raw)
        script = (ROOT / "scripts/ru_trusted_live_probe.py").read_text(
            encoding="utf-8",
        )
        for marker in (
            "RU_FIVE_FIRSTPARTY_HTTPS_VISIBLE=",
            "RU_FIVE_ORIGINAL_DETAIL_VERIFIED=NO",
            "RU_FIVE_WORKER_SQL_ACCEPTED=NO",
            "RU_FIVE_REAL_TELEGRAM_ACK=NO",
            "PRODUCTION_CHANGED=NO",
        ):
            self.assertIn(marker, script)
        self.assertIn("def checked_ips(", script)
        self.assertIn("publisher_tls_context(host)", script)
        self.assertIn("server_hostname=self.host", script)


if __name__ == "__main__":
    unittest.main()
