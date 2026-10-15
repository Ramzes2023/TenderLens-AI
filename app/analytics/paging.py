"""Signed, scoped read cursors. Replaying a cursor repeats a read, never a write."""
import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone


class CursorError(ValueError):
    pass


def utc_filter(value):
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc).isoformat(timespec='microseconds')
    except (ValueError, AttributeError, OverflowError):
        raise CursorError('An offset-aware UTC time is required.') from None


def seal(state, key):
    if not isinstance(key, str) or not key.strip():
        raise CursorError('Existing application signing key is unavailable.')
    raw = json.dumps(state, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    signature = hmac.new(key.encode(), b'phase24-history-v1\0' + raw, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature + raw).decode().rstrip('=')


def unseal(token, key, binding):
    try:
        if len(token) > 100000:
            raise ValueError()
        raw = base64.b64decode(token + '=' * (-len(token) % 4), altchars=b'-_', validate=True)
        state = json.loads(raw[32:])
        if not hmac.compare_digest(seal(state, key), token):
            raise ValueError()
        if state['binding'] != binding or state['expires'] < time.time():
            raise ValueError()
        return state
    except (ValueError, KeyError, TypeError, RecursionError, OverflowError):
        raise CursorError('Invalid, expired or differently scoped cursor.') from None
