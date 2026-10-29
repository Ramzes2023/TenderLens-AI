"""Offline V6 inventory-grounded selection: fake Docker only, zero network."""
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PS1 = ROOT / "scripts" / "VALYQON-V6-LENOBL-EXISTING-IMAGE-READONLY.ps1"

FAKE_DOCKER = """#!/usr/bin/env python3
import os
import pathlib
import sys

case = os.environ["V6_FAKE_CASE"]
args = sys.argv[1:]
log = pathlib.Path(os.environ["V6_FAKE_LOG"])
with log.open("a") as file:
    file.write(" ".join(args) + "\\n")
if case == "docker_error":
    sys.exit(11)
if args[0] == "ps":
    # Only the 29 October operator-inventoried project+service labels are valid.
    if "label=com.docker.compose.project=valyqon-public-sources" not in args:
        sys.exit(12)
    if "label=com.docker.compose.service=worker-v6" not in args:
        sys.exit(13)
    values = {
        "actual_worker_v6": ["v6"],
        "duplicate_v6": ["v6", "v6b"],
        "wrong_image": ["v5"],
        "exited_v6": [],
        "only_legacy_worker": [],
        "only_production_worker": [],
        "no_v6": [],
    }.get(case, [])
    print("\\n".join(values))
elif args[0] == "inspect":
    if args[-1] == "v5":
        print("valyqon-public-sources:f6a75d355a49")
    elif args[-1] in ("v6", "v6b"):
        print("valyqon-public-sources:v6-fe4c66bbd553")
    else:
        sys.exit(14)
elif args[0] == "exec":
    print("V6_LENOBL_EXISTING_IMAGE=READONLY_DIAGNOSED")
    print("TELEGRAM_SEND_AUTHORIZED=NO")
    print("PRODUCTION_CHANGED=NO")
else:
    sys.exit(15)
"""

def shell_source():
    content = PS1.read_text(encoding="utf-8-sig")
    _, marker, rest = content.partition("$remote = @'\n")
    if not marker:
        raise AssertionError("No operator POSIX remote shell")
    shell, marker, _ = rest.partition("\n'@\n")
    if not marker or not shell.startswith("set -eu\n") or not shell.endswith("\nPY"):
        raise AssertionError("Bounded POSIX/Python heredoc missing")
    return shell + "\n"

class V6WorkerSelectionOffline(unittest.TestCase):
    def run_case(self, case):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            docker = root / "docker"
            docker.write_text(FAKE_DOCKER, encoding="utf-8")
            docker.chmod(0o755)
            log = root / "calls.txt"
            environment = {
                **os.environ,
                "PATH": str(root) + os.pathsep + os.environ.get("PATH", ""),
                "V6_FAKE_CASE": case,
                "V6_FAKE_LOG": str(log),
            }
            process = subprocess.run(
                ["sh", "-s"], input=shell_source(), text=True, env=environment,
                capture_output=True, timeout=8, check=False,
            )
            calls = log.read_text().splitlines() if log.exists() else []
            return process.returncode, process.stdout, process.stderr, calls

    def test_exact_observed_running_v6_is_selected(self):
        code, stdout, stderr, calls = self.run_case("actual_worker_v6")
        self.assertEqual(code, 0, stderr)
        self.assertIn("V6_PRIMARY_LABEL_MATCH_COUNT=1", stdout)
        self.assertIn("V6_SELECTION=EXACT_INVENTORIED_WORKER_V6", stdout)
        self.assertIn("V6_EXACT_WORKER=VERIFIED_UNIQUE_PINNED_IMAGE", stdout)
        self.assertEqual(sum(x.startswith("exec ") for x in calls), 1)
        self.assertTrue(any("label=com.docker.compose.service=worker-v6" in x for x in calls))

    def test_all_other_cases_fail_closed_without_docker_exec(self):
        for case in ("duplicate_v6", "wrong_image", "exited_v6",
                     "only_legacy_worker", "only_production_worker",
                     "no_v6", "docker_error"):
            with self.subTest(case=case):
                code, stdout, stderr, calls = self.run_case(case)
                self.assertEqual(code, 2, (case, stderr))
                self.assertIn("V6_EXACT_WORKER=BLOCKED_", stdout)
                self.assertIn("PRODUCTION_CHANGED=NO", stdout)
                self.assertFalse(any(x.startswith("exec ") for x in calls))
                self.assertFalse(any(x.startswith("ps ") and
                    "label=com.docker.compose.service=worker-v6" not in x
                    for x in calls))

if __name__ == "__main__":
    unittest.main()
