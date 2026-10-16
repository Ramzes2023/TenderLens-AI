#!/usr/bin/env bash
# Trusted owner-branch push only. All test code executes in disposable Docker
# containers; the laptop database, Docker credentials, and secrets are not mounted.
set -euo pipefail
mode="${1:-}"
if [[ "$mode" != "postgres" && "$mode" != "regression" ]]; then
  echo "CIS_INT02=INVALID_MODE"; exit 2
fi
if [[ "${RUNNER_NAME:-}" != "VALYQON-INT-02" || "${GITHUB_ACTIONS:-}" != "true" || "${GITHUB_REPOSITORY:-}" != "Ramzes2023/TenderLens-AI" || "${GITHUB_EVENT_NAME:-}" != "push" || "${GITHUB_REF:-}" != "refs/heads/integration/cis-am-tj-mainline-20261016" ]]; then
  echo "CIS_INT02=UNTRUSTED_RUN_CONTEXT"; exit 3
fi
if [[ -z "${GITHUB_WORKSPACE:-}" || ! -d "$GITHUB_WORKSPACE" ]]; then
  echo "CIS_INT02=INVALID_CHECKOUT"; exit 4
fi
if [[ ! -w /var/run/docker.sock ]]; then
  echo "CIS_INT02=DOCKER_NOT_ACCESSIBLE"; exit 5
fi
authless="$(mktemp -d)"
chmod 700 "$authless"
printf '%s\n' '{"auths":{}}' > "$authless/config.json"
chmod 600 "$authless/config.json"
export DOCKER_CONFIG="$authless"
network="valyqon_cis_${GITHUB_RUN_ID}_${GITHUB_RUN_ATTEMPT}_${mode}"
pg_name="${network}_pg"
network_created=0
pg_created=0
cleanup() {
  if (( pg_created )); then docker rm --force "$pg_name" >/dev/null 2>&1 || true; fi
  if (( network_created )); then docker network rm "$network" >/dev/null 2>&1 || true; fi
  rm -rf -- "$authless"
}
trap cleanup EXIT
echo "CIS_INT02_MODE=$mode"
echo "CIS_INT02_AUTH=PUBLIC_ONLY_ISOLATED_CONFIG"
docker pull --quiet python:3.12-slim >/dev/null
docker network create --driver bridge --label "valyqon-cis-run=${GITHUB_RUN_ID}" "$network" >/dev/null
network_created=1
if [[ "$mode" == "postgres" ]]; then
  docker pull --quiet postgres:16-alpine >/dev/null
  docker run --detach --name "$pg_name" --network "$network" --network-alias postgres \
    --memory 1g --pids-limit 128 --security-opt no-new-privileges \
    --env POSTGRES_USER=valyqon_ci \
    --env POSTGRES_PASSWORD=only-for-disposable-github-cis16 \
    --env POSTGRES_DB=postgres postgres:16-alpine >/dev/null
  pg_created=1
  ready=0
  for _ in $(seq 1 40); do
    if docker exec "$pg_name" pg_isready -h 127.0.0.1 -U valyqon_ci -d postgres >/dev/null 2>&1; then ready=1; break; fi
    sleep 1
  done
  if (( ! ready )); then
    echo "CIS_INT02_POSTGRES=NOT_READY"; exit 6
  fi
  echo "CIS_INT02_POSTGRES=CONTAINER_READY"
fi
docker run --rm --network "$network" --memory 4g --cpus 2 --pids-limit 256 \
  --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,source=${GITHUB_WORKSPACE},target=/workspace,readonly" \
  --workdir /workspace \
  --env CI=true --env GITHUB_ACTIONS=true \
  --env GITHUB_REPOSITORY=Ramzes2023/TenderLens-AI \
  --env GITHUB_EVENT_NAME=push \
  --env GITHUB_REF=refs/heads/integration/cis-am-tj-mainline-20261016 \
  --env RUNNER_NAME=VALYQON-INT-02 \
  --env PYTHON_DOTENV_DISABLED=1 \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  --env VALYQON_DATABASE_REQUIRE_POSTGRES=true \
  --env VALYQON_CIS_PG16_CONTEXT=valyqon-cis-postgres16-ephemeral-ci-v1 \
  --env VALYQON_CIS_PG16_PASSWORD=only-for-disposable-github-cis16 \
  --env VALYQON_CIS_PG16_HOST=postgres \
  --env CIS_INT02_MODE="$mode" \
  python:3.12-slim sh -euc '
    test -e /.dockerenv
    python --version
    python -m pip install --no-cache-dir -r requirements-dev.txt
    if [ "$CIS_INT02_MODE" = "postgres" ]; then
      getent hosts postgres >/dev/null
      exec python -B -m scripts.ci_cis_postgres16_fenced_acceptance
    else
      exec python -B -m pytest -p no:cacheprovider -q \
        tests/test_connector_workers.py \
        tests/test_cis_am_tj_main_integration.py \
        tests/test_international_sources.py \
        tests/test_ru03_integration.py
    fi
  '
echo "CIS_INT02_${mode^^}=PASS"
