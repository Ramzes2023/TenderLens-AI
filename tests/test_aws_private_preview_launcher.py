"""Static launcher guard rails; no remote SSH or AWS requests are executed."""
from pathlib import Path

SCRIPT=(Path(__file__).resolve().parents[1]/
        "ops/private_preview/launch_aws_preview.ps1").read_text(encoding="utf-8")


def test_private_launcher_does_not_mutate_main_or_production():
    assert '[switch]$PlanOnly' in SCRIPT
    assert 'valyqon-private-preview' in SCRIPT
    assert '/home/ubuntu/valyqon-personal-preview' in SCRIPT
    assert 'build_safe_archive.py' in SCRIPT
    assert 'StrictHostKeyChecking=yes' in SCRIPT
    assert 'BatchMode=yes' in SCRIPT
    assert 'Get-ValyqonPreviewBashCommand' in SCRIPT
    assert 'source-only.tar.gz' in SCRIPT
    assert 'docker compose down -v' not in SCRIPT
    assert 'docker system prune' not in SCRIPT
    assert 'ssh-keyscan' not in SCRIPT


def test_loopback_and_verified_disabled_billing_before_browser():
    assert '127.0.0.1:18765:127.0.0.1:18765' in SCRIPT
    assert '127.0.0.1:18766:127.0.0.1:18766' in SCRIPT
    assert '0.0.0.0:18765' not in SCRIPT
    assert 'PREVIEW_SERVER_HTTP=VERIFIED' in SCRIPT
    assert 'PAYMENTS_AND_EXTERNAL_SOURCES=DISABLED' in SCRIPT
    assert "states['database'] == 'operational'" in SCRIPT
    assert "states['payments'] == 'not_enabled'" in SCRIPT
    assert '/private-preview/ready' in SCRIPT
    assert 'generate_env.py' in SCRIPT
    assert 'stat -c' in SCRIPT
