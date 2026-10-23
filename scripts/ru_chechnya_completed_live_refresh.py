"""Reevaluate Chechnya's PR release gate AFTER trusted live workflow completes.

Runs from a default-branch workflow_run listener, NOT from the feature branch.
Never treats hosted diagnostics, offline checks, a stale SHA or a different
self-hosted runner as integration evidence. No Telegram secrets are read.
"""
from __future__ import annotations

import json
import os
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REPO = "Ramzes2023/TenderLens-AI"
BRANCH = "feat/ru-chechnya-eis-rss-20261022"
SOURCE_NAME = "RU Chechnya EIS 44 regional source gated acceptance"
SOURCE_PATH = ".github/workflows/ru-chechnya-eis-live.yml"
PROOF_NAME = "RU Chechnya real EIS Worker Telegram release proof"
PROOF_PATH = ".github/workflows/ru-chechnya-release-gate.yml"
PR_NUMBER = 236
API_ROOT = f"https://api.github.com/repos/{REPO}"
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")


def trusted_completed_run(event: dict) -> tuple[int, str] | None:
    """Only completed, successful first-party feature PUSH at exact workflow."""
    run = event.get("workflow_run") if isinstance(event, dict) else None
    if not isinstance(run, dict) or event.get("action") != "completed":
        return None
    repository = run.get("head_repository") or {}
    number = run.get("id")
    head = run.get("head_sha")
    if (repository.get("full_name") != REPO
            or run.get("head_branch") != BRANCH
            or run.get("event") != "push"
            or run.get("name") != SOURCE_NAME
            or str(run.get("path") or "").split("@", 1)[0] != SOURCE_PATH
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
            or type(number) is not int or number <= 0
            or not isinstance(head, str) or not SHA_RE.fullmatch(head)):
        return None
    return (number, head)


def confirmed_ru01_live_job(jobs: list[dict]) -> bool:
    """A real assigned named Linux RU runner must have completed live job."""
    for job in jobs:
        if not isinstance(job, dict):
            continue
        labels = {str(x).casefold() for x in (job.get("labels") or [])}
        if (job.get("name") == "chechnya-real-live-worker"
                and job.get("status") == "completed"
                and job.get("conclusion") == "success"
                and job.get("runner_name") == "VALYQON-RU-01"
                and type(job.get("runner_id")) is int and job["runner_id"] > 0
                and {"self-hosted", "linux", "x64"}.issubset(labels)):
            return True
    return False


def pr_is_exact_head(pr: dict, sha: str) -> bool:
    """Never touch another PR, already-merged PR or future commit."""
    if not isinstance(pr, dict):
        return False
    head, base = pr.get("head") or {}, pr.get("base") or {}
    return bool(
        pr.get("number") == PR_NUMBER
        and pr.get("state") == "open" and not pr.get("merged_at")
        and head.get("sha") == sha and head.get("ref") == BRANCH
        and (head.get("repo") or {}).get("full_name") == REPO
        and base.get("ref") == "main"
    )


def failed_proof_check_id(runs: list[dict], sha: str) -> int | None:
    """Re-run ONLY the last failed exact-SHA PR release proof, never canaries."""
    matches = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        number = run.get("id")
        if (run.get("head_sha") == sha
                and run.get("head_branch") == BRANCH
                and run.get("event") == "pull_request"
                and run.get("name") == PROOF_NAME
                and str(run.get("path") or "").split("@", 1)[0] == PROOF_PATH
                and run.get("status") == "completed"
                and run.get("conclusion") == "failure"
                and type(number) is int and number > 0):
            matches.append(number)
    return max(matches) if matches else None


def api(path: str, token: str, *, post: bool = False) -> dict:
    """Restrict all requests to named GitHub API routes; redact any failures."""
    allowed = (
        re.fullmatch(r"/actions/runs/[0-9]+/jobs\?per_page=100", path)
        or path == f"/pulls/{PR_NUMBER}"
        or path.startswith("/actions/workflows/ru-chechnya-release-gate.yml/runs?")
        or (post and re.fullmatch(r"/actions/runs/[0-9]+/rerun", path))
    )
    if not allowed or any(x in path for x in ("\r", "\n")):
        raise ValueError("Not a permitted GitHub API path")
    req = Request(
        API_ROOT + path,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "VALYQON-Chechnya-live-proof-refresh/1.0",
        },
        data=b"" if post else None,
        method="POST" if post else "GET",
    )
    with urlopen(req, timeout=18) as response:
        payload = response.read(2 * 1024 * 1024 + 1)
    if len(payload) > 2 * 1024 * 1024:
        raise ValueError("GitHub API response too large")
    if post:
        return {}
    result = json.loads(payload)
    if not isinstance(result, dict):
        raise ValueError("GitHub API unexpected response")
    return result


def main() -> int:
    if (os.environ.get("GITHUB_REPOSITORY") != REPO
            or os.environ.get("GITHUB_EVENT_NAME") != "workflow_run"
            or not os.environ.get("GITHUB_TOKEN")):
        print("RU_CHECHNYA_PROOF_REFRESH=UNTRUSTED_CONTEXT_BLOCKED")
        return 2
    try:
        with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as file:
            event = json.load(file)
        selected = trusted_completed_run(event)
        if selected is None:
            print("RU_CHECHNYA_PROOF_REFRESH=IGNORED_UNRELATED_RUN")
            return 0
        run_id, sha = selected
        token = os.environ["GITHUB_TOKEN"]
        jobs = api(f"/actions/runs/{run_id}/jobs?per_page=100", token).get("jobs", [])
        if not isinstance(jobs, list) or not confirmed_ru01_live_job(jobs):
            print("RU_CHECHNYA_PROOF_REFRESH=BLOCKED_NO_VERIFIED_RU01_JOB")
            return 2
        pr = api(f"/pulls/{PR_NUMBER}", token)
        if not pr_is_exact_head(pr, sha):
            print("RU_CHECHNYA_PROOF_REFRESH=IGNORED_PR_HEAD_MOVED")
            return 0
        query = urlencode({"event": "pull_request", "head_sha": sha, "per_page": 100})
        runs = api(
            "/actions/workflows/ru-chechnya-release-gate.yml/runs?" + query,
            token,
        ).get("workflow_runs", [])
        if not isinstance(runs, list):
            raise ValueError("Unexpected release-proof runs")
        target = failed_proof_check_id(runs, sha)
        if target is None:
            print("RU_CHECHNYA_PROOF_REFRESH=NO_MATCHING_FAILED_PROOF")
            return 0
        api(f"/actions/runs/{target}/rerun", token, post=True)
    except Exception as error:
        # Never log token, URL query, exception message or private environment.
        print("RU_CHECHNYA_PROOF_REFRESH=GITHUB_API_" + type(error).__name__)
        return 2
    print("RU_CHECHNYA_PROOF_REFRESH=RERUN_REQUESTED_SAME_SHA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
