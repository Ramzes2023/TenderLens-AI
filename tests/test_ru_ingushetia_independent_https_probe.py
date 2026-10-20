"""Offline-only independent strict curl probe regressions; no real DNS/HTTP."""
import asyncio
import ipaddress
import subprocess

import pytest

from scripts.ru_ingushetia_independent_https_probe import (
    MAX_BYTES, LIST_URL, RSS_URL, curl_observation, public_addresses,
)


def test_public_dns_validates_complete_answer_before_approving_first_ip():
    async def resolver(host, port):
        assert host == "zakupki.gov.ru" and port == 443
        return ["8.8.8.8", "10.2.3.4"]

    with pytest.raises(Exception):
        asyncio.run(public_addresses("zakupki.gov.ru", resolver))


def test_dns_deduplicates_public_addresses_and_caps_attempts():
    async def resolver(host, port):
        return ["8.8.8.8", "8.8.8.8", "1.1.1.1", "9.9.9.9", "4.2.2.2"]

    checked, total = asyncio.run(public_addresses("zakupki.gov.ru", resolver))
    assert checked == tuple(map(ipaddress.ip_address, ["8.8.8.8", "1.1.1.1", "9.9.9.9"]))
    assert total == 4


@pytest.mark.parametrize("host,url,ip", [
    ("example.invalid", LIST_URL, "8.8.8.8"),
    ("44.fabrikant.ru", "http://44.fabrikant.ru/private", "8.8.8.8"),
    ("44.fabrikant.ru", LIST_URL, "169.254.169.254"),
    ("zakupki.gov.ru", RSS_URL, "127.0.0.1"),
])
def test_invalid_endpoint_or_ip_never_invokes_curl(host, url, ip):
    calls = []
    def runner(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("No subprocess may be launched")
    with pytest.raises(ValueError):
        curl_observation(host, url, ip, root_path="trusted.pem", runner=runner)
    assert not calls


@pytest.mark.parametrize("host,url,ip,expected_resolve", [
    ("zakupki.gov.ru", RSS_URL, "8.8.8.8", "zakupki.gov.ru:443:8.8.8.8"),
    ("44.fabrikant.ru", LIST_URL, "2606:4700:4700::1111",
     "44.fabrikant.ru:443:[2606:4700:4700::1111]"),
])
def test_curl_probe_is_direct_https_no_proxy_with_original_sni(host, url, ip, expected_resolve):
    calls = []
    def runner(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="200;5176.000", stderr="")

    result = curl_observation(host, url, ip, root_path="trusted.pem", runner=runner)
    assert result == {"status": "HTTP_200_OBSERVED_ONLY", "exit_code": 0,
                      "http": 200, "bytes": 5176}
    assert len(calls) == 1
    argv, kw = calls[0]
    assert kw == dict(capture_output=True, text=True, timeout=26, check=False)
    assert argv[0] == "curl" and argv[-1] == url
    assert argv[argv.index("--resolve") + 1] == expected_resolve
    assert argv[argv.index("--proto") + 1] == "=https"
    assert argv[argv.index("--max-redirs") + 1] == "0"
    assert argv[argv.index("--noproxy") + 1] == "*"
    assert argv[argv.index("--proxy") + 1] == ""
    assert argv[argv.index("--max-filesize") + 1] == str(MAX_BYTES)
    assert "--insecure" not in argv and "-k" not in argv
    assert ("--cacert" in argv) == (host == "zakupki.gov.ru")


def test_timeout_and_http_403_are_observational_not_success():
    def blocked(args, **kwargs):
        return subprocess.CompletedProcess(args, 28, stdout="000;0", stderr="secret")

    def refused(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout="403;100.000", stderr="")

    assert curl_observation("44.fabrikant.ru", LIST_URL, "8.8.8.8",
                            root_path="root", runner=blocked)["status"] == "TRANSPORT_FAILED"
    result = curl_observation("44.fabrikant.ru", LIST_URL, "8.8.8.8",
                              root_path="root", runner=refused)
    assert result["status"] == "HTTP_OTHER" and result["http"] == 403
