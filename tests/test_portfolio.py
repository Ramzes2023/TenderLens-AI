from pathlib import Path

from app import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_portfolio_v1():
    assert __version__ == "1.2.0"


def test_portfolio_documents_exist_and_are_linked():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for relative in ("SECURITY.md", "docs/DEMO.md", "docs/DEPLOYMENT.md", "docs/PORTFOLIO.md", "docs/MULTI_COMPANY.md"):
        assert (ROOT / relative).is_file()
        assert relative in readme


def test_readme_states_safety_boundary():
    text = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "not" in text and "autonomously" in text
    assert "probability of winning" in text


def test_ci_runs_tests_and_docker_build():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "python -m pytest -q" in workflow
    assert "python -m compileall" in workflow
    assert "docker build -t tenderlens-ai:ci ." in workflow


def test_smoke_script_checks_core_openapi_paths():
    text = (ROOT / "scripts" / "smoke_api.py").read_text(encoding="utf-8")
    assert '"/api/v1/companies"' in text
    assert '"/api/v1/scoring/evaluate"' in text
    assert '"/api/v1/rag/ask"' in text
    assert '"/api/v1/monitoring/status"' in text
