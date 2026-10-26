"""One-command, read-only public SaaS launch diagnostic.

Combines already-reviewed synthetic local Docker Compose, pinned SSH inventory,
and strict external HTTPS tests. Does NOT deploy, handle keys' bytes, start
containers, access backups/customer databases, send mail or approve commercial
go-live. Every external gate is explicitly NOT_VERIFIED until separate evidence.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from scripts import valyqon_local_compose_preflight as local
from scripts import valyqon_vps_readonly_preflight as vps
from scripts import verify_public_https as edge

DEFAULT_UNVERIFIED = (
    "postgresql_operator_restore",
    "external_mail_delivery",
    "real_source_to_consenting_user",
    "payment_provider_signed_entitlements",
    "approved_seller_privacy_and_terms",
    "notification_provider_ack",
    "external_llm",
)


def evaluate(*, ssh_host: str, ssh_key: str, hostname: str,
             expected_sha: str, local_check=local.local_probe,
             ssh_check=vps.inspect, https_check=edge.verify) -> dict:
    # Validate everything before any subprocess or outbound connection.
    vps.validated_host(ssh_host)
    edge.validate_target("https://" + hostname)
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("Exact 40-character commit SHA required")
    if not isinstance(ssh_key, str) or not Path(ssh_key).is_file():
        raise ValueError("An existing local SSH key path is required")
    result = {
        "kind": "VALYQON_PUBLIC_LAUNCH_READ_ONLY",
        "expected_sha": expected_sha,
        "local_compose": "NOT_VERIFIED",
        "vps_ssh": "NOT_VERIFIED",
        "vps_public_tree": "NOT_VERIFIED",
        "vps_exact_sha": "NOT_VERIFIED",
        "vps_api_caddy": "NOT_VERIFIED",
        "private_preview_not_counted": True,
        "external_https": "NOT_VERIFIED",
        "external_homepage": "NOT_VERIFIED",
        "external_health": "NOT_VERIFIED",
        "blocked_gates": list(DEFAULT_UNVERIFIED),
        "production_changed": False,
        "public_commercial_launch_approved": False,
    }
    try:
        checked=local_check()
        if checked.get("LOCAL_RELEASE_COMPOSE")=="PASS":
            result["local_compose"]="PASS_SYNTHETIC_ONLY"
        else:
            result["local_compose"]="BLOCKED"
    except (ValueError, RuntimeError, OSError, KeyError, TypeError):
        result["local_compose"]="BLOCKED"
    try:
        status,same=ssh_check(ssh_host,ssh_key,expected_sha=expected_sha)
        result["vps_ssh"]="PASS_READ_ONLY"
        result["vps_public_tree"]="PASS" if (
            status.get("REPO_PRESENT")=="YES"
            and status.get("PUBLIC_COMPOSE_PRESENT")=="YES") else "BLOCKED"
        result["vps_exact_sha"]="PASS" if same else "BLOCKED"
        result["vps_api_caddy"]="PASS" if all(
            status.get(f"PUBLIC_{service}_RUNNING")=="YES"
            for service in ("api","caddy")) else "BLOCKED"
        result["private_preview_not_counted"]=True
    except vps.SSHPreflightError as exc:
        result["vps_ssh"]="BLOCKED_"+exc.failure_code
    except (ValueError, RuntimeError, OSError, TypeError):
        result["vps_ssh"]="BLOCKED_UNCLASSIFIED"
    try:
        status=https_check("https://"+hostname)
        result["external_https"]="PASS" if status.get("public_edge_pass") is True else "BLOCKED"
        result["external_homepage"]=status.get("homepage","NOT_VERIFIED")
        result["external_health"]=status.get("health","NOT_VERIFIED")
        result["edge_failure_class"]=status.get("redirect_class") or status.get("blocker_type") or "NONE"
    except (ValueError, RuntimeError, OSError, TypeError):
        result["external_https"]="BLOCKED"
        result["edge_failure_class"]="PROBE_UNAVAILABLE"
    # All internet, SSH and Docker checks are independent. An old image, SSH
    # failure, or a healthy PRIVATE preview can never satisfy production launch.
    result["technical_staging_edge_pass"] = (
        result["local_compose"]=="PASS_SYNTHETIC_ONLY"
        and result["vps_ssh"]=="PASS_READ_ONLY"
        and all(result[k]=="PASS" for k in (
            "vps_public_tree","vps_exact_sha","vps_api_caddy","external_https",
            "external_homepage","external_health",
        ))
    )
    return result


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--ssh-host",required=True)
    parser.add_argument("--ssh-key",required=True)
    parser.add_argument("--hostname",required=True)
    parser.add_argument("--expected-sha",required=True)
    args=parser.parse_args(argv)
    try:
        result=evaluate(ssh_host=args.ssh_host,ssh_key=args.ssh_key,
                        hostname=args.hostname,expected_sha=args.expected_sha)
    except (ValueError,TypeError):
        print(json.dumps({
            "kind":"VALYQON_PUBLIC_LAUNCH_READ_ONLY",
            "preflight":"BLOCKED_INPUT_VALIDATION",
            "production_changed":False,
            "public_commercial_launch_approved":False,
        },sort_keys=True))
        return 2
    # Deliberately omit host, key, username, remote stderr, .env and response
    # bodies: report only fixed-state evidence, not access details.
    print(json.dumps(result,sort_keys=True))
    return 0 if result["technical_staging_edge_pass"] else 2


if __name__=="__main__":
    raise SystemExit(main())
