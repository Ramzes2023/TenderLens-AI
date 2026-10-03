"""Internal namespace helpers for organization-owned compatibility state."""

ORGANIZATION_OWNER_OFFSET = 8_000_000_000_000


def organization_owner_id(organization_id: int) -> int:
    organization_id = int(organization_id)

    if organization_id <= 0:
        raise ValueError(
            "organization_id must be positive."
        )

    return ORGANIZATION_OWNER_OFFSET + organization_id


def is_organization_owner_id(owner_user_id: int) -> bool:
    return int(owner_user_id) >= ORGANIZATION_OWNER_OFFSET
