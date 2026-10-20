"""Fingerprint-pinned, source-scoped root trust for Russian EIS 44-FZ.

Application module is shipped inside the runtime Docker image (unlike scripts/).
Never modifies system trust, downloads roots, disables TLS or trusts user CA
without matching the independently documented canonical DER SHA-256.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import ssl

ROOT_SHA256 = "d26d2d0231b7c39f92cc738512ba54103519e4405d68b5bd703e9788ca8ecf31"
MAX_CERT_BYTES = 65536
ROOT_FILENAME = "russian_trusted_root_ca_pem.crt"


def verify_root(data: bytes) -> str:
    """Accept PEM or DER only when the canonical DER fingerprint matches."""
    if not isinstance(data, bytes) or not 200 <= len(data) <= MAX_CERT_BYTES:
        raise ValueError("Invalid root CA certificate size")
    der = data
    if b"-----BEGIN CERTIFICATE-----" in data:
        try:
            pem = data.decode("ascii").strip()
            if (not pem.startswith("-----BEGIN CERTIFICATE-----")
                    or not pem.endswith("-----END CERTIFICATE-----")
                    or pem.count("-----BEGIN CERTIFICATE-----") != 1
                    or pem.count("-----END CERTIFICATE-----") != 1):
                raise ValueError("Invalid PEM certificate wrapper")
            der = ssl.PEM_cert_to_DER_cert(pem)
        except (ValueError, UnicodeError):
            raise ValueError("Invalid PEM certificate format") from None
    if hashlib.sha256(der).hexdigest() != ROOT_SHA256:
        raise ValueError("Official root CA fingerprint mismatch; nothing trusted")
    return ssl.DER_cert_to_PEM_cert(der)


def select_verified_eis_ca(override: Path | None = None, *, project_root: Path | None = None) -> Path:
    """Resolve reviewed CA in Docker /app/certs or local repository root.

    A configured path is checked strictly and never silently replaced if its
    certificate is missing or altered. Only a default path may be selected
    from known fixed layouts; no environment or filesystem-wide CA probing.
    """
    root = Path(project_root) if project_root is not None else Path(__file__).resolve().parents[2]
    if override is not None:
        selected = Path(override)
    else:
        candidates = (root / "certs" / ROOT_FILENAME, root / ROOT_FILENAME)
        selected = next((file for file in candidates if file.is_file()), None)
        if selected is None:
            raise ValueError("Verified official EIS root CA not bundled")
    verify_root(selected.read_bytes())
    return selected
