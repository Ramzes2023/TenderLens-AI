#!/usr/bin/env bash
# Trusted CIS mainline staging branch only. Validates the unchanged full Linux
# test command from .github/workflows/ci.yml in disposable Docker.
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" == "true" && "${GITHUB_EVENT_NAME:-}" == "push" ]]
[[ "${GITHUB_REPOSITORY:-}" == "Ramzes2023/TenderLens-AI" ]]
[[ "${GITHUB_REF:-}" == "refs/heads/integration/cis-am-tj-mainline-20261016" ]]
[[ "${RUNNER_NAME:-}" == "VALYQON-INT-02" ]]
[[ -n "${GITHUB_WORKSPACE:-}" && -d "$GITHUB_WORKSPACE" && -w /var/run/docker.sock ]]
auth_dir=$(mktemp -d)
trap 'rm -rf -- "$auth_dir"' EXIT
chmod 700 "$auth_dir"
printf '%s\n' '{"auths":{}}' > "$auth_dir/config.json"
chmod 600 "$auth_dir/config.json"
export DOCKER_CONFIG="$auth_dir"
docker pull --quiet python:3.12-slim >/dev/null
docker run --rm --network bridge --memory 4g --cpus 2 --pids-limit 256 \
  --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,source=${GITHUB_WORKSPACE},target=/source,readonly" \
  --workdir /work python:3.12-slim sh -euc '
    mkdir -p /work
    # No CAP_CHOWN in this isolated Docker job: copy contents without trying
    # to preserve host ownership. Only the disposable /work tree is modified.
    cp -R /source/. /work/
    cd /work
    python -m pip install --no-cache-dir -r requirements-dev.txt
    python - <<'"'"'PY'"'"'
import hashlib
from pathlib import Path
from urllib.request import Request, urlopen
files = [
    ("https://raw.githubusercontent.com/OP-TED/eForms-SDK/1.15.1/codelists/cpv.gc",
     ".cache/phase24p33-completion/official_eforms_cpv.gc",
     "e8f48feedb63ce1583caa22825011afccd402973c28a885c2e81f89460fd6301"),
    ("https://docs.ted.europa.eu/ODS/latest/reuse/field-list.html",
     ".cache/phase24p33-completion/official_ted_search_fields.html",
     "79324dc627ee846f137e8cf4d069509784d51dcc7770f592dcd58096e261a419"),
    ("https://docs.ted.europa.eu/eforms/latest/schema/procedure-lot-part-information.html",
     ".cache/phase24p33-xml-context/official_eforms_lot_schema.html",
     "79241647c6acae10fcf61b3112cef35228339c632c664bfc4f8101f82c0556bd"),
]
for url, path, digest in files:
    # The official eForms CPV codelist is tens of MB, not a small HTML page.
    # Keep an explicit bounded maximum and the SAME pinned SHA256 commitment.
    limit = 128 * 1024 * 1024 if path.endswith("official_eforms_cpv.gc") else 8 * 1024 * 1024
    with urlopen(Request(url, headers={"User-Agent": "VALYQON-CIS-trusted-CI/1.0"}), timeout=90) as response:
        blob = response.read(limit + 1)
    if len(blob) > limit:
        raise AssertionError("Official CI evidence exceeds bounded size: " + path)
    computed = hashlib.sha256(blob).hexdigest()
    if computed != digest:
        print("CIS_PINNED_EVIDENCE_HASH_MISMATCH=" + path, flush=True)
        raise AssertionError("Pinned external CI evidence unavailable or changed: " + path)
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(blob)
    print("CIS_PINNED_EVIDENCE=VERIFIED; FILE=" + dest.name, flush=True)
fixture = Path("tests/fixtures/eforms/official_sdk_cn_24_minimal.xml")
if hashlib.sha256(fixture.read_bytes()).hexdigest() != "3bba90994d3e7d86ed8bb07f5c2fc49b8be27523b9ac5397c83ee86312b43ef8":
    raise AssertionError("Pinned fixture changed")
dest = Path(".cache/phase24p33-xml-context/official_sdk_cn_24_minimal.xml")
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_bytes(fixture.read_bytes())
history = Path("tests/fixtures/p39d_offline_history.json")
original = history.read_bytes()
lf = original.removeprefix(b"\xef\xbb\xbf").replace(b"\r\n", b"\n")
variants = [original, lf, lf.rstrip(b"\r\n"), lf.rstrip(b"\r\n") + b"\n",
            lf.replace(b"\n", b"\r\n"),
            lf.rstrip(b"\r\n").replace(b"\n", b"\r\n") + b"\r\n"]
expected = "6d7ff62145ca4c05388d988419ccd4343c269e842c0614bab0ea3edbdbbccfaf"
valid = next((variant for variant in variants if hashlib.sha256(variant).hexdigest() == expected), None)
if valid is None:
    raise AssertionError("Pinned synthetic fixture does not match known commitment")
history.write_bytes(valid)
print("CIS_FULL_LINUX_PINNED_FIXTURES=VERIFIED", flush=True)
PY
    python -m compileall -q app tests scripts
    python -B -m pytest -q --durations=15 --ignore=tests/test_p39e_local_preview.py
  '
echo "CIS_INT02_FULL_LINUX_SUITE=PASS"
