"""Organization application service and explicit RBAC primitives."""

from .models import Role
from .repository import OrganizationError


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
