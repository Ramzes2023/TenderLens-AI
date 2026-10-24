"""GitHub read-only gate: real RU runner + authorized Telegram Bot API ACK.

A PR's green offline tests and skipped live job can NEVER satisfy merge-readiness.
Only a completed trusted feature-branch PUSH at the PR's exact head commit with
a successful *self-hosted Linux* live worker can satisfy this status.

The source workflow configures RU_CHECHNYA_REQUIRE_TEST_BOT_ACK=true so the
live worker job cannot pass with LocalCaptureBot or absent test credentials.
This gate does not use GitHub secrets other than the read-only GITHUB_TOKEN.
"""
from __future__ import annotations

import json
import os
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REPOSITORY = "Ramzes2023/TenderLens-AI"
BRANCH = "feat/ru-chechnya-eis-rss-20261022"
WORKFLOW = "RU Chechnya EIS 44 regional source gated acceptance"
WORKFLOW_PATH = ".github/workflows/ru-chechnya-eis-live.yml"
LIVE_JOB = "chechnya-real-live-worker"


def successful_trusted_live_job(head_sha: str, runs: list[dict],
                                jobs_by_id: dict[int, list[dict]]) -> bool:
    """Require exact SHA, repository branch, PUSH event and real runner."""
    if not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        return False
    for run in runs:
        if not isinstance(run, dict):
            continue
        if (run.get("head_sha") != head_sha or run.get("head_branch") != BRANCH
                or run.get("event") != "push" or run.get("name") != WORKFLOW
                or run.get("status") != "completed"
                or run.get("conclusion") != "success"
                or str(run.get("path") or "").split("@", 1)[0] != WORKFLOW_PATH):
            continue
        run_id = run.get("id")
        if type(run_id) is not int:
            continue
        for job in jobs_by_id.get(run_id, []):
            if not isinstance(job, dict):
                continue
            labels = {str(label).casefold() for label in (job.get("labels") or [])}
            if (job.get("name") == LIVE_JOB and job.get("status") == "completed"
                    and job.get("conclusion") == "success"
                    and type(job.get("runner_id")) is int
                    and job["runner_id"] > 0
                    and job.get("runner_name") == "VALYQON-RU-01"
                    and {"self-hosted", "linux", "x64"}.issubset(labels)):
                return True
    return False


def _fetch_json(endpoint: str, token: str) -> dict:
    if not endpoint.startswith("https://api.github.com/repos/" + REPOSITORY + "/actions/"):
        raise ValueError("Unapproved GitHub Actions API endpoint")
    request = Request(
        endpoint,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "VALYQON-Chechnya-release-proof/1.0",
        },
    )
    # Repository Actions API only; never output tokens, response URLs or
    # API errors that might expose request credentials.
    with urlopen(request, timeout=15) as response:
        payload = response.read(3 * 1024 * 1024 + 1)
    if len(payload) > 3 * 1024 * 1024:
        raise ValueError("Oversize GitHub API response")
    doc = json.loads(payload)
    if not isinstance(doc, dict):
        raise ValueError("Unexpected GitHub API result")
    return doc


def main() -> int:
    sha = os.environ.get("VALYQON_PR_HEAD_SHA", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    if (repo != REPOSITORY or not re.fullmatch(r"[0-9a-f]{40}", sha) or not token):
        print("RU_CHECHNYA_RELEASE_PROOF=BLOCKED_INVALID_CONTEXT")
        return 2
    try:
        params = urlencode({"branch": BRANCH, "event": "push", "per_page": 100})
        url = f"https://api.github.com/repos/{REPOSITORY}/actions/runs?{params}"
        doc = _fetch_json(url, token)
        runs = doc.get("workflow_runs", [])
        if not isinstance(runs, list):
            raise ValueError("Unexpected workflow runs")
        matches = [x for x in runs
                   if isinstance(x, dict)
                   and x.get("head_sha") == sha
                   and x.get("event") == "push"
                   and x.get("name") == WORKFLOW
                   and x.get("status") == "completed"
                   and x.get("conclusion") == "success"]
        jobs_by_id = {}
        for run in matches:
            run_id = run.get("id")
            if type(run_id) is not int:
                continue
            job_doc = _fetch_json(
                f"https://api.github.com/repos/{REPOSITORY}/actions/runs/{run_id}/jobs?per_page=100",
                token,
            )
            jobs = job_doc.get("jobs", [])
            if not isinstance(jobs, list):
                raise ValueError("Unexpected workflow jobs")
            jobs_by_id[run_id] = jobs
        accepted = successful_trusted_live_job(sha, matches, jobs_by_id)
    except Exception as error:
        # Preserve neither token nor HTTP URLs in logs.
        print("RU_CHECHNYA_RELEASE_PROOF=BLOCKED_GITHUB_READ_" + type(error).__name__)
        return 2
    if not accepted:
        print("RU_CHECHNYA_RELEASE_PROOF=BLOCKED_NO_MATCHING_TRUSTED_LIVE_RUN")
        print("RU_CHECHNYA_REAL_TELEGRAM_ACK=NOT_VERIFIED")
        return 2
    print("RU_CHECHNYA_RELEASE_PROOF=VERIFIED_TRUSTED_RUN_AT_EXACT_PR_SHA")
    print("RU_CHECHNYA_REAL_TELEGRAM_ACK=REQUIRED_BY_SUCCESSFUL_LIVE_JOB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
