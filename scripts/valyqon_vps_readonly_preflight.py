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
echo PREFLIGHT_SCHEMA=2
if test -d /opt/tenderlens/.git; then
  echo REPO_PRESENT=YES
  rev="$(git -C /opt/tenderlens rev-parse --verify HEAD 2>/dev/null || true)"
  case "$rev" in
    *[!0123456789abcdef]*|'') echo REMOTE_SHA=UNKNOWN;;
    *) echo "REMOTE_SHA=$rev";;
  esac
  if test -z "$(git -C /opt/tenderlens status --porcelain 2>/dev/null)"; then
    echo WORKTREE_CLEAN=YES
  else
    echo WORKTREE_CLEAN=NO
  fi
else
  echo REPO_PRESENT=NO
  echo REMOTE_SHA=UNKNOWN
  echo WORKTREE_CLEAN=UNKNOWN
fi
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  echo DOCKER_USABLE=YES
else
  echo DOCKER_USABLE=NO
fi
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
   command -v docker >/dev/null 2>&1; then
  services="$(cd /opt/tenderlens &&
      docker compose -f compose.public.yaml ps --services --status running 2>/dev/null || true)"
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
# The existing owner AWS preview is *not* a public production site.
# Report its presence separately; never mistake a private preview for
# a deployed production checkout or public HTTPS.
if test -d /home/ubuntu/valyqon-personal-preview; then
  echo PRIVATE_PREVIEW_TREE_PRESENT=YES
else
  echo PRIVATE_PREVIEW_TREE_PRESENT=NO
fi
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  preview_running="$(docker ps     --filter 'label=com.docker.compose.project=valyqon-private-preview'     --format '{{.ID}}' 2>/dev/null || true)"
  if test -n "$preview_running"; then
    echo PRIVATE_PREVIEW_CONTAINERS_RUNNING=YES
  else
    echo PRIVATE_PREVIEW_CONTAINERS_RUNNING=NO
  fi
else
  echo PRIVATE_PREVIEW_CONTAINERS_RUNNING=UNKNOWN
fi
echo TELEGRAM_BOT_API_ACK=NOT_CHECKED
echo LIVE_TENDER_DB=NOT_CHECKED
echo EXTERNAL_HTTPS=NOT_CHECKED
echo PRODUCTION_CHANGED=NO
"""

class SSHPreflightError(RuntimeError):
    """Only a fixed diagnostic category, never private SSH stderr or key data."""

    def __init__(self, category: str):
        if category not in {
            "SSH_HOST_KEY_UNVERIFIED", "SSH_AUTH_REJECTED",
            "SSH_CONNECT_TIMEOUT", "SSH_CONNECTION_REFUSED",
            "SSH_ROUTE_UNREACHABLE", "SSH_DNS_FAILURE",
            "SSH_REMOTE_COMMAND_FAILED", "SSH_COMMAND_UNAVAILABLE",
            "SSH_PROCESS_TIMEOUT", "SSH_UNCLASSIFIED",
        }:
            category = "SSH_UNCLASSIFIED"
        self.failure_code = category
        super().__init__("SSH preflight failed (private error suppressed)")


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
        raise SSHPreflightError(_safe_ssh_failure(run.stderr, run.returncode))
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
