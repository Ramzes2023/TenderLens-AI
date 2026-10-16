#!/usr/bin/env bash
# Real official HTTPS source -> leased worker -> disposable SQLite -> search.
# Owner-controlled push workflow only; no GitHub tokens, credentials or host databases.
set -euo pipefail
source_id="${1:-}"
case "$source_id" in am_armeps|tj_eprocurement) ;; *) echo "CIS_LIVE=INVALID_SOURCE"; exit 2;; esac
if [[ "${RUNNER_NAME:-}" != "VALYQON-INT-02" || "${GITHUB_ACTIONS:-}" != "true" || "${GITHUB_REPOSITORY:-}" != "Ramzes2023/TenderLens-AI" || "${GITHUB_EVENT_NAME:-}" != "push" || "${GITHUB_REF:-}" != "refs/heads/fix/cis-postgres16-fencing-gate-20261015" ]]; then
  echo "CIS_LIVE=UNTRUSTED_RUN_CONTEXT"; exit 3
fi
if [[ -z "${GITHUB_WORKSPACE:-}" || ! -d "$GITHUB_WORKSPACE" || ! -w /var/run/docker.sock ]]; then
  echo "CIS_LIVE=INVALID_ISOLATION_ENVIRONMENT"; exit 4
fi
authless="$(mktemp -d)"
chmod 700 "$authless"
printf '%s\n' '{"auths":{}}' > "$authless/config.json"
chmod 600 "$authless/config.json"
export DOCKER_CONFIG="$authless"
network="valyqon_cis_live_${GITHUB_RUN_ID}_${GITHUB_RUN_ATTEMPT}_${source_id}"
network_created=0
cleanup() {
  if (( network_created )); then docker network rm "$network" >/dev/null 2>&1 || true; fi
  rm -rf -- "$authless"
}
trap cleanup EXIT
echo "CIS_LIVE_SOURCE=$source_id"
echo "CIS_LIVE_DOCKER_AUTH=PUBLIC_ONLY_CONFIG"
docker pull --quiet python:3.12-slim >/dev/null
docker network create --driver bridge --label "valyqon-cis-live-run=${GITHUB_RUN_ID}" "$network" >/dev/null
network_created=1
docker run --rm --network "$network" --cpus 2 --memory 4g --pids-limit 256 \
  --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,source=${GITHUB_WORKSPACE},target=/workspace,readonly" \
  --workdir /workspace \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env PYTHON_DOTENV_DISABLED=1 \
  --env CIS_LIVE_SOURCE="$source_id" \
  python:3.12-slim sh -euc '
    test -e /.dockerenv
    python -m pip install --no-cache-dir -r requirements-dev.txt
    exec python -B -m scripts.ci_cis_am_tj_live_acceptance --source "$CIS_LIVE_SOURCE"
  '
echo "CIS_LIVE_${source_id^^}=PASS"
