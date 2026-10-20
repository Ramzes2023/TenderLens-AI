"""Independent curl HTTPS observation for the two fixed Ingushetia origins.

OBSERVATIONAL ONLY: no repository Worker, SQL, notifications or production.
Public DNS answers are validated in full before any outbound connection.
curl is pinned to one verified public IP at a time; hostname TLS verification
remains enabled, proxies and HTTP redirects are disabled. Response bodies are
discarded under a byte cap. Never treat HTTP 200 as procurement acceptance.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
import subprocess
import tempfile

from app.sources.http_transport import _public_address, resolve_addresses
from app.sources.ru_ingushetia_eis44 import RSS_URL
from app.sources.ru_ingushetia_fabrikant44 import HOST as FAB_HOST, LIST_URL
from scripts.ru_eis_pinned_tls_probe import verify_root

ROOT = Path(__file__).resolve().parents[1] / "russian_trusted_root_ca_pem.crt"
HOSTS = (
    ("official_eis_rss", "zakupki.gov.ru", RSS_URL),
    ("first_party_fabrikant_regional_listing", FAB_HOST, LIST_URL),
)
MAX_IPS_PER_HOST = 3
MAX_BYTES = 1_800_000


async def public_addresses(host, resolver=resolve_addresses):
    raw = await resolver(host, 443)
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError("DNS not proven")
    # All records are verified before permitting *any* transport, including
    # DNS replies with a late private/link-local/rebinding address.
    verified = tuple(dict.fromkeys(_public_address(ip) for ip in raw))
    return verified[:MAX_IPS_PER_HOST], len(verified)


def _pinned_resolve(host, ip):
    address = _public_address(str(ip))
    literal = f"[{address}]" if address.version == 6 else str(address)
    return f"{host}:443:{literal}"


def curl_observation(host, url, address, *, root_path, runner=subprocess.run):
    if (host, url) not in {("zakupki.gov.ru", RSS_URL), (FAB_HOST, LIST_URL)}:
        raise ValueError("Only matched fixed official diagnostic endpoints")
    args = [
        "curl", "--silent", "--show-error", "--http1.1",
        "--proto", "=https", "--max-redirs", "0",
        "--noproxy", "*", "--proxy", "",
        "--connect-timeout", "7", "--max-time", "22",
        "--max-filesize", str(MAX_BYTES),
        "--output", "REPLACED_BY_ISOLATED_TEMP_DIR",
        "--write-out", "%{http_code};%{size_download}",
        "--resolve", _pinned_resolve(host, address),
    ]
    if host == "zakupki.gov.ru":
        args += ["--cacert", str(root_path)]
    args.append(url)
    # Unique temporary output prevents cross-job races; use no-shell argv.
    with tempfile.TemporaryDirectory(prefix="valyqon-ing-curl-") as directory:
        args[args.index("--output") + 1] = str(Path(directory) / "body")
        try:
            done = runner(args, capture_output=True, text=True, timeout=26, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return {"status": "TRANSPORT_FAILED", "exit_code": None, "http": None}
    stdout = done.stdout.strip() if type(done.stdout) is str else ""
    m = re.fullmatch(r"([0-9]{3});([0-9]+)(?:\.[0-9]+)?", stdout)
    http = int(m.group(1)) if m else None
    size = int(m.group(2)) if m else None
    rc = done.returncode if type(done.returncode) is int and 0 <= done.returncode <= 127 else None
    return {
        "status": "HTTP_200_OBSERVED_ONLY" if rc == 0 and http == 200
                  else "HTTP_OTHER" if rc == 0 and http is not None
                  else "TRANSPORT_FAILED",
        "exit_code": rc,
        "http": http,
        "bytes": size if size is not None and size <= MAX_BYTES else None,
    }


async def observation():
    # Never trust an unpinned CA from the repository, an environment variable
    # or a remote server. curl checks both chain and original origin hostname.
    verify_root(ROOT.read_bytes())
    results = []
    for name, host, url in HOSTS:
        try:
            addresses, total = await public_addresses(host)
            attempts = []
            for ip in addresses:
                detail = curl_observation(host, url, ip, root_path=ROOT)
                attempts.append({"family": "ipv6" if ip.version == 6 else "ipv4", **detail})
                if detail["status"] == "HTTP_200_OBSERVED_ONLY":
                    break
            results.append({"route": name, "dns_total_validated": total, "attempts": attempts})
        except Exception as exc:
            results.append({"route": name, "status": "BLOCKED", "failure_class": type(exc).__name__})
    return results


def main():
    print("INGUSHETIA_INDEPENDENT_HTTPS=" + json.dumps(asyncio.run(observation()), sort_keys=True), flush=True)
    print("PROXY_USED=NO; STRICT_TLS=YES; LIVE_INGESTION_PROVEN=NO; PRODUCTION_CHANGED=NO", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
