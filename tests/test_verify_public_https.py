"""Release-edge verification contracts; never contact external hosts in tests."""
from email.message import Message
from unittest.mock import patch
from urllib.error import URLError
import pytest

from scripts.verify_public_https import validate_target, verify, main


@pytest.mark.parametrize("address",[
    "http://example.org","https://localhost","https://127.0.0.1",
    "https://tenderlens.example.com","https://example.invalid",
    "https://admin:secret@example.org","https://example.org:8443",
    "https://example.org/path","https://example.org/?token=abc",
    "https://-bad.example.org","https://example.org/#x",
])
def test_release_probe_rejects_unsafe_or_placeholder_addresses(address):
    with pytest.raises(ValueError):
        validate_target(address)


def test_release_probe_accepts_valid_https_domain():
    assert validate_target("https://example.org")==("example.org",443)


class _Response:
    def __init__(self,text,headers=None):
        self.status=200
        self.data=text.encode("utf-8")
        self.headers=Message()
        for key,value in (headers or {}).items():
            self.headers[key]=value
    def read(self,limit=65536):
        return self.data[:limit]
    def __enter__(self):return self
    def __exit__(self,*args):return False


def test_public_edge_pass_does_not_claim_tenders_or_payments():
    responses=[
        _Response("<html>VALYQON AI public portal</html>",{
            "Strict-Transport-Security":"max-age=31536000",
            "X-Content-Type-Options":"nosniff",
        }),
        _Response('{"status":"ready"}'),
    ]
    with patch("scripts.verify_public_https.socket.getaddrinfo",return_value=[("dummy",)]),\
         patch("scripts.verify_public_https.urlopen",side_effect=responses):
        result=verify("https://example.org")
    assert result["public_edge_pass"] is True
    assert result["ready_for_commercial_launch"] is False
    assert result["billing_entitlements"]=="NOT_TESTED"
    assert result["real_source_worker_to_user"]=="NOT_TESTED"


def test_tls_or_network_failure_blocks_release_without_leaking_body():
    with patch("scripts.verify_public_https.socket.getaddrinfo",return_value=[("dummy",)]),\
         patch("scripts.verify_public_https.urlopen",side_effect=URLError("network unavailable")):
        result=verify("https://example.org")
    assert result["public_edge_pass"] is False
    assert result["ready_for_commercial_launch"] is False
    assert "network unavailable" not in str(result)
    assert main(["--url","http://example.org"])==2
