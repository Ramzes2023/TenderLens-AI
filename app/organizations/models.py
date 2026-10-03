from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


@dataclass(frozen=True)
class Organization:
    id: int
    name: str
    created_at: str
    updated_at: str
    created_by_account_id: int
    personal_account_id: int | None


@dataclass(frozen=True)
class Membership:
    organization_id: int
    account_id: int
    role: Role
    created_at: str


@dataclass(frozen=True)
class Invitation:
    id: int
    organization_id: int
    email: str
    role: Role
    invited_by_account_id: int
    expires_at: str
    accepted_at: str | None
    revoked_at: str | None
    created_at: str
