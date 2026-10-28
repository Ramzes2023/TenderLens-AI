"""Read-only exact Compose preflight. Never starts containers or sends email.

Run on the deployment host. Resolved environments stay in memory; only fixed
status categories and deployment file names may be published.
"""
import copy
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile


MAIL_KEYS = {
    'VALYQON_EMAIL_MODE', 'VALYQON_SMTP_HOST', 'VALYQON_SMTP_PORT',
    'VALYQON_SMTP_USERNAME', 'VALYQON_SMTP_PASSWORD', 'VALYQON_SMTP_FROM',
    'VALYQON_SMTP_SSL', 'VALYQON_SMTP_STARTTLS', 'VALYQON_PUBLIC_BASE_URL',
}



def sender_link_host_status(mail_env):
    """Classify the conservative From-domain vs account-link hostname check.

    Domain-name similarity does NOT prove DNS ownership or Gmail acceptance.
    A different hostname warrants an operator review, not a DMARC diagnosis.
    No secrets or recipient data are returned.
    """
    from email.utils import parseaddr
    from urllib.parse import urlsplit

    address = parseaddr(str(mail_env.get('VALYQON_SMTP_FROM', '')))[1]
    if address.count('@') != 1:
        return 'UNKNOWN'
    from_domain = address.rsplit('@', 1)[1].lower().rstrip('.')
    try:
        target = urlsplit(str(mail_env.get('VALYQON_PUBLIC_BASE_URL', '')))
        link_host = (target.hostname or '').lower().rstrip('.')
    except ValueError:
        return 'UNKNOWN'
    if target.scheme != 'https' or not link_host or not from_domain:
        return 'UNKNOWN'
    if from_domain == link_host:
        return 'EXACT_MATCH'
    return 'DIFFERENT_HOST'


def validate_diff(original, candidate):
    """Reject every change outside the API's explicit mail settings."""
    left, right = copy.deepcopy(original), copy.deepcopy(candidate)
    a = left['services']['api']['environment']
    b = right['services']['api']['environment']
    assert a.get('VALYQON_EMAIL_MODE', 'disabled') == 'disabled'
    assert a.get('VALYQON_LEGAL_REQUIRED') == b.get('VALYQON_LEGAL_REQUIRED') == 'true'
    expected = dict(VALYQON_EMAIL_MODE='smtp', VALYQON_SMTP_HOST='smtp.resend.com',
                    VALYQON_SMTP_PORT='465', VALYQON_SMTP_USERNAME='resend',
                    VALYQON_SMTP_SSL='true', VALYQON_SMTP_STARTTLS='false',
                    VALYQON_PUBLIC_BASE_URL='https://valyqon.duckdns.org')
    assert all(b.get(k) == v for k, v in expected.items())
    from email.utils import parseaddr
    assert parseaddr(b['VALYQON_SMTP_FROM'])[1] in {
        'noreply@valyqon.dns.army', 'team@valyqon.dns.army'}
    assert b.get('VALYQON_SMTP_PASSWORD', '').startswith('re_')
    for env in (a, b):
        for key in MAIL_KEYS:
            env.pop(key, None)
    assert left == right, 'Non-mail configuration drift'


def run(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError('Read-only deployment query failed')
    return result.stdout


def inspect(name):
    return json.loads(run(['docker', 'inspect', name]))[0]


def preflight():
    before = inspect('tenderlens-vps-api-1')
    proxy = inspect('tenderlens-vps-caddy-1')
    labels = before['Config']['Labels']
    files = labels['com.docker.compose.project.config_files'].split(',')
    envfiles = labels['com.docker.compose.project.environment_file'].split(',')
    working = labels['com.docker.compose.project.working_dir']
    assert working == '/opt/tenderlens'
    assert all(Path(f).parent == Path(working) and Path(f).is_file() for f in files + envfiles)
    secret = Path('/home/ubuntu/.config/valyqon/resend.env')
    info = secret.lstat()
    assert stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600 and info.st_uid == os.getuid()
    cfg = {}
    for line in secret.read_text(encoding='utf-8-sig').splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            k, sep, v = line.partition('=')
            if sep:
                cfg[k.strip()] = v.strip().strip('"')
    # Do not import unrelated settings from the protected file into the candidate.
    assert MAIL_KEYS <= cfg.keys()
    command = ['docker', 'compose', '--project-directory', working,
               '--project-name', labels['com.docker.compose.project']]
    for f in envfiles:
        command += ['--env-file', f]
    for f in files:
        command += ['-f', f]
    original = json.loads(run(command + ['config', '--format', 'json']))
    with tempfile.TemporaryDirectory(prefix='valyqon-preflight-') as directory:
        overlay = Path(directory) / 'candidate.json'
        overlay.write_text(json.dumps({'services': {'api': {'environment': {
            k: cfg[k].replace('$', '$$') for k in MAIL_KEYS}}}}))
        os.chmod(overlay, 0o600)
        candidate = json.loads(run(command + ['-f', str(overlay), 'config', '--format', 'json']))
    validate_diff(original, candidate)
    link_host_status = sender_link_host_status(candidate['services']['api']['environment'])
    live = dict(v.split('=', 1) for v in before['Config']['Env'])
    assert live.get('VALYQON_EMAIL_MODE', 'disabled') == 'disabled'
    assert live.get('VALYQON_LEGAL_REQUIRED') == 'true'
    resolved = original['services']['api']
    assert all(live.get(k) == str(v) for k, v in resolved['environment'].items())
    image = json.loads(run(['docker', 'image', 'inspect', resolved['image']]))[0]
    assert image['Id'] == before['Image']
    for mount in before['Mounts']:
        if mount['Type'] == 'volume':
            volume = json.loads(run(['docker', 'volume', 'inspect', mount['Name']]))[0]
            assert volume['Mountpoint'] == mount['Source']
    assert json.loads(run(command + ['config', '--format', 'json'])) == original
    for name, saved in [('tenderlens-vps-api-1', before), ('tenderlens-vps-caddy-1', proxy)]:
        now = inspect(name)
        assert all(now[k] == saved[k] for k in ('Id', 'Image', 'Mounts'))
        assert now['State']['StartedAt'] == saved['State']['StartedAt']
    return dict(exact_ordered_compose='PASS', env_precedence='PASS',
                api_mail_only_diff='PASS', original_image_available='PASS',
                volume_identity='PASS', original_config_return='PASS',
                live_container_identity='PASS', live_email_mode='disabled',
                legal_required=True, email_sent=False, production_changed=False,
                compose_files=[Path(f).name for f in files],
                live_cutover_rehearsed=False,
                sender_link_host_alignment=link_host_status,
                sender_link_review_required=(link_host_status != 'EXACT_MATCH'),
                recipient_delivery_verified=False,
                production_mail_release_authorized=False)


if __name__ == '__main__':
    try:
        print(json.dumps(preflight()))
    except Exception as exc:
        # No exception text, Docker stderr or resolved secrets in public output.
        print(json.dumps({'preflight': 'FAIL', 'error_class': type(exc).__name__}))
        raise SystemExit(1)
