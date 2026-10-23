"""Read-only fixed-host trusted survey policy contracts, not live tender proof."""
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from scripts import ru_blocked_sources_trusted_observation as mod
from scripts.ru_trusted_live_probe import TARGETS, Target


class TrustedBlockedPublisherSurveyTests(unittest.TestCase):
    def test_only_one_request_per_distinct_official_endpoint(self):
        self.assertEqual(mod.MAX_UNIQUE_READS, 5)
        self.assertEqual(mod.PROBE_ORDER, (
            "eis_regional_network_only", "ingushetia_fabrikant_public",
            "roseltorg_public", "gpb_official_rss", "tektorg_public",
        ))
        self.assertEqual(mod.TARGETS_READONLY, {
            "eis_regional_network_only": Target("zakupki.gov.ru", "/"),
            "chechnya_eis_network_only": Target("zakupki.gov.ru", "/"),
            "ingushetia_fabrikant_public": TARGETS["fabrikant_44"],
            "roseltorg_public": TARGETS["roseltorg"],
            "gpb_official_rss": TARGETS["gpb_rss"],
            "tektorg_public": TARGETS["tektorg"],
        })
        self.assertEqual(len({
            (mod.TARGETS_READONLY[key].host, mod.TARGETS_READONLY[key].path)
            for key in mod.PROBE_ORDER
        }), mod.MAX_UNIQUE_READS)

    def test_wrong_runner_refused_before_dns_and_http(self):
        calls = []
        for runner in ("ubuntu-latest", "RU-OTHER", "VALYQON-INT-02", None):
            with self.assertRaises(PermissionError):
                mod.observe_all(runner=runner, reader=lambda t: calls.append(t))
        self.assertEqual(calls, [])

    def test_official_reads_remain_observational_and_do_not_claim_tenders(self):
        requested = []
        def fake_reader(target):
            requested.append(target)
            if target.mode == "rss":
                return ("application/rss+xml", b"<rss><channel><item/></channel></rss>")
            return ("text/html", b"<html><a href='/'>x</a></html>")
        result = mod.observe_all(runner="VALYQON-RU-01", reader=fake_reader)
        self.assertEqual(len(requested), 5)
        self.assertEqual(len(result), 6)
        self.assertEqual(result["gpb_official_rss"]["status"], "RSS_VISIBLE_NOT_INGESTED")
        self.assertTrue(result["chechnya_eis_network_only"]["reused_official_eis_transport"])
        self.assertEqual(result["eis_regional_network_only"]["status"], "HTML_VISIBLE_NOT_INGESTED")
        self.assertFalse(any("verified" in value["status"].lower() for value in result.values()))

    def test_failures_are_redacted_and_per_source(self):
        def failing_reader(target):
            if target.host == "etpgpb.ru":
                raise TimeoutError("SECRET_QUERY_TOKEN_AND_URL")
            return ("text/html", b"<a href='/'>ok</a>")
        result = mod.observe_all(runner="VALYQON-RU-01", reader=failing_reader)
        self.assertEqual(result["gpb_official_rss"],
                         {"status": "BLOCKED", "failure_class": "TimeoutError"})
        self.assertNotIn("SECRET", str(result))

    def test_no_arbitrary_url_choices_ever_trigger_network(self):
        calls = []
        for invalid in ("https://etpgpb.ru/procedures.rss",
                        "evil.example", "gpb_official_rss?q=secret", ""):
            with self.assertRaises(ValueError):
                mod.observe_one(invalid, reader=lambda t: calls.append(t))
        self.assertEqual(calls, [])

    def test_main_entry_never_claims_sqlite_or_telegram_receipt(self):
        with patch.dict("os.environ", {"RUNNER_NAME": "VALYQON-RU-01"}), patch.object(
                mod, "observe_all", return_value={
                    "gpb_official_rss": {"status": "BLOCKED", "failure_class": "TimeoutError"}
                }):
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(mod.main(), 0)
        for marker in (
            "RU_TRUSTED_ORIGINAL_DETAIL_VERIFIED=NO",
            "RU_TRUSTED_WORKER_SQL_VERIFIED=NO",
            "RU_TRUSTED_CUSTOMER_ALERT_ACK=NO",
            "PRODUCTION_CHANGED=NO",
        ):
            self.assertIn(marker, output.getvalue())
        with patch.dict("os.environ", {"RUNNER_NAME": "VALYQON-OTHER"}):
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(mod.main(), 2)
        self.assertIn("BLOCKED_WRONG_RUNNER", output.getvalue())

    def test_selfhosted_workflow_is_not_ever_pr_triggered(self):
        path = (Path(__file__).resolve().parents[1] / ".github/workflows" /
                "ru-blocked-sources-trusted-main.yml")
        raw = path.read_text(encoding="utf-8")
        self.assertIn("on:\n  push:\n    branches: [main]", raw)
        self.assertNotIn("pull_request:", raw)
        self.assertIn("workflow_dispatch:", raw)
        self.assertIn("github.ref == 'refs/heads/main'", raw)
        self.assertIn("github.repository == 'Ramzes2023/TenderLens-AI'", raw)
        self.assertIn("runs-on: [self-hosted, Linux, X64]", raw)
        self.assertIn('test "$ACTUAL_RUNNER_NAME" = "VALYQON-RU-01"', raw)
        self.assertIn("persist-credentials: false", raw)
        self.assertIn("RU_TRUSTED_ORIGINAL_DETAIL_VERIFIED=NO",
                      (Path(__file__).resolve().parents[1] / "scripts" /
                       "ru_blocked_sources_trusted_observation.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
