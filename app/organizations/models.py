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
