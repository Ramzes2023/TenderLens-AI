"""Deterministic public-only release bundle. NEVER an automatic deployment.

Contains four explicitly enumerated, reviewed marketing files and a manifest.
No application Python code, .env, customer data, SSH key, DB or backup can be
traversed into the archive. A candidate bundle is not operator authorization.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import gzip
import json
from pathlib import Path
import tarfile

ALLOWED = (
    "ops/public_landing/site/index.html",
    "ops/public_landing/site/valyqon-public-landing.css",
    "ops/public_landing/Caddyfile",
    "ops/public_landing/compose.static.yaml",
)
MAX_SIZE = 200_000


def build(root: Path, destination: Path):
    root = Path(root).resolve(strict=True)
    destination = Path(destination).resolve()
    approved = {}
    for relative in ALLOWED:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing or symlinked release asset")
        data = path.read_bytes()
        if not data or len(data) > MAX_SIZE:
            raise ValueError("Invalid public asset size")
        approved[relative] = data
    assert len(approved) == len(ALLOWED)
    manifest = {
        "schema": 1,
        "release_track": "public_static_homepage_only",
        "production_deployment_authorized": False,
        "application_api_upgrade": False,
        "database_migration": False,
        "included_assets": {
            name: {"sha256": sha256(approved[name]).hexdigest(), "bytes": len(approved[name])}
            for name in ALLOWED
        },
    }
    approved["public_landing_manifest.json"] = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    raw = BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        for relative, payload in approved.items():
            entry = tarfile.TarInfo(relative)
            entry.size = len(payload)
            entry.mode = 0o644
            entry.mtime = 0
            entry.uid = 0
            entry.gid = 0
            entry.uname = ""
            entry.gname = ""
            archive.addfile(entry, BytesIO(payload))
    with destination.open("wb") as fp:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fp, mtime=0,
                           compresslevel=9) as compressed:
            compressed.write(raw.getvalue())
    return sha256(destination.read_bytes()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        root = Path(__file__).resolve().parents[1]
        artifact_sha = build(root, args.output)
    except (OSError, ValueError, tarfile.TarError):
        print("PUBLIC_STATIC_BUNDLE=BLOCKED")
        return 2
    print("PUBLIC_STATIC_BUNDLE=BUILT_NOT_DEPLOYED")
    print("PUBLIC_STATIC_BUNDLE_SHA256=" + artifact_sha)
    print("PUBLIC_STATIC_ONLY_FILES=4")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
