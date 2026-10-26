"""Release safety: never track production-derived evidence/backup material."""
from scripts.check_release_artifacts import (
    audit_file_paths, disallowed_tracked_path,
)


def test_production_evidence_and_backups_are_never_git_assets(capsys):
    unsafe=[
        ".release/evidence/LAUNCH_REPORT_RU.md",
        ".release/evidence/staging-postgres.dump",
        "./.release/evidence/staging-restore.json",
        "private/staging.pgDUMP",
        "private/account-data.backup",
        "private/prod.sqlite",
        "private/prod.db",
        "private/prod.sql.gz",
        "private/data.tar.age",
        r"private\\.release\\evidence\\db.dump",
    ]
    assert all(disallowed_tracked_path(path) for path in unsafe)
    assert audit_file_paths(unsafe)==1
    assert "blocked_file_count=10" in capsys.readouterr().out


def test_regular_code_and_documentation_remain_allowed(capsys):
    clean=[
        ".gitignore",
        "docs/PUBLIC_LAUNCH_READINESS_20261025.md",
        "scripts/verify_public_https.py",
        "app/database/backend.py",
        "app/database/schema/tender_workflows.sql",
        ".env.example",
        "docs/DEPLOYMENT.md",
    ]
    assert not any(disallowed_tracked_path(path) for path in clean)
    assert audit_file_paths(clean)==0
    assert "RELEASE_EVIDENCE_GIT_GUARD=PASS" in capsys.readouterr().out


def test_git_file_index_is_clean_of_prod_backups():
    from scripts.check_release_artifacts import main
    assert main()==0
