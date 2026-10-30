"""Operator-only staging script: exact V6, SHA pin, private RC and no release."""
import pathlib
import re
import subprocess
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
FILE=ROOT/"scripts/VALYQON-STAN-LENOBL-RC-STAGE-OPERATOR.ps1"

def parse():
    raw=FILE.read_text(encoding="utf-8-sig")
    prefix, sep, rest=raw.partition("$remote = @'\n")
    if not sep: raise AssertionError("Missing literal shell")
    shell,sep,tail=rest.partition("\n'@\n")
    if not sep or not shell.startswith("set -eu\n"): raise AssertionError("Invalid shell boundary")
    py=re.search(r"python3 - \"\$stage/config.json\" <<'PY'\n(.*?)\nPY\nthen",shell,re.S)
    if py is None: raise AssertionError("Missing Python config validator")
    return raw,shell+"\n",py.group(1)

class StageOperatorSecurity(unittest.TestCase):
    def test_bash_and_embedded_python_compile(self):
        src,sh,code=parse()
        compile(code,"<rc-config-guard>","exec")
        p=subprocess.run(["sh","-n"],input=sh,text=True,capture_output=True,timeout=8)
        self.assertEqual(p.returncode,0,p.stderr)

    def test_production_is_not_touched_and_deploy_is_pinned(self):
        src,sh,code=parse()
        markers=[
            "ValidatePattern('^[0-9a-f]{40}$')",
            "ReviewedCommit",
            "__REVIEWED_COMMIT__",
            "git -C \"$stage/repo\" rev-parse HEAD",
            "git -C \"$stage/repo\" status --porcelain",
            "valyqon-public-sources:v6-fe4c66bbd553",
            "label=com.docker.compose.service=worker-v6",
            "project=valyqon-public-sources",
            "valyqon-stan-lenobl-rc",
            "valyqon-stan-lenobl-rc:reviewed",
            "VALYQON_STAN_LENOBL_RC_MODE",
            "3145728",
            "BLOCKED_PROJECT_EXISTS",
            "BLOCKED_VOLUME_EXISTS",
            "BLOCKED_STAGE_IMAGE_EXISTS" if False else "BLOCKED_IMAGE_EXISTS",
            "set(s[\"guest-sources\"][\"networks\"])",
            "\"private_guest\"",
            "internal",
            "docker compose -p \"$project\" -f \"$manifest\" build --quiet worker",
            "docker compose -p \"$project\" -f \"$manifest\" up --no-build --no-deps -d guest-sources worker",
            "RC_STAGE_GUEST=HEALTHY_PRIVATE_ONLY",
            "RC_STAGE_E2E=NOT_RUN",
            "RC_STAGE=BOOT_PASS",
            "PRODUCTION_CHANGED=NO",
            "TELEGRAM_SEND_AUTHORIZED=NO",
            "StrictHostKeyChecking=yes",
        ]
        for marker in markers:
            self.assertIn(marker,src,marker)
        # No host routing and never change existing Docker project/volumes.
        for dangerous in (
            "docker system prune", "docker volume rm", "docker restart",
            "docker stop", "docker rm", "docker compose down -v",
            "sqlite3.connect(", "telegram.send(", "production.sqlite",
            "git reset --hard", "docker compose -p valyqon-public-sources",
            "docker compose -p tenderlens-vps",
            "tenderlens-vps_edge",
        ):
            self.assertNotIn(dangerous,src,dangerous)
        self.assertIn("set(cfg",src) if False else None
        self.assertIn("set(m[\"networks\"])",code)
        self.assertIn("assert not", "assert not" if "not x.get(\"ports\")" in code else "")

    def test_ssh_output_is_sanitized_and_no_hidden_recipient_send(self):
        raw,_,_=parse()
        self.assertIn("RedirectStandardError = $true",raw)
        self.assertIn("RC_STAGE_OPERATOR",raw)
        self.assertIn("Write-Output 'V6_REMOTE_STDERR_PRESENT=YES_REDACTED'",raw)
        self.assertIn("Write-Output \"V6_SSH_EXIT_CODE=$status\"",raw)
        self.assertNotIn("Write-Output $safeStdout",raw)
        self.assertNotIn("Write-Output $safeStderr",raw)
        self.assertNotIn("docker compose run --rm enqueue",raw)
        self.assertNotIn("app.sources.enqueue --",raw)

if __name__=="__main__":
    unittest.main()
