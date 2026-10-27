"""Execute the exact embedded remote probe with fake I/O; never connect or send."""
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/ops/valyqon_resend_diagnose.ps1'


def run_probe(mode='send', *, early=False, exists=False, sender='team@valyqon.dns.army', permissions=0o600, symlink=False, smtp_error=False):
    code = SOURCE.read_text(encoding='utf-8').split("$remote = @'", 1)[1].split("'@", 1)[0].replace('__MODE__', mode)
    config = '\n'.join(f'{k}={v}' for k, v in {
        'VALYQON_EMAIL_MODE': 'smtp', 'VALYQON_SMTP_HOST': 'smtp.resend.com',
        'VALYQON_SMTP_PORT': '465', 'VALYQON_SMTP_USERNAME': 'resend',
        'VALYQON_SMTP_SSL': 'true', 'VALYQON_SMTP_STARTTLS': 'false',
        'VALYQON_SMTP_FROM': sender, 'VALYQON_PUBLIC_BASE_URL': 'https://valyqon.duckdns.org',
        'VALYQON_SMTP_PASSWORD': 're_OFFLINE_SENTINEL',
    }.items())
    events = []

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 28, 17 if early else 19, tzinfo=timezone.utc)

    class SMTP:
        def __init__(self, *args, **kwargs):
            events.append('connect')
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def login(self, *args):
            if smtp_error:
                raise RuntimeError('re_OFFLINE_SENTINEL')
        def send_message(self, message):
            events.append('send')
            assert message['From'] == 'VALYQON AI <team@valyqon.dns.army>'
            assert message.get_content().strip() == 'hello world'
            return {}

    def marker(path, flags, mode):
        events.append('marker')
        assert flags == os.O_CREAT | os.O_EXCL | os.O_WRONLY
        assert mode == 0o600
        if exists:
            raise FileExistsError()
        return 99

    class MarkerFile:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def write(self, value):
            pass

    with patch('pathlib.Path.lstat', return_value=SimpleNamespace(st_mode=(stat.S_IFLNK if symlink else stat.S_IFREG) | permissions, st_uid=1000)), patch('pathlib.Path.read_text', return_value=config), patch('os.getuid', create=True, return_value=1000), patch('os.open', side_effect=marker), patch('os.fdopen', return_value=MarkerFile()), patch('smtplib.SMTP_SSL', SMTP), patch('datetime.datetime', Clock):
        try:
            exec(compile(code, str(SOURCE), 'exec'), {})
            status = 0
        except SystemExit as exc:
            status = exc.code
    return status, events


def test_early_gate_neither_spends_marker_nor_connects():
    assert run_probe(early=True) == (3, [])


def test_existing_marker_never_connects():
    assert run_probe(exists=True) == (4, ['marker'])


def test_audit_never_spends_marker_or_connects():
    assert run_probe('audit') == (0, [])


def test_eligible_one_shot_claims_marker_before_send():
    assert run_probe() == (0, ['marker', 'connect', 'send'])


@pytest.mark.parametrize('options', [{'sender': 'owner@gmail.com'}, {'permissions': 0o644}, {'symlink': True}])
def test_invalid_sender_or_secret_refused_before_marker(options):
    assert run_probe(**options) == (2, [])


def test_smtp_failure_does_not_retry_or_expose_secret(capsys):
    assert run_probe(smtp_error=True) == (2, ['marker', 'connect'])
    assert 're_OFFLINE_SENTINEL' not in capsys.readouterr().out
