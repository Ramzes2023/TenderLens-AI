"""Isolated, no-network trust checks for post-live proof refresher."""
import unittest

from scripts.ru_chechnya_completed_live_refresh import (
    BRANCH, PROOF_NAME, PROOF_PATH, REPO, SOURCE_NAME, SOURCE_PATH,
    trusted_completed_run, confirmed_ru01_live_job, pr_is_exact_head,
    failed_proof_check_id,
)

SHA = "a" * 40


def event(**overrides):
    run = {
        "id": 199,
        "head_sha": SHA,
        "head_repository": {"full_name": REPO},
        "head_branch": BRANCH,
        "name": SOURCE_NAME,
        "path": SOURCE_PATH + "@refs/heads/" + BRANCH,
        "event": "push",
        "status": "completed",
        "conclusion": "success",
    }
    run.update(overrides)
    return {"action": "completed", "workflow_run": run}


def job(**overrides):
    j = {
        "name": "chechnya-real-live-worker",
        "status": "completed",
        "conclusion": "success",
        "runner_name": "VALYQON-RU-01",
        "runner_id": 42,
        "labels": ["self-hosted", "Linux", "X64"],
    }
    j.update(overrides)
    return j


def pr(**overrides):
    p = {
        "number": 236,
        "state": "open",
        "merged_at": None,
        "head": {"sha": SHA, "ref": BRANCH, "repo": {"full_name": REPO}},
        "base": {"ref": "main"},
    }
    p.update(overrides)
    return p


def proof(**overrides):
    r = {
        "id": 456,
        "head_sha": SHA,
        "head_branch": BRANCH,
        "event": "pull_request",
        "name": PROOF_NAME,
        "path": PROOF_PATH + "@refs/heads/main",
        "status": "completed",
        "conclusion": "failure",
    }
    r.update(overrides)
    return r


class TrustedRUCallbackTests(unittest.TestCase):
    def test_requires_completed_first_party_push_exact_branch_and_sha(self):
        self.assertEqual(trusted_completed_run(event()), (199, SHA))
        for delta in [
            {"head_sha": "b" * 40},  # Should be *a different* sha, but valid.
            {"head_sha": "not-a-sha"},
            {"head_branch": "main"},
            {"name": "CI"},
            {"path": ".github/workflows/another.yml@refs/heads/" + BRANCH},
            {"event": "pull_request"},
            {"conclusion": "failure"},
            {"conclusion": "cancelled"},
            {"status": "in_progress"},
            {"head_repository": {"full_name": "other/repo"}},
            {"id": 0},
            {"id": True},
        ]:
            if delta == {"head_sha": "b" * 40}:
                # Any 40-character SHA may be valid; *PR head* is checked
                # separately before a re-run is sent.
                self.assertEqual(trusted_completed_run(event(**delta)), (199, "b" * 40))
            else:
                self.assertIsNone(trusted_completed_run(event(**delta)))

    def test_only_named_ru_runner_is_acceptable(self):
        self.assertTrue(confirmed_ru01_live_job([job()]))
        for delta in [
            {"name": "chechnya-hosted-windows-live-signal"},
            {"status": "queued"},
            {"conclusion": "skipped"},
            {"conclusion": "failure"},
            {"runner_name": "VALYQON-INT-02"},
            {"runner_name": "VALYQON-ASIA-03"},
            {"labels": ["ubuntu-latest"]},
            {"labels": ["self-hosted", "Linux"]},
            {"labels": ["self-hosted", "Windows", "X64"]},
            {"runner_id": 0},
            {"runner_id": True},
        ]:
            self.assertFalse(confirmed_ru01_live_job([job(**delta)]))

    def test_only_same_open_unmerged_pr_head(self):
        self.assertTrue(pr_is_exact_head(pr(), SHA))
        self.assertFalse(pr_is_exact_head(pr(), "b" * 40))
        for delta in [
            {"number": 237},
            {"state": "closed"},
            {"merged_at": "2026-10-23T12:00:00Z"},
            {"head": {"sha": SHA, "ref": "main", "repo": {"full_name": REPO}}},
            {"head": {"sha": SHA, "ref": BRANCH, "repo": {"full_name": "foreign/repo"}}},
            {"base": {"ref": "other"}},
        ]:
            self.assertFalse(pr_is_exact_head(pr(**delta), SHA))

    def test_only_failed_exact_branch_sha_release_proof_is_rerun(self):
        self.assertEqual(failed_proof_check_id([proof()], SHA), 456)
        self.assertEqual(failed_proof_check_id([proof(id=456), proof(id=999)], SHA), 999)
        for delta in [
            {"head_sha": "b" * 40}, {"head_branch": "main"},
            {"event": "push"}, {"name": "Other release gate"},
            {"path": ".github/workflows/ci.yml@refs/heads/main"},
            {"status": "in_progress"}, {"conclusion": "success"},
            {"conclusion": "cancelled"}, {"id": True},
        ]:
            self.assertIsNone(failed_proof_check_id([proof(**delta)], SHA))
        self.assertIsNone(failed_proof_check_id([], SHA))


if __name__ == "__main__":
    unittest.main()
