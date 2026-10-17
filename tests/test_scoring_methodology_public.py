"""Public scoring guidance must track the actual weighted engine and avoid unjustified win claims."""
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.scoring_methodology import methodology_html
from app.scoring.engine import WEIGHTS


def test_public_scoring_guide_tracks_engine_weights():
    page = methodology_html()
    assert sum(WEIGHTS.values()) == 100
    for weight in WEIGHTS.values():
        assert f"{weight}%" in page
    assert "not a probability of winning" not in page.lower() or "not" in page.lower()
    assert "compatibility" in page
    assert "completeness" in page
    assert "Not scored" in page
    assert "RNP" in page


def test_scoring_guide_is_public_safe_and_linked_from_help():
    with TestClient(create_app(runtime=ApiRuntime())) as client:
        result = client.get("/scoring-methodology")
        assert result.status_code == 200
        assert result.headers["x-frame-options"] == "DENY"
        assert result.headers["cache-control"] == "no-store"
        assert "How matching and scoring works" in result.text
        help = client.get("/how-it-works")
        assert help.status_code == 200
        assert "/scoring-methodology" in help.text
