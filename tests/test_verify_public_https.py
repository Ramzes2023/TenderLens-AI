"""Release-edge verification contracts; never contact external hosts in tests."""
from email.message import Message
from unittest.mock import patch, MagicMock
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
        _Response("<html><body class=\"landing premium\">VALYQON AI public portal<form id=\"guestSearchForm\"></form><div id=\"guestSearchResults\"></div></body></html>",{
            "Strict-Transport-Security":"max-age=31536000",
            "X-Content-Type-Options":"nosniff",
        }),
        _Response('{"status":"ok","service":"VALYQON AI","components":'
                  '{"database":"ready","scoring":"ready","cache":"ready"}}'),
    ]
    with patch("scripts.verify_public_https.socket.getaddrinfo",return_value=[(0,0,0,"",("93.184.216.34",443))]),\
         patch("scripts.verify_public_https._https_client",return_value=MagicMock(open=MagicMock(side_effect=responses))):
        result=verify("https://example.org")
    assert result["public_edge_pass"] is True
    assert result["ready_for_commercial_launch"] is False
    assert result["billing_entitlements"]=="NOT_TESTED"
    assert result["real_source_worker_to_user"]=="NOT_TESTED"


@pytest.mark.parametrize("health_json", [
    '{"status":"degraded","service":"VALYQON AI","components":'
    '{"database":"unavailable","scoring":"ready","cache":"ready"}}',
    '{"status":"ok","service":"VALYQON AI","components":'
    '{"database":"ready","scoring":"unavailable","cache":"ready"}}',
    '{"status":"ok","service":"VALYQON AI","components":'
    '{"database":"ready","scoring":"ready","cache":"unavailable"}}',
    '{"status":"ok","components":{"database":"ready","scoring":"ready"}}',
    '{"unexpected":"JSON object but not actual health"}',
])
def test_https_probe_rejects_unhealthy_service_even_with_http_200(health_json):
    responses=[
        _Response("<html><body class=\"landing premium\">VALYQON AI public portal<form id=\"guestSearchForm\"></form><div id=\"guestSearchResults\"></div></body></html>",{
            "Strict-Transport-Security":"max-age=31536000",
            "X-Content-Type-Options":"nosniff",
        }),
        _Response(health_json),
    ]
    with (
        patch("scripts.verify_public_https.socket.getaddrinfo",
              return_value=[(0,0,0,"",("93.184.216.34",443))]),
        patch("scripts.verify_public_https._https_client",
              return_value=MagicMock(open=MagicMock(side_effect=responses))),
    ):
        result=verify("https://example.org")
    assert result["dns"]=="PASS"
    assert result["tls"]=="PASS"
    assert result["health"]=="FAIL"
    assert result["public_edge_pass"] is False
    assert result["ready_for_commercial_launch"] is False


def test_tls_or_network_failure_blocks_release_without_leaking_body():
    with patch("scripts.verify_public_https.socket.getaddrinfo",return_value=[(0,0,0,"",("93.184.216.34",443))]),\
         patch("scripts.verify_public_https._https_client",return_value=MagicMock(open=MagicMock(side_effect=URLError("network unavailable")))):
        result=verify("https://example.org")
    assert result["public_edge_pass"] is False
    assert result["ready_for_commercial_launch"] is False
    assert "network unavailable" not in str(result)
    assert main(["--url","http://example.org"])==2


def test_private_dns_is_refused_before_any_http_request():
    with patch("scripts.verify_public_https.socket.getaddrinfo",
               return_value=[(0,0,0,"",("127.0.0.1",443))]),\
         patch("scripts.verify_public_https._https_client") as client:
        result=verify("https://example.org")
    assert result["public_edge_pass"] is False
    assert result["dns"]=="NOT_VERIFIED"
    client.assert_not_called()


def test_redirect_handler_refuses_cross_host_and_any_redirect():
    from scripts.verify_public_https import _NoRedirect
    assert _NoRedirect().redirect_request(None,None,302,"Moved",{}, "https://elsewhere.example/") is None


def test_public_edge_does_not_accept_legacy_login_even_when_http_200():
    """A 200 OK login screen can contain VALYQON branding but is not public."""
    from scripts.verify_public_https import _is_public_landing
    legacy='<html><title>VALYQON AI</title><body class="login">Sign in</body></html>'
    assert _is_public_landing(legacy) is False
    assert _is_public_landing('<body class="landing premium">VALYQON</body>') is False
    proper=(
        '<body class="landing premium">VALYQON'
        '<form id="guestSearchForm"></form>'
        '<div id="guestSearchResults"></div></body>'
    )
    assert _is_public_landing(proper) is True

    responses=[
        _Response(legacy,{
            "Strict-Transport-Security":"max-age=31536000",
            "X-Content-Type-Options":"nosniff",
        }),
        _Response('{"status":"ok","service":"VALYQON AI","components":'
                  '{"database":"ready","scoring":"ready","cache":"ready"}}'),
    ]
    with (
        patch("scripts.verify_public_https.socket.getaddrinfo",
              return_value=[(0,0,0,"",("93.184.216.34",443))]),
        patch("scripts.verify_public_https._https_client",
              return_value=MagicMock(open=MagicMock(side_effect=responses))),
    ):
        result=verify("https://example.org")
    assert result["dns"]=="PASS"
    assert result["tls"]=="PASS"
    assert result["homepage"]=="FAIL"
    assert result["public_edge_pass"] is False
    assert result["ready_for_commercial_launch"] is False
