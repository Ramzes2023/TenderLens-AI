"""Password hashing helpers using Python's built-in scrypt implementation."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

SCHEME = "scrypt"
N = 1 << 14
R = 8
P = 1
DKLEN = 32
SALT_BYTES = 16


class PasswordPolicyError(ValueError):
    pass


def validate_password(password: str) -> None:
    if not isinstance(password, str):
        raise PasswordPolicyError("Password must be text.")
    if len(password) < 12:
        raise PasswordPolicyError("Password must contain at least 12 characters.")
    if len(password) > 128:
        raise PasswordPolicyError("Password must contain at most 128 characters.")


def _derive(password: str, salt: bytes, *, n: int = N, r: int = R, p: int = P) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=DKLEN)


def hash_password(password: str) -> str:
    validate_password(password)
    salt = os.urandom(SALT_BYTES)
    digest = _derive(password, salt)
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii").rstrip("=")
    digest_b64 = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{SCHEME}${N}${R}${P}${salt_b64}${digest_b64}"


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n_raw, r_raw, p_raw, salt_raw, digest_raw = encoded.split("$", 5)
        if scheme != SCHEME:
            return False
        n, r, p = int(n_raw), int(r_raw), int(p_raw)
        if n <= 1 or r <= 0 or p <= 0:
            return False
        salt = _decode(salt_raw)
        expected = _decode(digest_raw)
        actual = _derive(password, salt, n=n, r=r, p=p)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, MemoryError):
        return False
