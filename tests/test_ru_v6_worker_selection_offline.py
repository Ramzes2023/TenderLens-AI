"""Pure offline test of the shell V6 worker selection; never calls real Docker."""
import os
import pathlib
import subprocess
import sys
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
    file.write(args[0] + "\\n")
if case == "docker_error":
    sys.exit(11)
images = {
    "iso1": "valyqon-public-sources:v6-fe4c66bbd553",
    "iso2": "valyqon-public-sources:v6-fe4c66bbd553",
    "alt1": "valyqon-public-sources:v6-fe4c66bbd553",
    "alt2": "valyqon-public-sources:v6-fe4c66bbd553",
    "prod_tag": "valyqon-public-sources:v6-fe4c66bbd553",
    "prod1": "tenderlens-vps:prod",
    "bad1": "valyqon-public-sources:v6-other",
}
owners = {
    "iso1": "valyqon-public-sources",
    "iso2": "valyqon-public-sources",
    "alt1": "six-live-sources-v6",
    "alt2": "six-live-sources-v6",
    "prod_tag": "tenderlens-vps",
    "prod1": "tenderlens-vps",
    "bad1": "valyqon-public-sources",
}
if args[0] == "ps":
    primary = any("com.docker.compose.project=valyqon-public-sources" in arg for arg in args)
    if primary:
        values = {
            "exact": ["iso1"],
            "primary_multiple": ["iso1", "iso2"],
            "bad_image": ["bad1"],
        }.get(case, [])
    else:
        values = {
            "alternate": ["alt1", "prod1"],
            "multiple_alt": ["alt1", "alt2"],
            "no_match": ["prod1"],
            "production_only": ["prod_tag"],
            "exact": ["iso1", "prod1"],
        }.get(case, [])
    print("\\n".join(values))
elif args[0] == "inspect":
    ident = args[-1]
    if "{{.Config.Image}}" in args:
        print(images[ident])
    elif any("com.docker.compose.project" in arg for arg in args):
        print(owners[ident])
    else:
        sys.exit(12)
elif args[0] == "exec":
    print("V6_LENOBL_EXISTING_IMAGE=READONLY_DIAGNOSED")
    print("TELEGRAM_SEND_AUTHORIZED=NO")
    print("PRODUCTION_CHANGED=NO")
else:
    sys.exit(13)
"""

def embedded_shell():
    content = PS1.read_text(encoding="utf-8-sig")
    head, sep, remainder = content.partition("$remote = @'\n")
    if not sep:
        raise AssertionError("Missing pinned operator shell here-string")
    shell, sep, tail = remainder.partition("\n'@\n")
    if not sep or not shell.startswith("set -eu\n") or not shell.endswith("\nPY"):
        raise AssertionError("Missing strict bounded shell or Python here-doc")
    return shell + "\n"

class V6SelectionOffline(unittest.TestCase):
    def run_case(self, case):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            stub = root / "docker"
            stub.write_text(FAKE_DOCKER, encoding="utf-8")
            stub.chmod(0o755)
            log = root / "calls.txt"
            env = {
                **os.environ,
                "PATH": str(root) + os.pathsep + os.environ.get("PATH", ""),
                "V6_FAKE_CASE": case,
                "V6_FAKE_LOG": str(log),
            }
            process = subprocess.run(
                ["sh", "-s"], input=embedded_shell(), text=True,
                capture_output=True, env=env, timeout=8, check=False,
            )
            calls = log.read_text().splitlines() if log.exists() else []
            return process.returncode, process.stdout, process.stderr, calls

    def test_exact_project_preserved(self):
        code, stdout, stderr, calls = self.run_case("exact")
        self.assertEqual(code, 0, stderr)
        self.assertIn("V6_PRIMARY_LABEL_MATCH_COUNT=1", stdout)
        self.assertIn("V6_SELECTION=EXACT_ORIGINAL_PROJECT", stdout)
        self.assertIn("V6_EXACT_WORKER=VERIFIED_UNIQUE_PINNED_IMAGE", stdout)
        self.assertEqual(calls.count("exec"), 1)

    def test_real_alt_compose_project_unique_pinned_worker(self):
        code, stdout, stderr, calls = self.run_case("alternate")
        self.assertEqual(code, 0, stderr)
        self.assertIn("V6_PRIMARY_LABEL_MATCH_COUNT=0", stdout)
        self.assertIn("V6_PINNED_IMAGE_WORKER_MATCH_COUNT=1", stdout)
        self.assertIn("V6_SELECTION=EXACT_IMAGE_ALTERNATE_COMPOSE_PROJECT", stdout)
        self.assertEqual(calls.count("exec"), 1)

    def test_fail_closed_on_ambiguity_or_wrong_image(self):
        for case in ("primary_multiple", "multiple_alt", "no_match",
                     "production_only", "bad_image", "docker_error"):
            with self.subTest(case=case):
                code, stdout, stderr, calls = self.run_case(case)
                self.assertEqual(code, 2, (case, stderr))
                self.assertIn("PRODUCTION_CHANGED=NO", stdout)
                self.assertIn("V6_EXACT_WORKER=BLOCKED_", stdout)
                self.assertEqual(calls.count("exec"), 0)
                self.assertNotIn("tenderlens-vps:prod", stdout)
                self.assertNotIn("valyqon-public-sources:v6-fe4c66bbd553", stdout)

if __name__ == "__main__":
    unittest.main()
