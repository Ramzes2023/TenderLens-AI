"""Very small, read-only pinned-SSH inspection of the actual VPS Caddy edge.

No source export, Docker mutation, database, files, keys, Caddy reload or
customer-data access. Only sanitized operational classes reach stdout.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

from scripts.valyqon_vps_readonly_preflight import validated_host


def ssh_readonly(host: str, key: str, source: str, *, runner=subprocess.run):
    args = [
        "ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10",
        "-i", key, "ubuntu@" + host, "sh", "-s",
    ]
    try:
        result = runner(args, input=source, capture_output=True, text=True,
                        timeout=25, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if (result.returncode != 0 or type(result.stdout) is not str
            or len(result.stdout) > 12000):
        return None
    return result.stdout.strip()


def inspect(host: str, key: str, *, runner=subprocess.run) -> dict:
    validated_host(host)
    if not isinstance(key, str) or not Path(key).is_file():
        raise ValueError("A previously trusted local SSH key is required")
    report = {
        "kind": "VALYQON_PUBLIC_CADDY_TOPOLOGY_READ_ONLY",
        "ssh": "NOT_VERIFIED", "docker": "UNKNOWN", "edge_kind": "UNKNOWN",
        "edge_instances": "UNKNOWN", "edge_compose_service": "UNKNOWN",
        "edge_compose_project": "UNKNOWN", "edge_config_mount": "UNKNOWN",
        "production_checkout": "UNKNOWN", "public_compose": "UNKNOWN",
        "static_caddy_overlay_compatible": False,
        "production_changed": False, "private_preview_untouched": True,
        "rollback_proven": False, "backup_restore_proven": False,
    }
    # Tiny independent commands are intentional: the already-observed host
    # permits minimal commands but can reject a long remote stdin script.
    echo = ssh_readonly(host, key, "echo VALYQON_SSH_READ_ONLY_OK\n", runner=runner)
    if echo != "VALYQON_SSH_READ_ONLY_OK":
        report["ssh"] = "BLOCKED"
        return report
    report["ssh"] = "PASS"
    ls = ssh_readonly(
        host, key,
        "docker ps --format '{{.ID}}|{{.Image}}|{{.Names}}'\n",
        runner=runner,
    )
    if ls is None:
        report["docker"] = "UNKNOWN"
        return report
    report["docker"] = "PASS_READ_ONLY"
    values = []
    for raw in ls.splitlines():
        line = raw.strip().split("|")
        if (len(line) != 3 or not re.fullmatch(r"[0-9a-f]{12,64}", line[0])
                or not all(line[1:]) or len(raw) > 500):
            report["edge_kind"] = "UNKNOWN"
            return report
        values.append(line)
    # Do not print private container names/image registry values.
    caddies = [item for item in values if "caddy" in (item[1] + " " + item[2]).lower()]
    nginx = [item for item in values if "nginx" in (item[1] + " " + item[2]).lower()]
    report["edge_kind"] = "CADDY" if caddies else "NGINX" if nginx else "UNKNOWN"
    report["edge_instances"] = "ONE" if len(caddies) == 1 else "MULTIPLE" if caddies else "NONE"
    if len(caddies) != 1:
        return report
    container_id = caddies[0][0]
    # Exact Docker-provided labels and container mount *destinations* only.
    labels = ssh_readonly(
        host, key,
        "docker inspect --format '{{index .Config.Labels \"com.docker.compose.project\"}}|{{index .Config.Labels \"com.docker.compose.service\"}}' "
        + container_id + "\n",
        runner=runner,
    )
    if labels is not None:
        parts = labels.strip().split("|")
        if len(parts) == 2:
            project, service = parts
            report["edge_compose_service"] = "YES" if service == "caddy" else "NO"
            report["edge_compose_project"] = (
                "PRESENT" if project and project != "<no value>" else "ABSENT"
            )
    mounts = ssh_readonly(
        host, key,
        "docker inspect --format '{{range .Mounts}}{{.Destination}}:{{.RW}};{{end}}' "
        + container_id + "\n",
        runner=runner,
    )
    if mounts is not None:
        mount_list = mounts.strip().split(";")
        report["edge_config_mount"] = (
            "READ_ONLY" if "/etc/caddy/Caddyfile:false" in mount_list
            else "WRITEABLE" if "/etc/caddy/Caddyfile:true" in mount_list
            else "NOT_DETECTED"
        )
    tree = ssh_readonly(
        host, key,
        "if test -d /opt/tenderlens/.git; then echo YES; else echo NO; fi\n",
        runner=runner,
    )
    compose = ssh_readonly(
        host, key,
        "if test -f /opt/tenderlens/compose.public.yaml; then echo YES; else echo NO; fi\n",
        runner=runner,
    )
    report["production_checkout"] = tree if tree in ("YES", "NO") else "UNKNOWN"
    report["public_compose"] = compose if compose in ("YES", "NO") else "UNKNOWN"
    report["static_caddy_overlay_compatible"] = all([
        report["docker"] == "PASS_READ_ONLY",
        report["edge_kind"] == "CADDY",
        report["edge_instances"] == "ONE",
        report["edge_compose_service"] == "YES",
        report["edge_compose_project"] == "PRESENT",
        report["edge_config_mount"] == "READ_ONLY",
        report["production_checkout"] == "YES",
        report["public_compose"] == "YES",
    ])
    # Compatible only means likely topology, NOT permission to cut over.
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--ssh-host", required=True)
    parser.add_argument("--ssh-key", required=True)
    args = parser.parse_args(argv)
    try:
        result = inspect(args.ssh_host, args.ssh_key)
    except ValueError:
        result = {"kind": "VALYQON_PUBLIC_CADDY_TOPOLOGY_READ_ONLY",
                  "ssh": "BLOCKED_INPUT", "static_caddy_overlay_compatible": False,
                  "production_changed": False}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["static_caddy_overlay_compatible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
