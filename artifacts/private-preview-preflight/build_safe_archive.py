"""Build a minimal, source-only private-preview archive (no account data).

Never follows symlinks. Copies only runtime source and a public example profile;
all local data, credentials, generated reports and private directories stay out.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tarfile
import tempfile

MAX_FILE = 24 * 1024 * 1024
MAX_TOTAL = 120 * 1024 * 1024
MAX_COUNT = 5000
EXTENSIONS = {
    '.py', '.pyi', '.txt', '.json', '.geojson', '.sql', '.html', '.css',
    '.js', '.mjs', '.cjs', '.yaml', '.yml', '.xml', '.svg', '.png',
    '.jpg', '.jpeg', '.webp', '.ico', '.gif', '.map', '.ps1',
    '.dockerignore', '.md',
}
PRIVATE_COMPONENTS = {
    'data', 'uploads', 'logs', 'secrets', 'private', 'customer_data',
    '__pycache__', '.git', '.cache', 'node_modules', '.venv',
    '.pytest_cache', 'artifacts', 'screenshots', 'traces',
}
BLOCKED_ENDINGS = {
    '.env', '.key', '.pem', '.p12', '.pfx', '.db', '.sqlite',
    '.sqlite3', '.csv', '.log', '.zip', '.tar', '.gz', '.bak',
}


def permitted(relative: Path) -> bool:
    parts = relative.parts
    if not parts or any(component.casefold() in PRIVATE_COMPONENTS for component in parts):
        return False
    name = parts[-1]
    folded = name.casefold()
    if any(component.startswith('.') for component in parts if component not in ('.dockerignore',)):
        return False
    if folded.startswith('.env') or folded in {'token.json', 'accounts.json', 'credentials.json', 'passwords.json'}:
        return False
    if Path(folded).suffix in BLOCKED_ENDINGS or folded.endswith(('.db-wal', '.db-shm')):
        return False
    if parts[0] == 'config':
        return relative.as_posix() == 'config/company_profile.example.json'
    if parts[0] == 'ops':
        if len(parts) < 3 or parts[1] != 'private_preview':
            return False
    elif parts[0] != 'app':
        return False
    return (Path(folded).suffix in EXTENSIONS
            or folded.startswith('dockerfile.preview'))


def build(source: Path, destination: Path) -> int:
    source = source.resolve(strict=True)
    destination = destination.absolute()
    if destination.is_relative_to(source):
        raise ValueError('Archive must be outside source tree')
    for required in ('app/api/static', 'ops/private_preview', 'config/company_profile.example.json'):
        if not (source / required).exists():
            raise ValueError('Required source missing')
    files = []
    total = 0
    for relative_root in ('app', 'ops/private_preview', 'config'):
        directory = source / relative_root
        for entry in directory.rglob('*'):
            if entry.is_symlink():
                raise ValueError('Symlink forbidden in preview source')
            if not entry.is_file():
                continue
            rel = entry.relative_to(source)
            if not permitted(rel):
                continue
            if not entry.resolve().is_relative_to(source):
                raise ValueError('Path escaped source root')
            size = entry.stat().st_size
            if size > MAX_FILE:
                raise ValueError('Source file exceeds size limit')
            total += size
            files.append((rel.as_posix(), entry, size))
            if total > MAX_TOTAL or len(files) > MAX_COUNT:
                raise ValueError('Source archive size/count limit exceeded')
    files.sort()
    if not any(name.startswith('app/api/static/') for name, _, _ in files):
        raise ValueError('No static assets found')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.preview-', suffix='.tar.gz.tmp', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            with tarfile.open(fileobj=output, mode='w:gz') as archive:
                for name, entry, size in files:
                    metadata = tarfile.TarInfo(name)
                    metadata.size = size
                    metadata.mode = 0o644
                    metadata.uid = metadata.gid = 0
                    metadata.mtime = 0
                    with entry.open('rb') as contents:
                        archive.addfile(metadata, contents)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return len(files)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: build_safe_archive.py SOURCE_DIRECTORY OUTPUT_TAR_GZ')
    try:
        count = build(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError, tarfile.TarError):
        print('Archive creation blocked by source validation', file=sys.stderr)
        raise SystemExit(2) from None
    print('SOURCE_ONLY_ARCHIVE=VERIFIED; FILE_COUNT=' + str(count))
