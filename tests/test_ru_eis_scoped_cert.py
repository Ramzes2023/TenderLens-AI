"""EIS pinned-root configuration and refusal to trust arbitrary certificates."""
from pathlib import Path

import pytest

from scripts.ru_eis_pinned_tls_probe import ROOT_SHA256, verify_root
from scripts.ru_public_live_smoke import _settings


def test_pinned_root_fingerprint_is_full_sha256():
    assert len(ROOT_SHA256) == 64
    assert all(ch in "0123456789abcdef" for ch in ROOT_SHA256)


def test_scoped_context_loads_real_verified_root_without_system_install():
    import ssl
    from scripts.ru_eis_pinned_tls_probe import pinned_ssl_context

    root = Path(__file__).resolve().parents[1] / "russian_trusted_root_ca_pem.crt"
    context = pinned_ssl_context(root)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert context.cert_store_stats()["x509_ca"] == 1


def test_scoped_context_rejects_changed_root(tmp_path):
    from scripts.ru_eis_pinned_tls_probe import pinned_ssl_context

    root = tmp_path / "untrusted.pem"
    root.write_bytes(b"untrusted" * 100)
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        pinned_ssl_context(root)


@pytest.mark.parametrize("untrusted", [b"", b"not-a-cert", b"Z" * 1000, b"P" * 65537],
                         ids=["empty", "invalid-text", "invalid-der", "oversized"])
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


def test_verified_der_and_pem_transports_resolve_to_same_pinned_root(monkeypatch):
    import hashlib
    import ssl
    from scripts import ru_eis_pinned_tls_probe as probe
    from app.sources import eis_pinned_ca as trust

    # Synthetic bytes test format normalization only, not real X.509 trust.
    der = bytes([0x30, 0x82]) + bytes([0x42]) * 512
    # Production is the sole authoritative verifier after Docker refactor.
    # This is synthetic DER formatting coverage, NOT an alternate trusted CA.
    monkeypatch.setattr(trust, "ROOT_SHA256", hashlib.sha256(der).hexdigest())
    pem = ssl.DER_cert_to_PEM_cert(der)

    assert probe.verify_root(der) == pem
    assert probe.verify_root(pem.encode("ascii")) == pem
    assert probe.verify_root(("\r\n" + pem + "\r\n").encode("ascii")) == pem


def test_multi_certificate_pem_and_wrong_pin_fail_closed(monkeypatch):
    import hashlib
    import ssl
    from scripts import ru_eis_pinned_tls_probe as probe
    from app.sources import eis_pinned_ca as trust

    der = bytes([0x30, 0x82]) + bytes([0x43]) * 512
    pem = ssl.DER_cert_to_PEM_cert(der)
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        probe.verify_root(pem.encode("ascii"))
    # Production is the sole authoritative verifier after Docker refactor.
    # This is synthetic DER formatting coverage, NOT an alternate trusted CA.
    monkeypatch.setattr(trust, "ROOT_SHA256", hashlib.sha256(der).hexdigest())
    with pytest.raises(ValueError, match="PEM certificate"):
        probe.verify_root((pem + pem).encode("ascii"))
