"""Offline runtime-stack rehearsal; never operates on a production Compose project.

Uses restored SQLite input and exact locally available images. No real credentials,
published ports, live volumes, public ACME, external networks or email operations.
The caller captures live metadata read-only and supplies only the four image IDs
and Caddyfile text. This is a sanitized rehearsal, not a production cutover.
"""
import hashlib
import json
from pathlib import Path
import re
import tempfile

from resend_compose_rehearsal import run


SERVICES = ('api', 'caddy', 'guest-sources', 'guest-d9446c0', 'worker', 'scheduler')
ENV = {
    'PYTHON_DOTENV_DISABLED': '1', 'PYTHONDONTWRITEBYTECODE': '1',
    'APP_ENV': 'development', 'VALYQON_EMAIL_MODE': 'disabled',
    'VALYQON_LEGAL_REQUIRED': 'true', 'VALYQON_PUBLIC_AI_ENABLED': 'false',
    'VALYQON_AI_FALLBACK_ENABLED': 'false', 'MONITORING_ENABLED': 'false',
    'VALYQON_DEADLINE_ALERTS_ENABLED': 'false', 'RAG_ENABLED': 'false',
    'VALYQON_RU_BACKGROUND_CATALOG_ENABLED': 'false',
    'DATABASE_URL': 'sqlite:////tmp/drill.sqlite3', 'DATA_DIR': '/tmp/data',
    'RAG_QDRANT_PATH': '/tmp/qdrant', 'FASTEMBED_CACHE_PATH': '/tmp/cache',
    'API_HOST': '0.0.0.0', 'API_PORT': '8000', 'API_RELOAD': 'false',
    'EIS_RSS_URLS': '', 'OUTBOUND_PROXY_URL': '', 'TELEGRAM_BOT_TOKEN': '',
    'GIGACHAT_CREDENTIALS': '', 'GROQ_API_KEY': '',
    'VALYQON_PUBLIC_ANALYTICS_MODE': 'demo',
    'VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED': 'true',
}
SMTP = {
    'VALYQON_EMAIL_MODE': 'smtp', 'VALYQON_SMTP_HOST': 'smtp.resend.com',
    'VALYQON_SMTP_PORT': '465', 'VALYQON_SMTP_FROM': 'VALYQON AI <team@valyqon.dns.army>',
    'VALYQON_SMTP_USERNAME': 'resend', 'VALYQON_SMTP_PASSWORD': 're_OFFLINE_ONLY',
    'VALYQON_SMTP_SSL': 'true', 'VALYQON_SMTP_STARTTLS': 'false',
    'VALYQON_PUBLIC_BASE_URL': 'https://valyqon.duckdns.org',
}
BOOT = "import shutil,os; shutil.copyfile('/restore/database.sqlite3','/tmp/drill.sqlite3'); os.execvp('python',['python','-m','app.api'])"
CHECK = r'''
import hashlib,json,sqlite3,ssl,time,urllib.request,urllib.error
def request(path, data=None):
 req=urllib.request.Request('https://drill.invalid:8443'+path,data=data,headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,context=ssl._create_unverified_context(),timeout=5) as r:
   return r.status,r.headers,r.read()
 except urllib.error.HTTPError as e:return e.code,e.headers,e.read()
for attempt in range(60):
 try:
  assert request('/health')[0]==200
  break
 except Exception:time.sleep(1)
else:raise RuntimeError('isolated HTTPS readiness timeout')
for route in ('/health','/','/login','/forgot-password','/register','/assets/premium.css'):
 status,headers,body=request(route)
 assert status==200,(route,status)
 assert headers['X-Content-Type-Options']=='nosniff'
assert request('/api/v1/auth/register',b'{"email":"drill@example.invalid","password":"Offline safe password! 2026"}')[0]==503
assert request('/api/v1/public/opportunities')[0]==200
# Disabled AI must fail closed through its real upstream, never call a provider.
assert request('/api/v1/public/help/ask',b'{"question":"How does this work?"}')[0] in (403,422,503)
def rows(path):
 with sqlite3.connect(path) as c:
  return {t:hashlib.sha256(repr(c.execute('select * from "'+t.replace('"','""')+'" order by rowid').fetchall()).encode()).hexdigest() for (t,) in c.execute("select name from sqlite_master where type='table'") if t.startswith(('auth_','organization'))}
assert rows('/tmp/drill.sqlite3')==rows('/restore/database.sqlite3')
with sqlite3.connect('/tmp/drill.sqlite3') as c:
 assert c.execute('pragma integrity_check').fetchall()==[('ok',)]
 assert not c.execute('pragma foreign_key_check').fetchall()
from app.auth.email_delivery import load_email_sender_from_env
import os
assert (load_email_sender_from_env() is not None)==(os.environ['VALYQON_EMAIL_MODE']=='smtp')
print('HTTPS_ROUTES_LEGAL_UPSTREAMS_SQLITE=PASS')
'''


