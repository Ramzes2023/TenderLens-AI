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
echo PREFLIGHT_SCHEMA=1
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
echo TELEGRAM_BOT_API_ACK=NOT_CHECKED
echo LIVE_TENDER_DB=NOT_CHECKED
echo EXTERNAL_HTTPS=NOT_CHECKED
echo PRODUCTION_CHANGED=NO
"""

KEYS = {
    "PREFLIGHT_SCHEMA", "REPO_PRESENT", "REMOTE_SHA", "WORKTREE_CLEAN",
    "DOCKER_USABLE", "PUBLIC_COMPOSE_PRESENT", "APP_ENV_FILE_PRESENT",
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
            if value != "1":
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
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError("SSH read-only preflight unavailable: " +
                           type(error).__name__) from None
    if run.returncode != 0:
        raise RuntimeError("SSH preflight failed (private error suppressed)")
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
