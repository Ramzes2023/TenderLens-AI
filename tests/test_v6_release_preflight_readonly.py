"""Offline-only contract for fail-closed pinned V6 deployment preflight."""
import os
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "VALYQON-V6-RELEASE-PREFLIGHT-READONLY.ps1"

MOCK = """#!/usr/bin/env python3
import os
import sys
args=sys.argv[1:]
with open(os.environ["V6_FAKE_LOG"],"a") as f: f.write(args[0]+"\\n")
case=os.environ["V6_FAKE_CASE"]
if case=="docker_error": sys.exit(9)
if args[0]=="ps":
    if ("label=com.docker.compose.project=valyqon-public-sources" not in args
        or "label=com.docker.compose.service=worker-v6" not in args):
        sys.exit(10)
    print({"ok":"onlyv6", "double":"onlyv6\\nsecondv6", "bad_image":"onlyv6"}.get(case,""))
elif args[0]=="inspect":
    print("valyqon-public-sources:v6-wrong" if case=="bad_image"
          else "valyqon-public-sources:v6-fe4c66bbd553")
elif args[0]=="exec":
    payload=sys.stdin.read()
    if ("536870912" not in payload or "Path(\\"/app/data\\").is_mount()" not in payload
            or "READONLY_READY_FOR_SEPARATE_STAGE" not in payload):
        sys.exit(11)
    print("V6_PREFLIGHT=READONLY_READY_FOR_SEPARATE_STAGE")
    print("TELEGRAM_SEND_AUTHORIZED=NO")
    print("PRODUCTION_CHANGED=NO")
else:
    sys.exit(12)
"""

def parts():
    text = SCRIPT.read_text(encoding="utf-8-sig")
    _, sep, rest = text.partition("$remote = @'\n")
    if not sep:
        raise AssertionError("Missing literal POSIX remote command")
    shell, sep, _ = rest.partition("\n'@\n")
    if not sep or not shell.startswith("set -eu\n"):
        raise AssertionError("Invalid POSIX remote command")
    match = re.search(r"python - <<'PY'\n(.*?)\nPY\n?$", shell, re.S)
    if not match:
        raise AssertionError("Missing bounded Python")
    return text, shell + "\n", match.group(1)

class ReadOnlyV6Preflight(unittest.TestCase):
    def test_embedded_python_is_safe_and_compiles(self):
        text, shell, program = parts()
        compile(program, "<V6_PREFLIGHT>", "exec")
        for expect in (
            "valyqon-public-sources:v6-fe4c66bbd553",
            "label=com.docker.compose.service=worker-v6",
            'DATABASE_URL": "sqlite:////app/data/isolated-public-sources.sqlite3"',
            'Path("/app/data").is_mount()',
            "shutil.disk_usage(",
            "536870912",
            "READONLY_READY_FOR_SEPARATE_STAGE",
            "LEGACY_PATCHES_REQUIRED",
            'out("TELEGRAM_SEND_AUTHORIZED", "NO")',
            'out("PRODUCTION_CHANGED", "NO")',
            "stan.StanCommercialPublicSource.fetch",
            "lenobl.LenoblSmallPublicSource.fetch",
        ):
            self.assertIn(expect, text)
        for prohibited in ("docker compose up", "docker restart", "docker build",
                           "sqlite3.connect(", "telegram.send", "open('/app/data",
                           'open("/app/data', "subprocess.run(", "docker rm"):
            self.assertNotIn(prohibited, text)
        self.assertLess(program.index("if any(os.environ.get(key) != value"),
                        program.index("import app.sources.stan_commercial_public"))

    def case(self, name):
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp)
            fake=root/"docker"
            fake.write_text(MOCK, encoding="utf-8")
            fake.chmod(0o755)
            calls=root/"calls"
            env={**os.environ, "PATH": str(root)+os.pathsep+os.environ.get("PATH",""),
                 "V6_FAKE_CASE":name, "V6_FAKE_LOG":str(calls)}
            _, shell, _=parts()
            result=subprocess.run(["sh","-s"],input=shell,text=True,
                                  capture_output=True,env=env,timeout=8)
            items=calls.read_text().splitlines() if calls.exists() else []
            return result,items

    def test_exact_running_service_or_fail_closed_without_docker_exec(self):
        p,calls=self.case("ok")
        self.assertEqual(p.returncode,0, p.stderr)
        self.assertIn("V6_EXACT_WORKER=VERIFIED_UNIQUE_PINNED_IMAGE",p.stdout)
        self.assertEqual(calls.count("exec"),1)
        for bad in ("none","double","bad_image","docker_error"):
            with self.subTest(name=bad):
                p,calls=self.case(bad)
                self.assertEqual(p.returncode,2, p.stdout)
                self.assertEqual(calls.count("exec"),0)
                self.assertIn("PRODUCTION_CHANGED=NO",p.stdout)

if __name__=="__main__":
    unittest.main()