def isolated_caddy(text):
    """Keep reviewed routing/headers; replace identity and public ACME locally."""
    if text.count('valyqon.duckdns.org, {$TENDERLENS_DOMAIN} {') != 1:
        raise ValueError('Unrecognized Caddy site; review routing before running')
    proxies = re.findall(r'(?m)^\s*reverse_proxy\s+([^\s]+)\s*$', text)
    if sorted(proxies) != sorted(['api:8000', 'guest-sources:8101', 'guest-d9446c0:8100']):
        raise ValueError('Unrecognized Caddy upstreams')
    text = text.replace('email {$ACME_EMAIL}', 'auto_https disable_redirects\n\tlocal_certs')
    return text.replace('valyqon.duckdns.org, {$TENDERLENS_DOMAIN} {', 'https://drill.invalid:8443 {')


def configuration(root, images):
    if set(images) != {'api', 'caddy', 'guest-sources', 'guest-d9446c0'}:
        raise ValueError('Four exact runtime images required')
    if any(not re.fullmatch(r'sha256:[0-9a-f]{64}', value) for value in images.values()):
        raise ValueError('Exact local image IDs required')
    services = {}
    for name in SERVICES:
        image = images.get(name, images['guest-sources'])
        services[name] = {
            'image': image, 'pull_policy': 'never', 'restart': 'no',
            'read_only': True, 'cap_drop': ['ALL'],
            'security_opt': ['no-new-privileges:true'], 'pids_limit': 96,
            'mem_limit': '512m', 'networks': ['isolated'],
            'tmpfs': ['/tmp:rw,nosuid,mode=1777,size=256m'],
            'healthcheck': {'disable': True},
            'environment': dict(ENV),
        }
    services['api'].update(
        user='1000:1000', entrypoint=['python', '-c', BOOT],
        volumes=[str(root/'restore')+':/restore:ro'])
    services['caddy'].update(
        # The official binary has cap_net_bind_service set; its execution needs
        # that capability in the bounding set even when listening on port 8443.
        cap_add=['NET_BIND_SERVICE'],
        networks={'isolated': {'aliases': ['drill.invalid']}},
        environment={}, entrypoint=['caddy'],
        command=['run', '--config', '/etc/caddy/Caddyfile', '--adapter', 'caddyfile'],
        volumes=[str(root/'Caddyfile')+':/etc/caddy/Caddyfile:ro'],
        tmpfs=['/tmp:rw,nosuid,mode=1777,size=16m', '/data:rw,nosuid,size=16m', '/config:rw,nosuid,size=16m'])
    for name, module, port in [
        ('guest-sources', 'isolated_public_sources', '8101'),
        ('guest-d9446c0', 'isolated_guest_ai', '8100'),
    ]:
        services[name]['entrypoint'] = ['uvicorn', 'app.api.'+module+':app', '--host', '0.0.0.0', '--port', port]
    services['worker']['entrypoint'] = ['python', '-m', 'app.jobs.worker', '--connectors']
    services['scheduler']['entrypoint'] = ['python', '-m', 'app.sources.isolated_public_scheduler']
    for name in ('guest-sources', 'worker', 'scheduler'):
        services[name]['environment'].update(
            DATABASE_URL='sqlite:////app/data/isolated-public-sources.sqlite3',
            DATA_DIR='/app/data', MIKROTON_TENDER_ENABLED='true',
            STAN_COMMERCIAL_PUBLIC_ENABLED='true')
        # Independent empty stores prevent replaying a production job queue or
        # allowing the scheduler's jobs to reach the worker during this drill.
        services[name]['tmpfs'].append('/app/data:rw,nosuid,mode=1777,size=64m')
    return {'services': services, 'networks': {'isolated': {'internal': True}}}


