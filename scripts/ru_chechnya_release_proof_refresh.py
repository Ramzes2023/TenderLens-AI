"""Re-run only Chechnya's PR release-proof check after REAL RU-01 live success.

Triggered exclusively by a trusted feature-branch push workflow job that
depends on successful, ACK-gated chechnya-real-live-worker. This fixes the
stale-red-PR-check gap: the PR gate may initially fail while the RU-01 job
was queued, but must re-evaluate once that exact commit passes live.

No Telegram secret, RSS data, user recipient or other workflow is handled.
"""
from __future__ import annotations

import json
import os
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REPOSITORY = "Ramzes2023/TenderLens-AI"
BRANCH = "feat/ru-chechnya-eis-rss-20261022"
CHECK_WORKFLOW = "RU Chechnya real EIS Worker Telegram release proof"
CHECK_PATH = ".github/workflows/ru-chechnya-release-gate.yml"
API_ROOT = "https://api.github.com/repos/" + REPOSITORY


def eligible_release_proof_runs(head_sha: str, runs: list[dict]) -> list[int]:
    """Choose only failed PR proof runs, never another source or a new SHA."""
    if not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        return []
    selected = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        if (run.get("head_sha") != head_sha
                or run.get("head_branch") != BRANCH
                or run.get("event") != "pull_request"
                or run.get("name") != CHECK_WORKFLOW
                or str(run.get("path") or "").split("@", 1)[0] != CHECK_PATH
                or run.get("status") != "completed"
                or run.get("conclusion") != "failure"
                or type(run.get("id")) is not int):
            continue
        selected.append(run["id"])
    return sorted(set(selected), reverse=True)


def _github_call(path: str, token: str, *, method: str = "GET") -> dict:
    if not (path.startswith("/actions/") and not any(c in path for c in "\r\n")):
        raise ValueError("Unapproved Actions path")
    req = Request(
        API_ROOT + path,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "VALYQON-RU-Chechnya-proof-refresh/1.0",
        },
        method=method,
    )
    with urlopen(req, timeout=15) as response:
        result = response.read(2 * 1024 * 1024 + 1)
    if len(result) > 2 * 1024 * 1024:
        raise ValueError("Oversized GitHub response")
    if method == "POST":
        return {}
    output = json.loads(result)
    if not isinstance(output, dict):
        raise ValueError("Unexpected GitHub response")
    return output


def main() -> int:
    sha = os.environ.get("GITHUB_SHA", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    ref = os.environ.get("GITHUB_REF", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    if (repo != REPOSITORY or ref != "refs/heads/" + BRANCH
            or not re.fullmatch(r"[0-9a-f]{40}", sha) or not token):
        print("RU_CHECHNYA_PROOF_REFRESH=BLOCKED_UNTRUSTED_CONTEXT")
        return 2
    try:
        args = urlencode({"event": "pull_request", "head_sha": sha, "per_page": 100})
        collection = _github_call(
            "/actions/workflows/ru-chechnya-release-gate.yml/runs?" + args,
            token,
        )
        eligible = eligible_release_proof_runs(sha, collection.get("workflow_runs", []))
        # Re-run only the MOST RECENT failed check from the same immutable head.
        # If the check has not failed yet, there is nothing to re-run.
        if not eligible:
            print("RU_CHECHNYA_PROOF_REFRESH=NO_FAILED_MATCHING_PR_CHECK")
            return 0
        _github_call(f"/actions/runs/{eligible[0]}/rerun", token, method="POST")
    except Exception as error:
        print("RU_CHECHNYA_PROOF_REFRESH=GITHUB_ACTIONS_ERROR_" + type(error).__name__)
        return 2
    print("RU_CHECHNYA_PROOF_REFRESH=REQUESTED_FOR_EXACT_HEAD_ONLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
