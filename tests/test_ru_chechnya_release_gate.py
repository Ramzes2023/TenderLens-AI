"""Synthetic contract tests only; never assert actual EIS/Telegram delivery."""
from scripts.ru_chechnya_release_gate import (
    BRANCH, LIVE_JOB, WORKFLOW, WORKFLOW_PATH, successful_trusted_live_job,
)

SHA = "a" * 40

def _run(**overrides):
    item = {
        "id": 1234,
        "head_sha": SHA,
        "head_branch": BRANCH,
        "event": "push",
        "name": WORKFLOW,
        "path": WORKFLOW_PATH + "@refs/heads/" + BRANCH,
        "status": "completed",
        "conclusion": "success",
    }
    item.update(overrides)
    return item


def _job(**overrides):
    item = {
        "name": LIVE_JOB,
        "status": "completed",
        "conclusion": "success",
        "runner_id": 84,
        "runner_name": "VALYQON-RU-01",
        "labels": ["self-hosted", "Linux", "X64"],
    }
    item.update(overrides)
    return item


def test_trusted_linux_runner_success_on_same_exact_sha_required():
    assert successful_trusted_live_job(SHA, [_run()], {1234: [_job()]})
    assert not successful_trusted_live_job("invalid", [_run()], {1234: [_job()]})
    assert not successful_trusted_live_job("b" * 40, [_run()], {1234: [_job()]})
    assert not successful_trusted_live_job(SHA, [_run()], {})
    assert not successful_trusted_live_job(SHA, [_run(id=True)], {True: [_job()]})


def test_skipped_live_job_and_hosted_canaries_cannot_satisfy_merge_gate():
    for status, conclusion in [
        ("completed", "skipped"),
        ("queued", None),
        ("in_progress", None),
        ("completed", "failure"),
        ("completed", "cancelled"),
    ]:
        assert not successful_trusted_live_job(
            SHA, [_run()], {1234: [_job(status=status, conclusion=conclusion)]},
        )
    assert not successful_trusted_live_job(
        SHA, [_run()], {1234: [_job(name="chechnya-hosted-windows-live-signal")]},
    )


def test_gh_hosted_runner_and_unassigned_linux_are_rejected():
    for fields in [
        {"labels": ["windows-latest"]},
        {"labels": ["ubuntu-latest"]},
        {"labels": ["self-hosted", "Windows"]},
        {"labels": ["Linux"]},
        {"runner_id": 0},
        {"runner_id": None},
        {"runner_name": ""},
        {"runner_name": None},
        {"runner_id": True},
    ]:
        assert not successful_trusted_live_job(SHA, [_run()], {1234: [_job(**fields)]})


def test_wrong_branch_event_workflow_path_status_or_sha_rejected():
    for fields in [
        {"head_sha": "b" * 40},
        {"head_branch": "main"},
        {"event": "pull_request"},
        {"name": "CI"},
        {"path": ".github/workflows/other.yml@refs/heads/" + BRANCH},
        {"status": "queued"},
        {"conclusion": "failure"},
        {"conclusion": "cancelled"},
    ]:
        assert not successful_trusted_live_job(
            SHA, [_run(**fields)], {1234: [_job()]},
        )
