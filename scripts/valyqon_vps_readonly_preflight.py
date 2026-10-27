"""Read-only, pinned-host-key SSH preflight for an existing VALYQON VPS.

No deploy, no checkout, no Docker start/stop, no DB/secret reads, no Telegram.
"""
import argparse
import ipaddress
import re
import subprocess
from pathlib import Path

REMOTE = r"""
set -u
printf '%s\n' VALYQON_PREFLIGHT_STAGE=START >&2
echo PREFLIGHT_SCHEMA=2
printf '%s\n' VALYQON_PREFLIGHT_STAGE=REPOSITORY >&2
if test -d /opt/tenderlens/.git; then
  echo REPO_PRESENT=YES
  rev="$(git -C /opt/tenderlens rev-parse --verify HEAD 2>/dev/null || true)"
  case "$rev" in
    *[!0123456789abcdef]*|'') echo REMOTE_SHA=UNKNOWN;;
    *) echo "REMOTE_SHA=$rev";;
  esac
  # A failed git status MUST NOT masquerade as a clean worktree.
  if worktree_status="$(git -C /opt/tenderlens status --porcelain 2>/dev/null)"; then
    if test -z "$worktree_status"; then
      echo WORKTREE_CLEAN=YES
    else
      echo WORKTREE_CLEAN=NO
    fi
  else
    echo WORKTREE_CLEAN=UNKNOWN
  fi
else
  echo REPO_PRESENT=NO
  echo REMOTE_SHA=UNKNOWN
  echo WORKTREE_CLEAN=UNKNOWN
fi
printf '%s\n' VALYQON_PREFLIGHT_STAGE=DOCKER >&2
# A hung Docker daemon must not stall the entire read-only VPS inventory.
# A timeout is UNKNOWN, not proof the daemon is unavailable. Never mutate it.
if ! command -v docker >/dev/null 2>&1; then
  echo DOCKER_USABLE=NO
elif ! command -v timeout >/dev/null 2>&1; then
  echo DOCKER_USABLE=UNKNOWN
elif timeout 6s docker info >/dev/null 2>&1; then
  echo DOCKER_USABLE=YES
else
  echo DOCKER_USABLE=UNKNOWN
fi
printf '%s\n' VALYQON_PREFLIGHT_STAGE=PUBLIC_COMPOSE >&2
if test -f /opt/tenderlens/compose.public.yaml; then
  echo PUBLIC_COMPOSE_PRESENT=YES
else
  echo PUBLIC_COMPOSE_PRESENT=NO
fi
if test -f /opt/tenderlens/.env; then
  echo APP_ENV_FILE_PRESENT=YES
else
  echo APP_ENV_FILE_PRESENT=NO
fi
if test -f /opt/tenderlens/compose.public.yaml &&
   command -v docker >/dev/null 2>&1 &&
   command -v timeout >/dev/null 2>&1; then
  # An unavailable Compose query is UNKNOWN, not proof a service is off.
  if services="$(cd /opt/tenderlens &&
      timeout 6s docker compose -f compose.public.yaml ps --services --status running 2>/dev/null)"; then
    for service in api caddy bot; do
      if printf '%s\n' "$services" | grep -qx "$service"; then
        printf 'PUBLIC_%s_RUNNING=YES\n' "$service"
      else
        printf 'PUBLIC_%s_RUNNING=NO\n' "$service"
      fi
    done
  else
    echo PUBLIC_api_RUNNING=UNKNOWN
    echo PUBLIC_caddy_RUNNING=UNKNOWN
    echo PUBLIC_bot_RUNNING=UNKNOWN
  fi
else
  echo PUBLIC_api_RUNNING=UNKNOWN
  echo PUBLIC_caddy_RUNNING=UNKNOWN
  echo PUBLIC_bot_RUNNING=UNKNOWN
fi
# The existing owner AWS preview is *not* a public production site.
# Report its presence separately; never mistake a private preview for
# a deployed production checkout or public HTTPS.
printf '%s\n' VALYQON_PREFLIGHT_STAGE=PRIVATE_PREVIEW >&2
if test -d /home/ubuntu/valyqon-personal-preview; then
  echo PRIVATE_PREVIEW_TREE_PRESENT=YES
else
  echo PRIVATE_PREVIEW_TREE_PRESENT=NO
fi
if command -v docker >/dev/null 2>&1 && command -v timeout >/dev/null 2>&1; then
  if preview_running="$(timeout 6s docker ps --filter 'label=com.docker.compose.project=valyqon-private-preview' --format '{{.ID}}' 2>/dev/null)"; then
    if test -n "$preview_running"; then
      echo PRIVATE_PREVIEW_CONTAINERS_RUNNING=YES
    else
      echo PRIVATE_PREVIEW_CONTAINERS_RUNNING=NO
    fi
  else
    echo PRIVATE_PREVIEW_CONTAINERS_RUNNING=UNKNOWN
  fi
else
  echo PRIVATE_PREVIEW_CONTAINERS_RUNNING=UNKNOWN
fi
echo TELEGRAM_BOT_API_ACK=NOT_CHECKED
echo LIVE_TENDER_DB=NOT_CHECKED
echo EXTERNAL_HTTPS=NOT_CHECKED
echo PRODUCTION_CHANGED=NO
printf '%s\n' VALYQON_PREFLIGHT_STAGE=COMPLETE >&2
"""

