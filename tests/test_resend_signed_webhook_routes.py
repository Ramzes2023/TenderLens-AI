"""Offline contract tests: Resend delivery events never imply a sent auth email."""
import base64
import hashlib
import hmac
import json
import logging
import time

import pytest
from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.resend_webhook_routes import _verify

_SECRET_KEY = b"temporary-offline-webhook-key-32-byte"
_SECRET = "whsec_" + base64.b64encode(_SECRET_KEY).decode("ascii")
_PATH = "/api/v1/webhooks/resend"


def signed_request(body: bytes, *, key=_SECRET_KEY, timestamp=None, msgid="msg_fixture"):
    stamp = str(int(time.time()) if timestamp is None else timestamp)
    to_sign = msgid.encode() + b"." + stamp.encode() + b"." + body
    signature = base64.b64encode(hmac.new(key, to_sign, hashlib.sha256).digest()).decode()
    return {
        "svix-id": msgid,
        "svix-timestamp": stamp,
        "svix-signature": "v1," + signature,
        "content-type": "application/json",
    }


@pytest.fixture
def app_client():
    runtime = ApiRuntime()
    settings = ApiSettings(host="127.0.0.1", port=8000, reload=False, api_key=None)
    with TestClient(create_app(runtime=runtime, settings=settings)) as client:
        yield client


def payload(typ="email.bounced", subject="Verify your VALYQON AI email"):
    return json.dumps({
        "type": typ,
        "data": {
            "email_id": "would-be-private-provider-id",
            "to": ["owner-private-address@example.test"],
            "subject": subject,
            "bounce": {"message": "sensitive internal bounce details", "type": "Transient"},
        },
    }).encode()


def test_disabled_by_default_and_no_log(app_client, monkeypatch, caplog):
    monkeypatch.delenv("VALYQON_RESEND_WEBHOOK_SECRET", raising=False)
    raw = payload()
    caplog.set_level(logging.DEBUG)
    response = app_client.post(_PATH, data=raw, headers=signed_request(raw))
    assert response.status_code == 404
    assert "resend_account_mail_event" not in caplog.text


@pytest.mark.parametrize("type_,kind", [
    ("email.bounced", "verification"),
    ("email.suppressed", "verification"),
    ("email.complained", "verification"),
    ("email.failed", "verification"),
    ("email.failed", "password_reset"),
    ("email.delivered", "password_reset"),
    ("email.delivery_delayed", "password_reset"),
])
def test_verified_event_redacts_identifiers(app_client, monkeypatch, caplog, type_, kind):
    monkeypatch.setenv("VALYQON_RESEND_WEBHOOK_SECRET", _SECRET)
    subject = "Reset your VALYQON AI password" if kind == "password_reset" else "Verify your VALYQON AI email"
    raw = payload(type_, subject)
    caplog.set_level(logging.INFO, logger="valyqon.resend.outcomes")
    response = app_client.post(_PATH, content=raw, headers=signed_request(raw))
    assert response.status_code == 200
    assert response.json() == {"accepted": True}
    assert f"kind={kind} outcome={type_}" in caplog.text
    for private in ("owner-private-address", "would-be-private", "sensitive internal", subject):
        assert private not in caplog.text


@pytest.mark.parametrize("bad_headers,raw_override,expected", [
    ({"svix-signature": ""}, None, 401),
    ({"svix-signature": "v1,bad"}, None, 401),
    ({"svix-timestamp": "0"}, None, 401),
    ({"svix-timestamp": "9000000000"}, None, 401),
    ({"svix-id": "other-id"}, None, 401),
    (None, b'{"tampered":true}', 401),
])
def test_unsigned_stale_or_tampered_rejected(
    app_client, monkeypatch, caplog, bad_headers, raw_override, expected,
):
    monkeypatch.setenv("VALYQON_RESEND_WEBHOOK_SECRET", _SECRET)
    raw = payload()
    headers = signed_request(raw)
    if bad_headers:
        headers.update(bad_headers)
    caplog.set_level(logging.DEBUG)
    response = app_client.post(_PATH, content=raw if raw_override is None else raw_override, headers=headers)
    assert response.status_code == expected
    assert "resend_account_mail_event" not in caplog.text


def test_bad_json_and_oversize_are_rejected(app_client, monkeypatch):
    monkeypatch.setenv("VALYQON_RESEND_WEBHOOK_SECRET", _SECRET)
    raw = b"not json"
    response = app_client.post(_PATH, content=raw, headers=signed_request(raw))
    assert response.status_code == 400
    huge = b"X" * 65537
    response = app_client.post(_PATH, content=huge, headers=signed_request(huge))
    assert response.status_code == 413


def test_irrelevant_and_malformed_subject_never_logged(app_client, monkeypatch, caplog):
    monkeypatch.setenv("VALYQON_RESEND_WEBHOOK_SECRET", _SECRET)
    caplog.set_level(logging.DEBUG)
    for subject in ("Unrelated mail", {"unexpected": "object"}):
        raw = payload(subject=subject)
        response = app_client.post(_PATH, content=raw, headers=signed_request(raw))
        assert response.status_code == 200
    assert "resend_account_mail_event" not in caplog.text


def test_raw_body_signature_rejects_serialization_changes():
    raw = payload()
    headers = signed_request(raw)
    assert _verify(_SECRET, raw, headers)
    assert not _verify(_SECRET, json.dumps(json.loads(raw), indent=2).encode(), headers)


@pytest.mark.parametrize("missing_header", [
    "svix-id", "svix-timestamp", "svix-signature",
])
def test_missing_signature_headers_are_rejected(
    app_client, monkeypatch, caplog, missing_header,
):
    monkeypatch.setenv("VALYQON_RESEND_WEBHOOK_SECRET", _SECRET)
    raw = payload()
    headers = signed_request(raw)
    headers.pop(missing_header)
    caplog.set_level(logging.DEBUG)
    response = app_client.post(_PATH, content=raw, headers=headers)
    assert response.status_code == 401
    assert "resend_account_mail_event" not in caplog.text