def rehearse(snapshot, images, caddyfile, parent):
    snapshot = Path(snapshot).resolve(strict=True)
    before = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='valyqon-stack-drill-', dir=parent) as directory:
        root = Path(directory)
        (root/'restore').mkdir()
        (root/'restore/database.sqlite3').write_bytes(snapshot.read_bytes())
        (root/'Caddyfile').write_text(isolated_caddy(caddyfile))
        # Caddy runs as root without DAC_OVERRIDE; allow reading this sanitized
        # file across the bind mount. The parent directory remains private.
        (root/'Caddyfile').chmod(0o644)
        base = configuration(root, images)
        (root/'base.json').write_text(json.dumps(base))
        (root/'candidate.json').write_text(json.dumps({'services': {'api': {'environment': SMTP}}}))
        command = ['docker', 'compose', '--project-name', root.name, '-f', str(root/'base.json')]
        results, original_config, previous_ids = {}, None, None
        try:
            for stage in ('original', 'candidate', 'rollback'):
                current = command + (['-f', str(root/'candidate.json')] if stage == 'candidate' else [])
                resolved = json.loads(run(current+['config', '--format', 'json']))
                if stage == 'original':
                    original_config = resolved
                if stage == 'rollback' and resolved != original_config:
                    raise RuntimeError('Rollback configuration mismatch')
                run(current+['up', '-d', '--force-recreate', '--no-build', '--pull', 'never'])
                ids = {}
                for name in SERVICES:
                    cid = run(current+['ps', '-q', name]).strip()
                    if not cid:
                        raise RuntimeError('Isolated service exited: '+name)
                    ids[name] = cid
                    info = json.loads(run(['docker', 'inspect', cid]))[0]
                    assert info['Image'] == base['services'][name]['image']
                    assert info['HostConfig']['ReadonlyRootfs'] and not info['HostConfig']['PortBindings']
                    assert info['State']['Running']
                    assert all(m['Type'] == 'tmpfs' or (m['Type'] == 'bind' and Path(m['Source']).is_relative_to(root) and not m['RW']) for m in info['Mounts'])
                    nets = info['NetworkSettings']['Networks']
                    assert len(nets) == 1
                    net = json.loads(run(['docker', 'network', 'inspect', next(iter(nets))]))[0]
                    assert net['Internal'] and net['Labels']['com.docker.compose.project'] == root.name
                if previous_ids:
                    assert all(ids[n] != previous_ids[n] for n in SERVICES)
                run(current+['exec', '-T', 'api', 'python', '-'], CHECK)
                # Recheck after probes to catch workers that exit during startup.
                for cid in ids.values():
                    assert json.loads(run(['docker', 'inspect', cid]))[0]['State']['Running']
                results[stage] = 'PASS'
                previous_ids = ids
        finally:
            run(command+['down', '--remove-orphans'])
        assert not run(command+['ps', '-aq']).strip()
        assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == before
        results.update(cleanup='PASS', services=list(SERVICES), real_email_sent=False,
                       production_cutover=False, source_snapshot_unchanged=True,
                       rollback_resolved_config_equal=True, public_acme=False)
        return results
