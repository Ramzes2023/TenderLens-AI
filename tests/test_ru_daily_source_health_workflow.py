"""Enforce an actual daily public-source live health pipeline, not fake green."""
from pathlib import Path
import yaml

YML=Path(".github/workflows/ru-public-sources-daily-live-health.yml")

def load():
    return yaml.load(YML.read_text("utf-8"), Loader=yaml.BaseLoader)

EXPECTED={
    "b2b-center-public-signal": (
        "python -B -m scripts.ci_ru_b2b_real_worker",
        "python -B scripts/ci_ru_b2b_user_scoring.py",
    ),
    "leningrad-oblast-public-signal": (
        "python -B -m scripts.ci_ru_lenobl_real_worker",
        "python -B -m scripts.ci_ru_lenobl_authenticated",
    ),
    "nmck-native-public-signal": (
        "python -B -m scripts.ci_ru_nmck_real_worker",
        "python -B -m scripts.ci_ru_nmck_authenticated",
    ),
    "stan-commercial-public-signal": (
        "python -B -m scripts.ci_ru_stan_real_worker",
        "python -B -m scripts.ci_ru_stan_authenticated",
    ),
    "south-ural-ten-public-signal": (
        "python -B -m scripts.ci_ru_south_ural_10_real_worker",
        "python -B -m scripts.ci_ru_south_ural_authenticated",
    ),
}

def test_schedule_manual_default_and_five_specific_jobs():
    x=load()
    assert "schedule" in x["on"] and len(x["on"]["schedule"])==1
    assert x["on"]["schedule"][0]["cron"]=="17 4 * * *"
    assert "workflow_dispatch" in x["on"]
    assert set(x["jobs"])=={"health-workflow-safety",*EXPECTED}
    assert x["permissions"]=={"contents":"read"}
    assert x["concurrency"]["cancel-in-progress"]=="false"

def test_real_worker_sql_keyword_and_auth_scoring_still_run_on_live_network():
    x=load()
    for name,(worker,scorer) in EXPECTED.items():
        job=x["jobs"][name]
        assert job["runs-on"]=="ubuntu-latest"
        assert job["timeout-minutes"]=="14"
        assert "github.ref == 'refs/heads/main'" in job["if"]
        cmds=[s.get("run") for s in job["steps"] if s.get("run")]
        assert worker in cmds and scorer in cmds
        assert cmds.index(worker)<cmds.index(scorer)
        assert not any("|| true" in s or "continue-on-error" in s for s in cmds)
        assert all(s.get("continue-on-error") is None for s in job["steps"])
        assert all(s.get("uses") in (None,"actions/checkout@v4","actions/setup-python@v5") for s in job["steps"])
        for command in (worker,scorer):
            import shlex
            parts=shlex.split(command)
            assert parts[0:2]==["python","-B"]
            if parts[2]=="-m":
                script=Path(parts[3].replace(".","/")+".py")
            else:
                script=Path(parts[2])
            assert script.exists(),script

def test_no_selfhosted_pr_exec_or_credentials():
    txt=YML.read_text("utf-8").lower()
    assert "self-hosted" not in txt and "pull_request_target" not in txt
    assert "secrets." not in txt and "aws-actions" not in txt
    assert "continue-on-error" not in txt
    assert "persist-credentials: false" in txt
    assert "cancel-in-progress: false" in txt
    for forbidden in ("curl -k","--insecure","trust_env=true","tls_verify=false"):
        assert forbidden not in txt



def test_approved_ten_originals_and_independent_deadline_stay_mandatory():
    x=load()
    job=x["jobs"]["south-ural-ten-public-signal"]
    scripts=[item.get("run") for item in job["steps"] if item.get("run")]
    assert "python -B -m scripts.ci_ru_south_ural_10_real_worker" in scripts
    assert "python -B -m scripts.ci_ru_south_ural_deadline" in scripts
    assert "python -B -m scripts.ci_ru_south_ural_authenticated" in scripts
    assert scripts.index("python -B -m scripts.ci_ru_south_ural_10_real_worker") < scripts.index("python -B -m scripts.ci_ru_south_ural_authenticated")
    assert "continue-on-error" not in job and not any(step.get("continue-on-error") for step in job["steps"])


def test_daily_south_ural_buyer_amount_deadline_real_sql_roundtrip():
    """New metadata gate may neither be skipped nor satisfied with fixtures."""
    y = load()
    steps = y["jobs"]["south-ural-ten-public-signal"]["steps"]
    commands = [step.get("run") for step in steps if step.get("run")]
    originals = "python -B -m scripts.ci_ru_south_ural_10_real_worker"
    metadata = "python -B -m scripts.ci_ru_south_ural_verified_metadata"
    assert originals in commands
    assert metadata in commands
    assert commands.index(originals) < commands.index(metadata)
    assert "python -B -m scripts.ci_ru_south_ural_deadline" in commands
    assert not any(step.get("continue-on-error") for step in steps)
    source = Path("scripts/ci_ru_south_ural_verified_metadata.py").read_text("utf-8")
    for required in ("SouthUralPublicSource(", "OpportunityRepository(db)",
                     "store.upsert(", "store.read(", "notice.customer",
                     "notice.deadline", "notice.initial_price", "TemporaryDirectory"):
        assert required in source, required
    for forbidden in ("MockTransport", "continue-on-error", "skip_live", "sqlite:///:memory:"):
        assert forbidden not in source
