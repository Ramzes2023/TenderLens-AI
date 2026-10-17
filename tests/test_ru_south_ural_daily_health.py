"""Verify scheduled South Ural source monitor remains genuine and fail closed."""
from pathlib import Path
import yaml

FILE=Path(".github/workflows/ru-south-ural-research.yml")

def test_daily_official_real_notices_remain_required():
    d=yaml.load(FILE.read_text(encoding="utf-8"),Loader=yaml.BaseLoader)
    assert d["on"]["schedule"]==[{"cron":"07 5 * * *"}]
    assert "workflow_dispatch" in d["on"]
    jobs=d["jobs"]
    assert {"south-ural-adversarial-offline","south-ural-two-live-independent-details"}==set(jobs)
    assert d["permissions"]=={"contents":"read"}
    steps=jobs["south-ural-two-live-independent-details"]["steps"]
    assert any(s.get("run")=="python -B -m scripts.research_ru_south_ural_public" for s in steps)
    assert jobs["south-ural-two-live-independent-details"]["runs-on"]=="ubuntu-latest"
    assert all(s.get("continue-on-error") is None for s in steps)
    assert all(s.get("persist-credentials") is None for s in steps)
    assert all(x.get("with",{}).get("persist-credentials")=="false" for x in steps if x.get("uses")=="actions/checkout@v4")

def test_daily_source_not_mocked_or_secret_activated():
    source=Path("scripts/research_ru_south_ural_public.py").read_text(encoding="utf-8")
    assert "verified.append(verify_public_detail(" in source
    assert "PRODUCTION_CHANGED=NO" in source
    assert "bounded_fetch(FetchPolicy(" in source
    txt=FILE.read_text(encoding="utf-8").lower()
    for bad in ("continue-on-error", "pull_request_target", "self-hosted", "secrets.", "curl -k", "--insecure"):
        assert bad not in txt
