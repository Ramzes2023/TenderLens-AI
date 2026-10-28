"""Signed Resend delivery-outcome telemetry (off unless explicitly configured).

An SMTP handoff is not evidence that Gmail has accepted an email.
This endpoint records redacted outcomes only. It does not issue or modify
authentication tickets, send emails, or change any account state.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])
_LOG = logging.getLogger("valyqon.resend.outcomes")
_MAX_BYTES = 65536
_TOLERANCE_SECONDS = 300
_TYPES = frozenset({
    "email.sent", "email.delivered", "email.delivery_delayed",
    "email.bounced", "email.suppressed", "email.complained",
})
_SUBJECT_KINDS = {
    "Verify your VALYQON AI email": "verification",
    "Reset your VALYQON AI password": "password_reset",
}


def _verify(secret: str, body: bytes, headers, *, now: int | None = None) -> bool:
    """Verify a raw Svix/Resend HMAC webhook without logging secrets or body."""
    if not secret.startswith("whsec_"):
        return False
    msg_id = headers.get("svix-id", "")
    timestamp = headers.get("svix-timestamp", "")
    signatures = headers.get("svix-signature", "")
    if (not msg_id or len(msg_id) > 128 or not msg_id.isascii()
            or not timestamp.isascii() or not timestamp.isdecimal()
            or len(timestamp) > 16):
        return False
    current = int(time.time()) if now is None else now
    if abs(current - int(timestamp)) > _TOLERANCE_SECONDS:
        return False
    try:
        raw_secret = secret[6:]
        signing_key = base64.b64decode(
            raw_secret + "=" * (-len(raw_secret) % 4), validate=True,
        )
        if len(signing_key) < 16:
            return False
        signed = msg_id.encode("ascii") + b"." + timestamp.encode("ascii") + b"." + body
        expected = hmac.new(signing_key, signed, hashlib.sha256).digest()
        for entry in signatures.split():
            if not entry.startswith("v1,"):
                continue
            presented = base64.b64decode(entry[3:], validate=True)
            if hmac.compare_digest(expected, presented):
                return True
    except (UnicodeError, ValueError, TypeError, base64.binascii.Error):
        return False
    return False


@router.post("/resend")
async def resend_outcome(request: Request) -> dict[str, bool]:
    """Accept signed events; record only known auth-mail category and outcome."""
    secret = os.environ.get("VALYQON_RESEND_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(status_code=404, detail="Not found.")
    # Bounded streaming, including when Content-Length is absent or untrusted.
    chunks: list[bytes] = []
    length = 0
    async for chunk in request.stream():
        length += len(chunk)
        if length > _MAX_BYTES:
            raise HTTPException(status_code=413, detail="Webhook too large.")
        chunks.append(chunk)
    body = b"".join(chunks)
    if not _verify(secret, body, request.headers):
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")
    try:
        event = json.loads(body)
    except (ValueError, UnicodeError):
        raise HTTPException(status_code=400, detail="Invalid webhook body.") from None
    if not isinstance(event, dict):
        raise HTTPException(status_code=400, detail="Invalid webhook body.")
    event_type = event.get("type")
    data = event.get("data")
    if event_type in _TYPES and isinstance(data, dict):
        kind = _SUBJECT_KINDS.get(data.get("subject"))
        if kind:
            # Never log recipient, message ID, subject, token-bearing URL or bounce text.
            level = logging.WARNING if event_type in {
                "email.bounced", "email.suppressed", "email.complained",
            } else logging.INFO
            _LOG.log(level, "resend_account_mail_event kind=%s outcome=%s", kind, event_type)
    return {"accepted": True}
