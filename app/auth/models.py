"""Authentication domain models for VALYQON AI web accounts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthAccount:
    id: int
    email: str
    owner_user_id: int
    is_active: bool
    email_verified: bool
    email_verified_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class AuthSession:
    token_hash: str
    account_id: int
    expires_at: str
    created_at: str
    last_seen_at: str
