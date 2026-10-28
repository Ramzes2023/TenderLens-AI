"""Isolation and failure contracts; no Docker or external communication."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

OPS = Path(__file__).resolve().parents[1]/'scripts/ops'
sys.path.insert(0, str(OPS))
spec = importlib.util.spec_from_file_location('stack_drill', OPS/'resend_stack_rehearsal.py')
drill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drill)
sys.path.remove(str(OPS))

IMAGES = {name: 'sha256:'+'a'*64 for name in ('api', 'caddy', 'guest-sources', 'guest-d9446c0')}
CADDY = '''{\n email {$ACME_EMAIL}\n}\nvalyqon.duckdns.org, {$TENDERLENS_DOMAIN} {
 reverse_proxy api:8000
 reverse_proxy guest-sources:8101
 reverse_proxy guest-d9446c0:8100
}'''


def test_configuration_cannot_use_live_resources_or_credentials(tmp_path):
    config = drill.configuration(tmp_path, IMAGES)
    assert config['networks'] == {'isolated': {'internal': True}}
    assert set(config['services']) == set(drill.SERVICES)
    for service in config['services'].values():
        assert not {'ports', 'env_file', 'build', 'container_name', 'network_mode'} & service.keys()
        assert service['read_only'] and service['cap_drop'] == ['ALL']
        assert list(service['networks']) == ['isolated']
        assert service['pull_policy'] == 'never'
        for mount in service.get('volumes', []):
            assert mount.startswith(str(tmp_path)) and mount.endswith(':ro')
        assert not any(value for key, value in service['environment'].items() if key.endswith(('KEY', 'TOKEN', 'CREDENTIALS', 'PASSWORD')))
    assert config['services']['api']['environment']['VALYQON_LEGAL_REQUIRED'] == 'true'
    text = drill.isolated_caddy(CADDY)
    assert 'local_certs' in text and 'https://drill.invalid:8443 {' in text
    assert '{$ACME_EMAIL}' not in text


@pytest.mark.parametrize('text', [CADDY.replace('api:8000', 'external.example:8000'), CADDY.replace('valyqon.duckdns.org, {$TENDERLENS_DOMAIN}', 'unknown.example')])
def test_unknown_proxy_or_identity_requires_review(text):
    with pytest.raises(ValueError):
        drill.isolated_caddy(text)


@pytest.mark.parametrize('value', ['latest', 'sha256:'+'z'*64, 'sha256:'+'a'*63])
def test_mutable_or_malformed_image_rejected(tmp_path, value):
    with pytest.raises(ValueError):
        drill.configuration(tmp_path, dict(IMAGES, api=value))


def test_startup_failure_cleans_only_private_project(tmp_path, monkeypatch):
    snapshot = tmp_path/'snapshot.sqlite3'
    snapshot.write_bytes(b'snapshot sentinel')
    calls = []
    def run(args, data=None):
        calls.append(args)
        if 'config' in args:
            return json.dumps({'sanitized': True})
        if 'up' in args:
            raise RuntimeError('injected startup failure')
        return ''
    monkeypatch.setattr(drill, 'run', run)
    with pytest.raises(RuntimeError, match='injected'):
        drill.rehearse(snapshot, IMAGES, CADDY, tmp_path)
    assert calls[-1][-2:] == ['down', '--remove-orphans']
    assert all(c[c.index('--project-name')+1].startswith('valyqon-stack-drill-') for c in calls)
    assert all('-v' not in c for c in calls)
    assert snapshot.read_bytes() == b'snapshot sentinel'
    assert list(tmp_path.iterdir()) == [snapshot]
