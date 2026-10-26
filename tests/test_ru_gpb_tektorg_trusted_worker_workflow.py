"""Offline safety guard for strictly main-only real procurement acceptance.

This file never contacts a publisher or Telegram and cannot be used as live proof.
"""
from pathlib import Path
import ast
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ru-gpb-tektorg-trusted-firstparty-worker.yml"


class TrustedRealPublisherReleaseGate(unittest.TestCase):
    def test_only_manual_main_runs_can_reach_the_named_server(self):
        body = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", body)
        self.assertIn("pull_request:", body)
        self.assertIn("if: github.event_name == 'pull_request'", body)
        self.assertIn("github.event_name == 'workflow_dispatch'", body)
        self.assertIn("github.ref == 'refs/heads/main'", body)
        self.assertIn("github.repository == 'Ramzes2023/TenderLens-AI'", body)
        self.assertEqual(body.count("runs-on: [self-hosted, Linux, X64]"), 1)
        self.assertIn('test "$ACTUAL_RUNNER_NAME" = "VALYQON-RU-01"', body)
        self.assertLess(body.index("Refuse non-approved RU runner"),
                        body.index("uses: actions/checkout@v4", body.index("current-real-firstparty-worker-to-ephemeral-sql:")))
        self.assertIn("persist-credentials: false", body)
        self.assertIn("ref: ${{ github.sha }}", body)
        self.assertIn("permissions:\n  contents: read", body)
        self.assertIn("cancel-in-progress: false", body)

    def test_manual_input_has_exact_two_known_source_keys_and_modules(self):
        body = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("type: choice", body)
        self.assertIn("          - gpb_etp_public", body)
        self.assertIn("          - tektorg", body)
        self.assertIn('case "$APPROVED_SOURCE" in', body)
        self.assertIn("python -B -m scripts.ci_ru_gpb_public_worker", body)
        self.assertIn("python -B -m scripts.ci_ru_tektorg_fenced_acceptance", body)
        self.assertIn("RU_REAL_SOURCE=REJECTED_UNKNOWN", body)
        self.assertIn("set -euo pipefail", body)
        self.assertIn("RU_REAL_USER_TELEGRAM_RECEIPT=NOT_TESTED", body)
        self.assertIn("PRODUCTION_CHANGED=NO", body)
        self.assertNotIn("follow_redirects=True", body)
        self.assertNotIn("verify=False", body)
        self.assertNotIn("curl -k", body)
        self.assertNotIn("bot.send_message", body)

    def test_actual_main_acceptance_scripts_exist_and_parse_not_fixtures(self):
        for name in ("ci_ru_gpb_public_worker", "ci_ru_tektorg_fenced_acceptance"):
            source = ROOT / "scripts" / (name + ".py")
            self.assertTrue(source.is_file(), name)
            contents = source.read_text(encoding="utf-8")
            ast.parse(contents, filename=str(source))
            self.assertIn("Worker", contents)
            self.assertIn("SQLite", contents)
            self.assertNotIn("verify=False", contents)
            self.assertNotIn("follow_redirects=True", contents)


if __name__ == "__main__":
    unittest.main()
