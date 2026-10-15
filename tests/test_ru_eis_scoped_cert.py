"""EIS pinned-root configuration and refusal to trust arbitrary certificates."""
from pathlib import Path

import pytest

from scripts.ru_eis_pinned_tls_probe import ROOT_SHA256, verify_root
from scripts.ru_public_live_smoke import _settings


def test_pinned_root_fingerprint_is_full_sha256():
    assert len(ROOT_SHA256) == 64
    assert all(ch in "0123456789abcdef" for ch in ROOT_SHA256)


@pytest.mark.parametrize("untrusted", [b"", b"not-a-cert", b"Z" * 1000, b"P" * 65537])
def test_untrusted_input_cannot_enable_eis_tls(untrusted):
    with pytest.raises(ValueError):
        verify_root(untrusted)


def test_scoped_bundle_does_not_enable_os_trust_or_production(monkeypatch, tmp_path):
    root = tmp_path / "eis-only-root.pem"
    root.write_text("isolated fixture; not trusted by Python TLS", encoding="ascii")
    monkeypatch.setenv("VALYQON_RU_EIS_CA_CERT", str(root))
    settings = _settings()
    assert settings.ca_bundle_file == root.resolve()
    assert not settings.eis_system_trust_enabled
    assert not settings.enabled
    assert settings.eis_direct_enabled
    assert settings.eis_223_enabled


def test_missing_scoped_file_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("VALYQON_RU_EIS_CA_CERT", str(tmp_path / "missing.pem"))
    with pytest.raises(ValueError):
        _settings()
