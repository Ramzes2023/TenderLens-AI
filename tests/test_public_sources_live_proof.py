"""Offline, zero-network contracts for the opt-in public-source live evidence gate."""
import asyncio
import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from app.sources.models import TenderNotice
from scripts import ci_public_sources_live_proof as proof


class _Adapter:
    def __init__(self, payload=None, error=None, delay=0):
        self.payload = payload
        self.error = error
        self.delay = delay
        self.calls = []

    async def fetch(self, limit=20):
        self.calls.append(limit)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.payload


def _notice(identity="n-1", url="https://ted.europa.eu/en/notice/1/html"):
    return TenderNotice(source="ted", external_id=identity,
                        title="Synthetic procurement", url=url)


class PublicSourceProofTests(unittest.TestCase):
    def test_exact_default_eight_and_limits(self):
        self.assertEqual(len(proof.DEFAULT_PUBLIC_SOURCES), 8)
        self.assertEqual(len(set(proof.DEFAULT_PUBLIC_SOURCES)), 8)
        self.assertEqual(proof.MAX_NOTICES, 3)
        self.assertLessEqual(proof.MAX_CONCURRENCY, 3)

    def test_nonempty_normalized_live_only_on_adapter_output(self):
        adapter = _Adapter([_notice()])
        result = asyncio.run(proof.probe_one("ted", adapter))
        self.assertEqual(result, {"source": "ted",
                                  "status": "REAL_NOTICES_NORMALIZED", "count": 1})
        self.assertEqual(adapter.calls, [3])

    def test_empty_is_not_proven_live(self):
        result = asyncio.run(proof.probe_one("ted", _Adapter([])))
        self.assertEqual(result["status"], "NO_VALID_NOTICES_IN_BATCH")
        self.assertEqual(result["count"], 0)

    def test_error_is_redacted_and_not_mislabeled_live(self):
        message = "sensitive-value-never-show.example"
        result = asyncio.run(proof.probe_one("ted", _Adapter(error=RuntimeError(message))))
        self.assertEqual(result, {"source": "ted", "status": "FETCH_OR_NORMALIZATION_FAILED",
                                  "count": 0})
        self.assertNotIn(message, repr(result))

    def test_timeout_does_not_pass(self):
        result = asyncio.run(proof.probe_one("ted", _Adapter([_notice()], delay=0.05),
                                              deadline=0.001))
        self.assertEqual(result["status"], "TIMEOUT")

    def test_duplicate_and_non_https_urls_fail_closed(self):
        for notices in (
            [_notice(), _notice()],
            [_notice(url="http://ted.europa.eu/en/notice/1/html")],
            [_notice(url="https://user:pass@ted.europa.eu/en/notice/1/html")],
            [_notice(url="https://ted.europa.eu/en/notice/1/html#fragment")],
            [_notice(identity="n" + str(i)) for i in range(4)],
        ):
            with self.subTest(case=len(notices)):
                with self.assertRaises(ValueError):
                    proof.verify_notices("ted", notices)

    def test_wrong_source_identity_fails_closed(self):
        with self.assertRaises(ValueError):
            proof.verify_notices("uk_fts", [_notice()])

    def test_dry_run_never_builds_sources(self):
        with patch.object(proof, "source_factories", side_effect=AssertionError("network")):
            output = io.StringIO()
            with redirect_stdout(output):
                result = proof.main([])
        self.assertEqual(result, 0)
        self.assertIn("NOT_RUN", output.getvalue())

    def test_live_is_blocked_outside_isolated_github_pr(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}, clear=True):
            with patch.object(proof, "source_factories",
                              side_effect=AssertionError("live should not run")):
                output = io.StringIO()
                with redirect_stdout(output):
                    result = proof.main(["--live", "--require-all"])
        self.assertEqual(result, 2)
        self.assertIn("BLOCKED_NOT_ISOLATED_GITHUB_PR", output.getvalue())


if __name__ == "__main__":
    unittest.main()
