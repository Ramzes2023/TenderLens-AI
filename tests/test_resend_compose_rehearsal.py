"""Failure-path checks for the offline operational drill; no Docker or sockets."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('drill', Path(__file__).resolve().parents[1] / 'scripts/ops/resend_compose_rehearsal.py')
drill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drill)


def test_failure_cleans_only_dedicated_project_and_never_inherits_secrets(tmp_path, monkeypatch):
    snapshot = tmp_path / 'snapshot.sqlite3'
    snapshot.write_bytes(b'isolated snapshot sentinel')
    commands = []

    def fake_run(args, data=None):
        commands.append(args)
        if 'up' in args:
            base = json.loads(Path(args[args.index('-f')+1]).read_text())
            service = base['services']['api']
            assert service['network_mode'] == 'none'
            assert service['read_only'] is True
            assert 'ports' not in service and 'env_file' not in service
            assert 'SECRET_SENTINEL' not in json.dumps(base)
            assert service['volumes'][0].endswith(':/restore:ro')
            raise RuntimeError('injected startup failure')
        return ''

    monkeypatch.setattr(drill, 'run', fake_run)
    with pytest.raises(RuntimeError, match='injected'):
        drill.rehearse(snapshot, 'sha256:'+'a'*64, {'VALYQON_EMAIL_MODE':'disabled', 'VALYQON_LEGAL_REQUIRED':'true', 'API_KEY':'SECRET_SENTINEL'}, tmp_path)
    assert commands[-1][-2:] == ['down', '--remove-orphans']
    assert '-v' not in commands[-1]
    assert all(c[c.index('--project-name')+1].startswith('valyqon-drill-') for c in commands)
    assert snapshot.read_bytes() == b'isolated snapshot sentinel'
    assert list(tmp_path.iterdir()) == [snapshot]


@pytest.mark.parametrize('image,env', [('latest', {'VALYQON_LEGAL_REQUIRED':'true'}), ('sha256:'+'a'*64, {'VALYQON_EMAIL_MODE':'smtp', 'VALYQON_LEGAL_REQUIRED':'true'}), ('sha256:'+'a'*64, {'VALYQON_LEGAL_REQUIRED':'false'})])
def test_unsafe_inputs_rejected_before_docker(tmp_path, monkeypatch, image, env):
    snapshot = tmp_path/'copy.sqlite3'
    snapshot.touch()
    monkeypatch.setattr(drill, 'run', lambda *a: pytest.fail('Docker must not be reached'))
    with pytest.raises(ValueError):
        drill.rehearse(snapshot, image, env, tmp_path)
