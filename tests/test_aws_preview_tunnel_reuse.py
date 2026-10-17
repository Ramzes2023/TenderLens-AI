"""Private preview update preserves existing tunnel if explicitly requested."""
from pathlib import Path


def test_reuse_requires_explicit_switch_and_exact_ssh_ownership():
    s=(Path(__file__).resolve().parents[1]/
       "ops/private_preview/launch_aws_preview.ps1").read_text(encoding="utf-8")
    assert "[switch]$ReuseExistingTunnel" in s
    assert "if ($ReuseExistingTunnel)" in s
    assert "$owner.Name -ne 'ssh.exe'" in s
    assert "OwningProcess -ne $listeners[1].OwningProcess" in s
    assert "127.0.0.1:18765:127.0.0.1:18765" in s
    assert "127.0.0.1:18766:127.0.0.1:18766" in s
    assert "'/private-preview/ready'" in s
    assert "external_integrations -ne 'disabled'" in s
    assert "REUSED_TUNNEL_PID" in s
    assert "docker system prune" not in s
    assert "Stop-Process -Id $listeners" not in s