class SSHPreflightError(RuntimeError):
    """Only a fixed diagnostic category, never private SSH stderr or key data."""

    def __init__(self, category: str, *, stage="UNKNOWN", exit_code=None):
        if category not in {
            "SSH_HOST_KEY_UNVERIFIED", "SSH_AUTH_REJECTED",
            "SSH_CONNECT_TIMEOUT", "SSH_CONNECTION_REFUSED",
            "SSH_ROUTE_UNREACHABLE", "SSH_DNS_FAILURE",
            "SSH_REMOTE_COMMAND_FAILED", "SSH_REMOTE_SHELL_UNAVAILABLE",
            "SSH_REMOTE_SCRIPT_FAILED", "SSH_COMMAND_UNAVAILABLE",
            "SSH_PROCESS_TIMEOUT", "SSH_UNCLASSIFIED",
        }:
            category = "SSH_UNCLASSIFIED"
        self.failure_code = category
        self.stage = stage if stage in {
            "START", "REPOSITORY", "DOCKER", "PUBLIC_COMPOSE",
            "PRIVATE_PREVIEW", "COMPLETE", "UNKNOWN",
        } else "UNKNOWN"
        self.exit_class = (
            "SSH_TRANSPORT_255" if exit_code == 255
            else "REMOTE_NONZERO" if type(exit_code) is int and exit_code != 0
            else "UNKNOWN"
        )
        super().__init__("SSH preflight failed (private error suppressed)")


def _safe_remote_stage(stderr: str) -> str:
    """Only this finite enum can enter logs; never print remote stderr."""
    stages = {
        "START", "REPOSITORY", "DOCKER", "PUBLIC_COMPOSE",
        "PRIVATE_PREVIEW", "COMPLETE",
    }
    observed = [
        line.removeprefix("VALYQON_PREFLIGHT_STAGE=")
        for line in stderr.splitlines()
        if line.startswith("VALYQON_PREFLIGHT_STAGE=")
        and line.removeprefix("VALYQON_PREFLIGHT_STAGE=") in stages
    ] if type(stderr) is str else []
    return observed[-1] if observed else "UNKNOWN"


