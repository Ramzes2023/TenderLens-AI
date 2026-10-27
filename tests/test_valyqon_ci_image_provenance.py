"""Falsify local Docker identity claims without Docker, network or credentials."""
from __future__ import annotations

import copy
import re

import pytest

from scripts.valyqon_ci_image_provenance import (
    EXPECTED_IMAGE,
    EXPECTED_SOURCE,
    EvidenceError,
    evidence,
)

SHA="a"*40
TREE="b"*40
DOCKERFILE_DIGEST="c"*64
LOCAL_IMAGE_ID="sha256:"+"d"*64


def valid_inspect():
    # Real Docker inspect may contain secret-bearing Config.Env; never leak it
    # through evidence output, even when the local Docker image stores it.
    return {
        "Id": LOCAL_IMAGE_ID,
        "RepoTags": [EXPECTED_IMAGE],
        "Config": {
            "Labels": {
                "org.opencontainers.image.revision": SHA,
                "org.opencontainers.image.source": EXPECTED_SOURCE,
                "com.valyqon.build.kind": "isolated-ci-audit-only",
            },
            "Env": ["A_PASSWORD=NOT_FOR_OUTPUT", "PROXY_AUTH=NOT_FOR_OUTPUT"],
        },
        "RepoDigests": ["private.registry.invalid/secret@sha256:" + "e"*64],
    }


def check(source=None, **kwargs):
    return evidence(
        valid_inspect() if source is None else source,
        expected_sha=kwargs.get("expected_sha", SHA),
        checkout_sha=kwargs.get("checkout_sha", SHA),
        tree_sha=kwargs.get("tree_sha", TREE),
        dockerfile_sha256=kwargs.get("dockerfile_sha256", DOCKERFILE_DIGEST),
    )


def test_exact_local_image_identity_receipt_does_not_authorize_release():
    manifest=check()
    assert manifest["image_local_id"]==LOCAL_IMAGE_ID
    assert manifest["source_checkout_sha"]==SHA
    assert manifest["source_checkout_tree"]==TREE
    assert manifest["dockerfile_sha256"]==DOCKERFILE_DIGEST
    assert manifest["oci_revision_matches_checkout"] is True
    assert manifest["signed_build_attestation"]=="NOT_VERIFIED"
    assert manifest["registry_digest"]=="NOT_VERIFIED"
    assert manifest["running_public_vps_source_sha"]=="NOT_VERIFIED"
    assert manifest["encrypted_off_host_backup_restore"]=="NOT_VERIFIED"
    assert manifest["rollback_rehearsal"]=="NOT_VERIFIED"
    assert manifest["public_deployment_authorized"] is False
    assert manifest["commercial_launch_approved"] is False
    assert manifest["production_changed"] is False
    assert "NOT_FOR_OUTPUT" not in str(manifest)
    assert "private.registry.invalid" not in str(manifest)
    assert "secret" not in str(manifest)


@pytest.mark.parametrize("change,error",[
    ("bad_expected","INVALID_GIT_IDENTITY"),
    ("different_checkout","CHECKOUT_SHA_MISMATCH"),
    ("invalid_tree","INVALID_GIT_IDENTITY"),
    ("invalid_dockerfile_digest","INVALID_DOCKERFILE_SHA256"),
    ("invalid_image_id","MISSING_IMAGE_ID"),
    ("missing_labels","MISSING_OCI_LABELS"),
    ("wrong_revision","IMAGE_REVISION_MISMATCH"),
    ("wrong_source","IMAGE_SOURCE_MISMATCH"),
    ("wrong_kind","NOT_AN_ISOLATED_AUDIT_IMAGE"),
    ("wrong_local_tag","LOCAL_AUDIT_TAG_MISSING"),
])
def test_wrong_binding_is_never_accepted(change,error):
    item=valid_inspect()
    args={}
    if change=="bad_expected":
        args["expected_sha"]="not-a-sha"
    elif change=="different_checkout":
        args["checkout_sha"]="f"*40
    elif change=="invalid_tree":
        args["tree_sha"]="broken"
    elif change=="invalid_dockerfile_digest":
        args["dockerfile_sha256"]="wrong"
    elif change=="invalid_image_id":
        item["Id"]="sha256:wrong"
    elif change=="missing_labels":
        item["Config"]["Labels"]=None
    elif change=="wrong_revision":
        item["Config"]["Labels"]["org.opencontainers.image.revision"]="f"*40
    elif change=="wrong_source":
        item["Config"]["Labels"]["org.opencontainers.image.source"]="https://invalid.example"
    elif change=="wrong_kind":
        item["Config"]["Labels"]["com.valyqon.build.kind"]="production-release"
    elif change=="wrong_local_tag":
        item["RepoTags"]=["tenderlens-ai:latest"]
    with pytest.raises(EvidenceError,match=re.escape(error)):
        check(item,**args)


def test_missing_and_invalid_inspect_fail_closed():
    for payload in (None,{},[],{"Id":LOCAL_IMAGE_ID}, {"Id":LOCAL_IMAGE_ID,"Config":{}}):
        with pytest.raises((EvidenceError,AttributeError)):
            check(payload if payload is not None else {})


def test_report_does_not_claim_registry_digest_even_if_inspect_lists_one():
    item=valid_inspect()
    item["RepoDigests"]=["public.registry.example/valyqon@sha256:" + "f"*64]
    report=check(item)
    assert report["registry_digest"]=="NOT_VERIFIED"
    assert not any("registry.example" in str(value) for value in report.values())
