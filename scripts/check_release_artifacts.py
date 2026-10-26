"""Fail-closed check that release evidence and database backups never enter Git.

Checks filenames only, does not open, read, encrypt, copy or delete any files.
Intended to run in CI and before staging commits. Does NOT certify backups.
"""
from __future__ import annotations

from pathlib import PurePosixPath
import subprocess
import sys


BACKUP_SUFFIXES = (
    ".dump", ".pgdump", ".backup", ".sqlite", ".sqlite3", ".db",
    ".sql.gz", ".db.gz", ".sqlite.gz",
    ".tar.age", ".tar.gpg", ".backup.age", ".backup.gpg",
)


def disallowed_tracked_path(path: str) -> bool:
    """True if path could be a release evidence directory or DB/backup artifact."""
    path = path.replace("\\", "/").lstrip("./")
    if not path or "\x00" in path:
        return True
    segments = path.split("/")
    if any(segment == ".release" for segment in segments):
        return True
    name = PurePosixPath(path).name.lower()
    return name.endswith(BACKUP_SUFFIXES)


def audit_file_paths(paths: list[str]) -> int:
    candidates = [name for name in paths if disallowed_tracked_path(name)]
    if candidates:
        # Do not print backup names; they may themselves disclose private IDs.
        print(f"RELEASE_EVIDENCE_GIT_GUARD=FAIL; blocked_file_count={len(candidates)}")
        return 1
    print("RELEASE_EVIDENCE_GIT_GUARD=PASS")
    return 0


def main() -> int:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "-z"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=True, timeout=15,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print("RELEASE_EVIDENCE_GIT_GUARD=BLOCKED; cannot inspect git index")
        return 2
    paths = [item.decode("utf-8", errors="surrogateescape")
             for item in result.stdout.split(b"\x00") if item]
    return audit_file_paths(paths)


if __name__ == "__main__":
    sys.exit(main())
