"""Strict scoped official Russian Root CA probe for EIS 44/223.

Never installs or alters system root certificates. Never disables TLS or
hostname checks. Root DER SHA-256 is pinned to a separately published value.
The provider certificate is trusted only by the two EIS test adapters.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import ssl
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

OFFICIAL_URL = "https://gu-st.ru/content/Other/doc/russian_trusted_root_ca.cer"
ROOT_SHA256 = "d26d2d0231b7c39f92cc738512ba54103519e4405d68b5bd703e9788ca8ecf31"
MAX_CERT_BYTES = 65536


def verify_root(data: bytes) -> str:
    if not isinstance(data, bytes) or len(data) > MAX_CERT_BYTES or len(data) < 200:
        raise ValueError("Invalid root CA certificate size")
    if hashlib.sha256(data).hexdigest() != ROOT_SHA256:
        raise ValueError("Official root CA fingerprint mismatch; nothing trusted")
    return ssl.DER_cert_to_PEM_cert(data)


def official_download() -> bytes:
    request = Request(OFFICIAL_URL, headers={"User-Agent": "VALYQON-EIS-CA-verify/1"})
    with urlopen(request, timeout=25, context=ssl.create_default_context()) as response:
        url = urlsplit(response.geturl())
        if url.scheme != "https" or url.hostname != "gu-st.ru" or response.status != 200:
            raise ValueError("Official CA download origin/status mismatch")
        return response.read(MAX_CERT_BYTES + 1)


def run(source_file: Path | None = None) -> int:
    data = source_file.read_bytes() if source_file else official_download()
    pem = verify_root(data)
    with tempfile.TemporaryDirectory(prefix="valyqon-eis-trusted-root-") as directory:
        root_file = Path(directory) / "eis-only-root.pem"
        root_file.write_text(pem, encoding="ascii", newline="\n")
        before_ca = os.environ.get("VALYQON_RU_EIS_CA_CERT")
        before_strict = os.environ.get("VALYQON_RU_REQUIRE_EIS_LIVE")
        try:
            os.environ["VALYQON_RU_EIS_CA_CERT"] = str(root_file)
            os.environ["VALYQON_RU_REQUIRE_EIS_LIVE"] = "1"
            print("EIS_ROOT_SHA256_PIN=VERIFIED", flush=True)
            print("APP_SCOPED_ONLY=YES; SYSTEM_TRUST_CHANGED=NO", flush=True)
            from scripts.ru_public_live_smoke import main as public_smoke
            return public_smoke()
        finally:
            for name, value in (
                ("VALYQON_RU_EIS_CA_CERT", before_ca),
                ("VALYQON_RU_REQUIRE_EIS_LIVE", before_strict),
            ):
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root-cer", type=Path, default=None,
                        help="Optional manually downloaded official Russian Trusted Root CA DER .cer")
    args = parser.parse_args()
    try:
        return run(args.root_cer)
    except Exception as error:
        # Do not print URLs, transport exceptions, file paths, secrets or body bytes.
        print("EIS_SCOPED_ROOT_PROBE=BLOCKED", flush=True)
        print("FAILURE_TYPE=" + type(error).__name__, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
