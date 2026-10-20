"""Strict scoped official Russian Root CA probe for EIS 44/223.

Never installs or alters system root certificates. Never disables TLS or
hostname checks. Root DER SHA-256 is pinned to a separately published value.
The provider certificate is trusted only by the two EIS test adapters.
"""
from __future__ import annotations

import argparse
import os
import ssl
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

OFFICIAL_URL = "https://gu-st.ru/content/Other/doc/russian_trusted_root_ca.cer"
# One shared implementation is bundled with the Docker application.
from app.sources.eis_pinned_ca import MAX_CERT_BYTES, ROOT_SHA256, verify_root


def official_download() -> bytes:
    request = Request(OFFICIAL_URL, headers={"User-Agent": "VALYQON-EIS-CA-verify/1"})
    with urlopen(request, timeout=25, context=ssl.create_default_context()) as response:
        url = urlsplit(response.geturl())
        if url.scheme != "https" or url.hostname != "gu-st.ru" or response.status != 200:
            raise ValueError("Official CA download origin/status mismatch")
        return response.read(MAX_CERT_BYTES + 1)


def pinned_ssl_context(source_file: Path) -> ssl.SSLContext:
    """Load only the fingerprint-verified root in memory on Windows or Linux.

    No /dev/stdin, system-store installation, environment CA or second file
    read is needed. Hostname and certificate validation remain mandatory.
    """
    pem = verify_root(source_file.read_bytes())
    return ssl.create_default_context(cadata=pem)


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
        # Never print arbitrary exceptions, URLs, file paths, secrets or bodies.
        # Print only allowlisted fixed-format certificate errors.
        print("EIS_SCOPED_ROOT_PROBE=BLOCKED", flush=True)
        print("FAILURE_TYPE=" + type(error).__name__, flush=True)
        known = {
            "Invalid root CA certificate size": "CERT_SIZE_OR_RESPONSE_INVALID",
            "Invalid PEM certificate wrapper": "CERT_FORMAT_INVALID",
            "Invalid PEM certificate format": "CERT_FORMAT_INVALID",
            "Official root CA fingerprint mismatch; nothing trusted": "CERT_DER_SHA256_MISMATCH",
            "Official CA download origin/status mismatch": "OFFICIAL_DOWNLOAD_ORIGIN_REJECTED",
        }
        reason = known.get(str(error), "OTHER_FAILURE") if type(error) is ValueError else "OTHER_FAILURE"
        print("FAILURE_STAGE=" + reason, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
