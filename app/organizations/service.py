"""Organization application service and explicit RBAC primitives."""

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from .models import Role
from .repository import OrganizationError


_INVITATION_EMAIL_RE = re.compile(
    r"^[^@\s]{1,64}@[^@\s]{1,189}$"
)


def _normalize_invitation_email(email):
    value = (email or "").strip().lower()

    if (
        len(value) > 254
        or not _INVITATION_EMAIL_RE.fullmatch(value)
    ):
        raise OrganizationError(
            "Enter a valid email address."
        )

    local, domain = value.rsplit("@", 1)

    if (
        "." not in domain
        or domain.startswith(".")
        or domain.endswith(".")
    ):
        raise OrganizationError(
            "Enter a valid email address."
        )

    return f"{local}@{domain}"

class OrganizationService:
    def __init__(self, repository):
        self.repository = repository

    @staticmethod
    def _require_active(account):
        if account is None or not account.is_active:
            raise OrganizationError("Organization access denied.")

    def require_membership(
        self,
        account,
        organization_id,
        allowed_roles=None,
    ):
        self._require_active(account)

        membership = self.repository.get_membership(
            organization_id,
            account.id,
        )

        allowed = (
            None
            if allowed_roles is None
            else {Role(role) for role in allowed_roles}
        )

        if membership is None or (
            allowed is not None and membership.role not in allowed
        ):
            raise OrganizationError("Organization access denied.")

        return membership

    def get(self, account, organization_id):
        self.require_membership(account, organization_id)
        organization = self.repository.get(organization_id)
        if organization is None:
            raise OrganizationError("Organization not found.")
        return organization

    def list_for_account(self, account):
        self._require_active(account)
        return self.repository.list_for_account(account.id)

    def default_for_account(self, account):
        self._require_active(account)
        return self.repository.default_for_account(account.id)

    def create(self, account, name):
        self._require_active(account)
        return self.repository.create(name, account.id)

    # Existing trusted/internal method kept for compatibility.
    def list_memberships(self, account, organization_id):
        self.require_membership(account, organization_id)
        return self.repository.list_memberships(organization_id)

    # -----------------------------------------------------------------
    # Phase 18B manager-facing operations.
    # -----------------------------------------------------------------

    def list_memberships_for_manager(self, actor, organization_id):
        self.require_membership(
            actor,
            organization_id,
            {Role.OWNER, Role.ADMIN},
        )
        return self.repository.list_memberships(organization_id)

    def add_member(
        self,
        actor,
        organization_id,
        account_id,
        role,
    ):
        self._require_active(actor)
        return self.repository.add_membership_authorized(
            actor_account_id=actor.id,
            organization_id=organization_id,
            account_id=account_id,
            role=role,
        )

    def update_member_role(
        self,
        actor,
        organization_id,
        account_id,
        role,
    ):
        self._require_active(actor)
        return self.repository.update_role_authorized(
            actor_account_id=actor.id,
            organization_id=organization_id,
            account_id=account_id,
            role=role,
        )

    def remove_member(
        self,
        actor,
        organization_id,
        account_id,
    ):
        self._require_active(actor)
        return self.repository.remove_membership_authorized(
            actor_account_id=actor.id,
            organization_id=organization_id,
            account_id=account_id,
        )

    # Trusted internal commands retained for non-HTTP callers.
    def add_membership(self, organization_id, account_id, role):
        return self.repository.add_membership(
            organization_id,
            account_id,
            role,
        )

    def update_role(self, organization_id, account_id, role):
        return self.repository.update_role(
            organization_id,
            account_id,
            role,
        )

    def remove_membership(self, organization_id, account_id):
        return self.repository.remove_membership(
            organization_id,
            account_id,
        )

    # -----------------------------------------------------------------
    # Phase 18F1 invitation operations.
    # -----------------------------------------------------------------

    @staticmethod
    def _invitation_token_hash(token):
        return hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest()

    def create_invitation(
        self,
        actor,
        organization_id,
        email,
        role,
    ):
        self._require_active(actor)

        clean_email = (
            _normalize_invitation_email(
                email
            )
        )

        role = Role(role)

        if role == Role.OWNER:
            raise OrganizationError(
                "Owner role cannot be granted by invitation."
            )

        token = secrets.token_urlsafe(32)

        expires_at = (
            datetime.now(timezone.utc)
            + timedelta(days=7)
        ).isoformat(
            timespec="seconds"
        )

        invitation = (
            self.repository.create_invitation_authorized(
                actor_account_id=actor.id,
                organization_id=organization_id,
                email=clean_email,
                role=role,
                token_hash=self._invitation_token_hash(
                    token
                ),
                expires_at=expires_at,
            )
        )

        return invitation, token

    def list_invitations(
        self,
        actor,
        organization_id,
    ):
        self._require_active(actor)

        return (
            self.repository.list_invitations_authorized(
                actor_account_id=actor.id,
                organization_id=organization_id,
            )
        )

    def revoke_invitation(
        self,
        actor,
        organization_id,
        invitation_id,
    ):
        self._require_active(actor)

        return (
            self.repository.revoke_invitation_authorized(
                actor_account_id=actor.id,
                organization_id=organization_id,
                invitation_id=invitation_id,
            )
        )

    def preview_invitation(
        self,
        token,
    ):
        clean = (
            token
            or ""
        ).strip()

        if not clean or len(clean) > 256:
            raise OrganizationError(
                "Invitation is invalid or expired."
            )

        current_time = datetime.now(
            timezone.utc
        ).isoformat(
            timespec="seconds"
        )

        return self.repository.preview_invitation(
            token_hash=self._invitation_token_hash(
                clean
            ),
            current_time=current_time,
        )

    def accept_invitation(
        self,
        account,
        token,
    ):
        self._require_active(account)

        clean = (
            token
            or ""
        ).strip()

        if not clean or len(clean) > 256:
            raise OrganizationError(
                "Invitation is invalid or expired."
            )

        current_time = datetime.now(
            timezone.utc
        ).isoformat(
            timespec="seconds"
        )

        return self.repository.accept_invitation(
            account_id=account.id,
            token_hash=self._invitation_token_hash(
                clean
            ),
            current_time=current_time,
        )
