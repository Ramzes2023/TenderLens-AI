"""Read-only, fail-closed evidence binding a local CI Docker image to its Git checkout.

This validates a local build *claim*, not an independently signed attestation
or the deployed public VPS image. Never calls SSH, Compose, AWS or a registry;
never reads Docker secrets or production volumes. Output is an allowlisted
JSON manifest and deliberately excludes raw docker inspect payload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

EXPECTED_IMAGE = "tenderlens-ai:provenance-audit"
EXPECTED_SOURCE = "https://github.com/Ramzes2023/TenderLens-AI"
SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")


class EvidenceError(ValueError):
    """A required local image→source binding is missing or contradictory."""


def evidence(
    inspect: dict[str, Any],
    *,
    expected_sha: str,
    checkout_sha: str,
    tree_sha: str,
    dockerfile_sha256: str,
) -> dict[str, object]:
    if not all(isinstance(v, str) and GIT_SHA.fullmatch(v)
               for v in (expected_sha, checkout_sha, tree_sha)):
        raise EvidenceError("INVALID_GIT_IDENTITY")
    if expected_sha != checkout_sha:
        raise EvidenceError("CHECKOUT_SHA_MISMATCH")
    if not isinstance(dockerfile_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", dockerfile_sha256
    ):
        raise EvidenceError("INVALID_DOCKERFILE_SHA256")
    if not isinstance(inspect, dict) or not SHA256.fullmatch(
        str(inspect.get("Id", ""))
    ):
        raise EvidenceError("MISSING_IMAGE_ID")
    labels = inspect.get("Config", {}).get("Labels")
    if not isinstance(labels, dict):
        raise EvidenceError("MISSING_OCI_LABELS")
    if labels.get("org.opencontainers.image.revision") != expected_sha:
        raise EvidenceError("IMAGE_REVISION_MISMATCH")
    if labels.get("org.opencontainers.image.source") != EXPECTED_SOURCE:
        raise EvidenceError("IMAGE_SOURCE_MISMATCH")
    if labels.get("com.valyqon.build.kind") != "isolated-ci-audit-only":
        raise EvidenceError("NOT_AN_ISOLATED_AUDIT_IMAGE")
    tags = inspect.get("RepoTags")
    if not isinstance(tags, list) or EXPECTED_IMAGE not in tags:
        raise EvidenceError("LOCAL_AUDIT_TAG_MISSING")
    return {
        "kind": "VALYQON_CI_IMAGE_IDENTITY_EVIDENCE_V1",
        "source_checkout_sha": checkout_sha,
        "source_checkout_tree": tree_sha,
        "dockerfile_sha256": dockerfile_sha256,
        "image_local_id": inspect["Id"],
        "image_local_tag": EXPECTED_IMAGE,
        "oci_revision_matches_checkout": True,
        "oci_source_matches_repository": True,
        "identity_scope": "SINGLE_GITHUB_CI_RUN_LOCAL_IMAGE_ONLY",
        "signed_build_attestation": "NOT_VERIFIED",
        "registry_digest": "NOT_VERIFIED",
        "running_public_vps_image_id": "NOT_VERIFIED",
        "running_public_vps_source_sha": "NOT_VERIFIED",
        "encrypted_off_host_backup_restore": "NOT_VERIFIED",
        "rollback_rehearsal": "NOT_VERIFIED",
        "source_worker_customer_delivery": "NOT_VERIFIED",
        "commercial_launch_approved": False,
        "public_deployment_authorized": False,
        "production_changed": False,
    }


def _run(*args: str) -> str:
    result = subprocess.run(
        args, check=True, capture_output=True, text=True, timeout=20
    )
    return result.stdout.strip()


def inspect_local_image() -> dict[str, Any]:
    # Only trusted fixed local image name; no user-provided image or remote host.
    raw = _run("docker", "image", "inspect", "--format", "{{json .}}",
               EXPECTED_IMAGE)
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise EvidenceError("INVALID_LOCAL_INSPECT_FORMAT")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify ONLY local CI Docker image↔source metadata."
    )
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        # Verify SHA syntax before any subprocess.
        if not GIT_SHA.fullmatch(args.expected_sha):
            raise EvidenceError("INVALID_EXPECTED_SHA")
        checkout = _run("git", "rev-parse", "HEAD")
        tree = _run("git", "rev-parse", "HEAD^{tree}")
        dockerfile = Path("Dockerfile")
        if not dockerfile.is_file():
            raise EvidenceError("DOCKERFILE_MISSING")
        digest = hashlib.sha256(dockerfile.read_bytes()).hexdigest()
        report = evidence(
            inspect_local_image(), expected_sha=args.expected_sha,
            checkout_sha=checkout, tree_sha=tree,
            dockerfile_sha256=digest,
        )
        # CI artifacts never include Docker inspect Env, SSH keys or .env.
        Path(args.output).write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print("LOCAL_CI_IMAGE_SHA_BINDING=PASS")
        print("PUBLIC_VPS_PROVENANCE=NOT_VERIFIED")
        print("DEPLOYMENT_AUTHORIZED=NO")
        return 0
    except (EvidenceError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
            OSError, json.JSONDecodeError, TypeError) as exc:
        code = str(exc) if isinstance(exc, EvidenceError) else type(exc).__name__
        print("LOCAL_CI_IMAGE_SHA_BINDING=FAIL")
        print("FAILURE_CLASS=" + code)
        print("DEPLOYMENT_AUTHORIZED=NO")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
