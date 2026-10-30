"""Offline-only safety contract for disposable STAN V6 Worker operator proof."""
import os
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "VALYQON-V6-STAN-PAGE2-TEMP-WORKER-READONLY.ps1"

MOCK_DOCKER = """#!/usr/bin/env python3
import os
import sys
case = os.environ.get("V6_FAKE_CASE")
cmd = sys.argv[1:]
with open(os.environ["V6_FAKE_LOG"],"a") as f:
    f.write(cmd[0] + "\\n")
if case == "docker_error":
    sys.exit(9)
if cmd[0] == "ps":
    if not ("label=com.docker.compose.project=valyqon-public-sources" in cmd
            and "label=com.docker.compose.service=worker-v6" in cmd):
        sys.exit(10)
    print({"ok":"v6abc", "double":"v6abc\\nv6def", "bad_image":"v6abc"}.get(case, ""))
elif cmd[0] == "inspect":
    print("valyqon-public-sources:v6-wrong" if case == "bad_image"
          else "valyqon-public-sources:v6-fe4c66bbd553")
elif cmd[0] == "exec":
    payload = sys.stdin.read()
    if "TemporaryDirectory(" not in payload or "stan_runtime.MAX_DETAILS = 1" not in payload:
        sys.exit(11)
    print("V6_STAN_TEMP_WORKER=PASS")
    print("PRODUCTION_CHANGED=NO")
else:
    sys.exit(12)
"""

def parsed():
    raw = SCRIPT.read_text(encoding="utf-8-sig")
    head, sep, tail = raw.partition("$remote = @'\n")
    assert sep, "Missing POSIX here-string"
    shell, sep, footer = tail.partition("\n'@\n")
    assert sep, "Missing POSIX here-string close"
    match = re.search(r"python - <<'PY'\n(.*?)\nPY\n?$", shell, re.S)
    assert match, "Missing exclusive Python here-doc"
    return raw, shell + "\n", match.group(1)

class V6TempWorkerScriptSafety(unittest.TestCase):
    def test_embedded_python_compiles_and_is_pinned(self):
        source, shell, python = parsed()
        compile(python, "<offline-disposable-worker>", "exec")
        self.assertTrue(shell.startswith("set -eu\n"))
        self.assertIn("label=com.docker.compose.service=worker-v6", shell)
        self.assertIn("valyqon-public-sources:v6-fe4c66bbd553", shell)
        self.assertIn("stan_runtime.MAX_DETAILS == 2", python)
        self.assertIn('stan_runtime.MAX_DETAILS = 1', python)
        self.assertLess(python.index('if any(os.environ.get(k) != v'),
                        python.index('stan_runtime.MAX_DETAILS = 1'))
        self.assertIn("with tempfile.TemporaryDirectory(", python)
        self.assertIn('dir="/tmp"', python)
        self.assertIn("ConnectorSyncHandler(catalog, store, max_records=3)", python)
        self.assertIn("JobRepository(db", python)
        self.assertIn("snapshot_catalog(catalog, store)", python)
        self.assertIn("store.upsert(notice, connector_version", python)
        self.assertIn("temporary_database_only", python)
        self.assertIn("EPHEMERAL_OFFICIAL_PAGE_TWO", python)
        self.assertIn("https://stantorgi.ru/etp?page=2", python)
        self.assertIn("stan_runtime.canonical(url) != url", python)
        self.assertIn("stan_runtime.source_client = page_two_only_client", python)
        self.assertIn('DB_PATH = "/app/data/isolated-public-sources.sqlite3"', python)
        self.assertIn("with tempfile.TemporaryDirectory(", python)
        self.assertIn("eligible_published_deadline(", python)
        self.assertNotIn("sqlite3.connect(DB_PATH)", source)
        self.assertNotIn("docker compose up", source)
        self.assertNotIn("docker restart", source)
        self.assertNotIn("telegram.send", source)

    def run_case(self, case):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            stub = root / "docker"
            stub.write_text(MOCK_DOCKER, encoding="utf-8")
            stub.chmod(0o755)
            log = root / "calls"
            env = {**os.environ, "PATH": str(root) + os.pathsep + os.environ.get("PATH",""),
                   "V6_FAKE_CASE": case, "V6_FAKE_LOG": str(log)}
            _, shell, _ = parsed()
            proc = subprocess.run(["sh","-s"], input=shell, text=True,
                                  capture_output=True, env=env, timeout=6)
            calls = log.read_text().splitlines() if log.exists() else []
            return proc.returncode, proc.stdout, calls

    def test_only_observed_exact_v6_image_can_run_disposable_proof(self):
        code, stdout, calls = self.run_case("ok")
        self.assertEqual(code, 0)
        self.assertIn("V6_EXACT_WORKER=VERIFIED_UNIQUE_PINNED_IMAGE", stdout)
        self.assertEqual(calls.count("exec"), 1)
        for case in ("double", "bad_image", "none", "docker_error"):
            with self.subTest(case=case):
                code, stdout, calls = self.run_case(case)
                self.assertEqual(code, 2)
                self.assertIn("PRODUCTION_CHANGED=NO", stdout)
                self.assertEqual(calls.count("exec"), 0)

if __name__ == "__main__":
    unittest.main()
