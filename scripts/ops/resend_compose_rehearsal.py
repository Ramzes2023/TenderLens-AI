"""Offline Compose lifecycle drill. Inputs must be decrypted backup copies, never live paths.

Run on the Docker host; no SMTP credentials or network are needed. Output contains
only stage results. The original production Compose project is never operated on.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


PROBE = r'''
import hashlib,json,os,shutil,sqlite3
from fastapi.testclient import TestClient
from app.api.main import create_app
def rows(path):
 with sqlite3.connect(path) as c:
  return {t:hashlib.sha256(repr(c.execute('select * from "'+t.replace('"','""')+'" order by rowid').fetchall()).encode()).hexdigest() for (t,) in c.execute("select name from sqlite_master where type='table'") if t.startswith(('auth_','organization'))}
baseline=rows('/restore/database.sqlite3')
shutil.copyfile('/restore/database.sqlite3','/tmp/drill.sqlite3')
with TestClient(create_app()) as client:
 assert client.app.state.runtime.auth_service is not None
 assert (client.app.state.runtime.email_sender is not None)==(os.environ['VALYQON_EMAIL_MODE']=='smtp')
 for route in ('/health','/','/login','/forgot-password','/register','/assets/premium.css'):
  assert client.get(route).status_code==200
 assert client.post('/api/v1/auth/register',json={'email':'drill@example.invalid','password':'Offline safe password! 2026'}).status_code==503
assert rows('/tmp/drill.sqlite3')==baseline
with sqlite3.connect('/tmp/drill.sqlite3') as c:
 assert c.execute('pragma integrity_check').fetchall()==[('ok',)]
 assert not c.execute('pragma foreign_key_check').fetchall()
print('PROBE=PASS')
'''


def run(args, data=None):
    result = subprocess.run(args, input=data, text=True, capture_output=True, timeout=180)
    if result.returncode:
        # Docker errors can contain environment values; do not expose them.
        raise RuntimeError('Isolated Docker operation failed')
    return result.stdout


def rehearse(snapshot, image, original_env, parent):
    snapshot = Path(snapshot).resolve(strict=True)
    parent = Path(parent).resolve(strict=True)
    if not image.startswith('sha256:') or len(image) != 71:
        raise ValueError('Exact local image ID required')
    if original_env.get('VALYQON_EMAIL_MODE', 'disabled') != 'disabled' or original_env.get('VALYQON_LEGAL_REQUIRED') != 'true':
        raise ValueError('Original release gates must be closed')
    os.umask(0o077)
    before = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='valyqon-drill-', dir=parent) as directory:
        root = Path(directory)
        # Only a private restored copy can become a container input.
        restore = root / 'restore'
        restore.mkdir()
        (restore / 'database.sqlite3').write_bytes(snapshot.read_bytes())
        env = dict(original_env)
        # Do not propagate credentials, external integrations or inherited env files.
        env = {k: v for k, v in env.items() if k in ('VALYQON_LEGAL_REQUIRED', 'VALYQON_EMAIL_MODE')}
        env.update(DATABASE_URL='sqlite:////tmp/drill.sqlite3', DATA_DIR='/tmp/data', PYTHONDONTWRITEBYTECODE='1', RAG_QDRANT_PATH='/tmp/qdrant', FASTEMBED_CACHE_PATH='/tmp/cache')
        base = {'services': {'api': {'image': image, 'pull_policy': 'never', 'network_mode': 'none', 'read_only': True, 'user': '1000:1000', 'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'], 'pids_limit': 128, 'tmpfs': ['/tmp:rw,nosuid,mode=1777,size=256m'], 'volumes': [str(restore)+':/restore:ro'], 'environment': env, 'entrypoint': ['python', '-c', 'import time; time.sleep(1800)'], 'healthcheck': {'disable': True}, 'restart': 'no'}}}
        candidate = {'services': {'api': {'environment': {'VALYQON_EMAIL_MODE': 'smtp', 'VALYQON_SMTP_HOST': 'smtp.resend.com', 'VALYQON_SMTP_PORT': '465', 'VALYQON_SMTP_FROM': 'VALYQON AI <team@valyqon.dns.army>', 'VALYQON_SMTP_USERNAME': 'resend', 'VALYQON_SMTP_PASSWORD': 're_OFFLINE_ONLY', 'VALYQON_SMTP_SSL': 'true', 'VALYQON_SMTP_STARTTLS': 'false', 'VALYQON_PUBLIC_BASE_URL': 'https://valyqon.duckdns.org'}}}}
        for name, content in [('base.json', base), ('candidate.json', candidate)]:
            (root/name).write_text(json.dumps(content))
        project = root.name
        command = ['docker', 'compose', '--project-name', project, '-f', str(root/'base.json')]
        previous = None
        results = {}
        try:
            for stage in ('original', 'candidate', 'rollback'):
                current = command + (['-f', str(root/'candidate.json')] if stage == 'candidate' else [])
                run(current+['up', '-d', '--no-build', '--pull', 'never'])
                cid = run(current+['ps', '-q', 'api']).strip()
                info = json.loads(run(['docker', 'inspect', cid]))[0]
                assert info['Image'] == image and info['HostConfig']['NetworkMode'] == 'none'
                assert info['HostConfig']['ReadonlyRootfs'] and not info['HostConfig']['PortBindings']
                assert all(m['Source'] == str(restore) and not m['RW'] for m in info['Mounts'] if m['Type'] != 'tmpfs')
                if previous:
                    assert cid != previous
                run(current+['exec', '-T', 'api', 'python', '-'], PROBE)
                results[stage] = 'PASS'
                previous = cid
        finally:
            # No -v: this dedicated project has no named volumes.
            run(command+['down', '--remove-orphans'])
        assert not run(command+['ps', '-aq']).strip()
        assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == before
        results.update(network='none', source_snapshot_unchanged=True, real_email_sent=False, production_cutover=False, cleanup='PASS')
        return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--original-env', required=True, help='Private JSON of original environment')
    parser.add_argument('--work-root', required=True)
    args = parser.parse_args()
    print(json.dumps(rehearse(args.snapshot, args.image, json.loads(Path(args.original_env).read_text()), args.work_root)))