def _remote_shell_probe(ssh_prefix):
    """Independent read-only SSH shell check, no keys/env/data displayed."""
    # Match the full SSH stdin-shell invocation: a single fixed echo on stdin.
    # Avoid remote sh -c quoting differences on Windows OpenSSH.
    probe = ssh_prefix + ["sh", "-s"]
    try:
        run = subprocess.run(
            probe, input="echo VALYQON_REMOTE_SHELL_OK\n", capture_output=True, text=True,
            timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return (run.returncode == 0
            and run.stdout.strip() == "VALYQON_REMOTE_SHELL_OK")


def _segmented_readonly_inventory(ssh_prefix):
    """Retry only *read-only* exact SSH inventory in short bounded shell parts.

    Some SSH gateways accept the tiny verified shell command but reject a
    long stdin script before its first stage marker. Segment only at known
    stage boundaries where all previous shell compounds have already closed.
    Each fragment remains the fixed original, is transmitted to the same
    strictly host-key-verified host, and cannot consume local key contents
    or mutate the remote host. No partial output is ever accepted as success.
    """
    marker = "printf '%s\\n' VALYQON_PREFLIGHT_STAGE="
    parts = REMOTE.split(marker)
    stages = ("START", "REPOSITORY", "DOCKER",
              "PUBLIC_COMPOSE", "PRIVATE_PREVIEW", "COMPLETE")
    if len(parts) != len(stages) + 1:
        return None, "UNKNOWN"
    combined = []
    for stage, fragment in zip(stages, parts[1:]):
        script = "set -u\n" + marker + fragment
        try:
            run = subprocess.run(
                ssh_prefix + ["sh", "-s"],
                input=script, capture_output=True, text=True,
                timeout=22, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None, stage
        if run.returncode != 0 or _safe_remote_stage(run.stderr) != stage:
            return None, stage
        combined.append(run.stdout)
    try:
        return parse_status("\n".join(combined)), "COMPLETE"
    except ValueError:
        return None, "COMPLETE"


def _safe_ssh_failure(stderr: str, returncode: int) -> str:
    """Classify only known SSH errors. No remote stderr ever leaves inspect()."""
    value = stderr.lower() if type(stderr) is str else ""
    if ("remote host identification has changed" in value
            or "host key verification failed" in value
            or "no matching host key type found" in value):
        return "SSH_HOST_KEY_UNVERIFIED"
    if ("permission denied (publickey" in value or "permission denied (publickey," in value
            or "too many authentication failures" in value):
        return "SSH_AUTH_REJECTED"
    if "connection timed out" in value or "operation timed out" in value:
        return "SSH_CONNECT_TIMEOUT"
    if "connection refused" in value:
        return "SSH_CONNECTION_REFUSED"
    if "no route to host" in value or "network is unreachable" in value:
        return "SSH_ROUTE_UNREACHABLE"
    if "could not resolve hostname" in value or "name or service not known" in value:
        return "SSH_DNS_FAILURE"
    return "SSH_REMOTE_COMMAND_FAILED" if returncode != 255 else "SSH_UNCLASSIFIED"


KEYS = {
    "PREFLIGHT_SCHEMA", "REPO_PRESENT", "REMOTE_SHA", "WORKTREE_CLEAN",
    "DOCKER_USABLE", "PUBLIC_COMPOSE_PRESENT", "APP_ENV_FILE_PRESENT",
    "PRIVATE_PREVIEW_TREE_PRESENT", "PRIVATE_PREVIEW_CONTAINERS_RUNNING",
    "PUBLIC_api_RUNNING", "PUBLIC_caddy_RUNNING", "PUBLIC_bot_RUNNING",
    "TELEGRAM_BOT_API_ACK", "LIVE_TENDER_DB", "EXTERNAL_HTTPS",
    "PRODUCTION_CHANGED",
}

def validated_host(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9.-]{4,253}", value):
        raise ValueError("Unapproved host input")
    if value.startswith("-") or ".." in value:
        raise ValueError("Unapproved host input")
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        if "." not in value or value.endswith("."):
            raise ValueError("Unapproved hostname") from None
    else:
        if not ip.is_global:
            raise ValueError("Only a public server is accepted")
    return value

def parse_status(output):
    if len(output) > 9000:
        raise ValueError("Oversized preflight response")
    result = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key not in KEYS or key in result or len(value) > 60:
            raise ValueError("Untrusted preflight output")
        if key == "PREFLIGHT_SCHEMA":
            if value != "2":
                raise ValueError("Unexpected diagnostic version")
        elif key == "REMOTE_SHA":
            if value != "UNKNOWN" and not re.fullmatch("[0-9a-f]{40}", value):
                raise ValueError("Invalid Git revision")
        elif value not in {"YES", "NO", "UNKNOWN", "NOT_CHECKED"}:
            raise ValueError("Invalid diagnostic value")
        result[key] = value
    if set(result) != KEYS or result["PRODUCTION_CHANGED"] != "NO":
        raise ValueError("Incomplete or non-read-only preflight")
    return result

def inspect(host, key, user="ubuntu", expected_sha=None):
    host = validated_host(host)
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user):
        raise ValueError("Unsafe SSH username")
    if not Path(key).is_file():
        raise ValueError("Existing SSH key file required")
    if expected_sha is not None and not re.fullmatch("[0-9a-f]{40}", expected_sha):
        raise ValueError("Full expected Git commit required")
    args = ["ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
            "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10",
            "-i", str(key), user + "@" + host, "sh", "-s"]
    try:
        run = subprocess.run(args, input=REMOTE, capture_output=True, text=True,
                             timeout=45, check=False)
    except subprocess.TimeoutExpired:
        raise SSHPreflightError("SSH_PROCESS_TIMEOUT") from None
    except OSError:
        raise SSHPreflightError("SSH_COMMAND_UNAVAILABLE") from None
    if run.returncode != 0:
        code = _safe_ssh_failure(run.stderr, run.returncode)
        stage = _safe_remote_stage(run.stderr)
        if code == "SSH_REMOTE_COMMAND_FAILED":
            # A tiny shell control checks whether the command runs at all.
            # If it does and the full diagnostic had NO stage marker, recover
            # a complete inventory via the same signed fixed script split
            # at closed shell-compound boundaries. Never accept a partial
            # inventory or SSH exit 255; no host-key/auth bypass.
            if _remote_shell_probe(args[:-2]):
                if stage == "UNKNOWN":
                    segmented, diagnosed_stage = _segmented_readonly_inventory(args[:-2])
                    if segmented is not None:
                        out = segmented
                        same = expected_sha is not None and out["REMOTE_SHA"] == expected_sha
                        return out, same
                    # If even the first segmented multiline script fails
                    # while a one-line echo succeeded, try exact fixed tiny
                    # individual read-only SSH statements. Never treat an
                    # incomplete inventory as success or relax host-key
                    # verification. This is only a diagnostics fallback.
                    if diagnosed_stage == "START":
                        from scripts.valyqon_vps_short_ssh_inventory import short_inventory
                        short_report, tiny_stage = short_inventory(args[:-2])
                        if short_report is not None:
                            same = (expected_sha is not None
                                    and short_report["REMOTE_SHA"] == expected_sha)
                            return short_report, same
                        stage = tiny_stage
                    else:
                        stage = diagnosed_stage
                code = "SSH_REMOTE_SCRIPT_FAILED"
            else:
                code = "SSH_REMOTE_SHELL_UNAVAILABLE"
        raise SSHPreflightError(code, stage=stage, exit_code=run.returncode)
    out = parse_status(run.stdout)
    same = expected_sha is not None and out["REMOTE_SHA"] == expected_sha
    return out, same

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--user", default="ubuntu")
    parser.add_argument("--expected-sha")
    args = parser.parse_args(argv)
    try:
        results, same = inspect(args.host, args.key, args.user, args.expected_sha)
    except (ValueError, RuntimeError) as err:
        print("VALYQON_VPS_PREFLIGHT=BLOCKED")
        print("FAILURE_CLASS=" + type(err).__name__)
        print("FAILURE_CODE=" + getattr(err, "failure_code", "VALIDATION_OR_RESPONSE_ERROR"))
        print("FAILURE_STAGE=" + getattr(err, "stage", "UNKNOWN"))
        print("FAILURE_EXIT_CLASS=" + getattr(err, "exit_class", "UNKNOWN"))
        print("PRODUCTION_CHANGED=NO")
        return 2
    for key, val in sorted(results.items()):
        print(key + "=" + val)
    print("EXPECTED_MAIN_MATCH=" +
          ("NOT_CHECKED" if args.expected_sha is None else "YES" if same else "NO"))
    passed = (same and results["REPO_PRESENT"] == "YES" and
              results["WORKTREE_CLEAN"] == "YES" and
              results["DOCKER_USABLE"] == "YES" and
              results["PUBLIC_COMPOSE_PRESENT"] == "YES" and
              results["APP_ENV_FILE_PRESENT"] == "YES")
    print("VALYQON_VPS_PREFLIGHT=" + ("BASE_READY_ONLY" if passed else "BLOCKED"))
    print("PRODUCTION_DEPLOYED_BY_THIS_STEP=NO")
    return 0 if passed else 2

if __name__ == "__main__":
    raise SystemExit(main())
