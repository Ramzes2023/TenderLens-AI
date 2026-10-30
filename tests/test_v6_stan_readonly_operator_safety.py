"""Offline-only safety tests for pinned V6 STAN listing/detail probe."""
import os
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "VALYQON-V6-STAN-EXISTING-IMAGE-READONLY.ps1"
MOCK = """#!/usr/bin/env python3
import os
import sys
p=sys.argv[1:]
with open(os.environ["FAKE_LOG"],"a") as f: f.write(p[0]+"\\\\n")
case=os.environ["FAKE_CASE"]
if case=="docker_error": sys.exit(9)
if p[0]=="ps":
    if ("label=com.docker.compose.project=valyqon-public-sources" not in p
            or "label=com.docker.compose.service=worker-v6" not in p): sys.exit(11)
    print({"valid":"v6aaa", "multiple":"v6aaa\\nv6bbb", "wrong_image":"v6aaa"}.get(case,""))
elif p[0]=="inspect":
    print("valyqon-public-sources:v6-wrong" if case=="wrong_image"
          else "valyqon-public-sources:v6-fe4c66bbd553")
elif p[0]=="exec":
    raw=sys.stdin.read()
    if "max_requests=3" not in raw or "stantorgi.ru" not in raw:
        sys.exit(12)
    print("V6_STAN_STATUS=READONLY_DIAGNOSED")
    print("TELEGRAM_SEND_AUTHORIZED=NO")
    print("PRODUCTION_CHANGED=NO")
else: sys.exit(13)
"""

def parsed():
    raw=SCRIPT.read_text(encoding="utf-8-sig")
    _,sep,rest=raw.partition("$remote = @'\n")
    if not sep: raise AssertionError("Missing operator heredoc")
    shell,sep,_=rest.partition("\n'@\n")
    if not sep or not shell.startswith("set -eu\n"):
        raise AssertionError("Invalid bounded shell")
    match=re.search(r"python - <<'PY'\n(.*?)\nPY\n?$",shell,re.S)
    if match is None: raise AssertionError("Missing bound Python")
    return raw,shell+"\n",match.group(1)

class STANReadOnlySafety(unittest.TestCase):
    def test_embedded_parser_and_strict_bounds(self):
        raw,shell,python=parsed()
        compile(python,"<STAN_READONLY_OFFLINE>","exec")
        for expected in ("worker-v6", "v6-fe4c66bbd553", "max_requests=3",
                         "parse_list", "independently_verified_commercial_metadata",
                         'eligible_published_deadline', 'trust_env=False',
                         'follow_redirects=False', 'worker_sql_verified": False',
                         '"telegram_sent": False'):
            self.assertIn(expected,raw)
        for forbidden in ("docker restart", "docker compose up", "telegram.send",
                          "sqlite3.connect(", "subprocess.run(", "data/isolated-public-sources.sqlite3?mode=rw"):
            self.assertNotIn(forbidden,raw)
        self.assertIn("V6_STAN_CANARY=",raw)

    def run_case(self,case):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder)
            fake=root/"docker"
            fake.write_text(MOCK,encoding="utf-8")
            fake.chmod(0o755)
            log=root/"calls"
            env={**os.environ, "PATH":str(root)+os.pathsep+os.environ.get("PATH",""),
                 "FAKE_LOG":str(log), "FAKE_CASE":case}
            _,shell,_=parsed()
            p=subprocess.run(["sh","-s"],input=shell,env=env,
                             text=True,capture_output=True,timeout=6,check=False)
            calls=log.read_text().splitlines() if log.exists() else []
            return p.returncode,p.stdout,calls

    def test_unique_pinned_v6_and_fail_closed_variants(self):
        code,out,calls=self.run_case("valid")
        self.assertEqual(code,0)
        self.assertIn("V6_EXACT_WORKER=VERIFIED_UNIQUE_PINNED_IMAGE",out)
        self.assertEqual(calls.count("exec"),1)
        for case in ("multiple", "missing", "wrong_image", "docker_error"):
            with self.subTest(case=case):
                code,out,calls=self.run_case(case)
                self.assertEqual(code,2)
                self.assertIn("PRODUCTION_CHANGED=NO",out)
                self.assertEqual(calls.count("exec"),0)

if __name__=="__main__":
    unittest.main()
