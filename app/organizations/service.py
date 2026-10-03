"""Internal operations and explicit allow-list authorization primitives."""
from .models import Role
from .repository import OrganizationError


class OrganizationService:
    def __init__(self, repository):
        self.repository = repository

    def require_membership(self, account, organization_id, allowed_roles=None):
        if not account.is_active:
            raise OrganizationError("Organization access denied.")
        membership = self.repository.get_membership(organization_id, account.id)
        allowed = None if allowed_roles is None else {Role(role) for role in allowed_roles}
        if membership is None or (allowed is not None and membership.role not in allowed):
            raise OrganizationError("Organization access denied.")
        return membership

    def get(self, account, organization_id):
        self.require_membership(account, organization_id)
        return self.repository.get(organization_id)

    def list_for_account(self, account):
        if not account.is_active:
            raise OrganizationError("Organization access denied.")
        return self.repository.list_for_account(account.id)

    def default_for_account(self, account):
        if not account.is_active:
            raise OrganizationError("Organization access denied.")
        return self.repository.default_for_account(account.id)

    def create(self, account, name):
        if not account.is_active:
            raise OrganizationError("Organization access denied.")
        return self.repository.create(name, account.id)

    def list_memberships(self, account, organization_id):
        self.require_membership(account, organization_id)
        return self.repository.list_memberships(organization_id)

    # Trusted internal commands, not HTTP endpoints. Future callers must authorize
    # the actor explicitly before calling; repository protects structural invariants.
    def add_membership(self, organization_id, account_id, role):
        return self.repository.add_membership(organization_id, account_id, role)

    def update_role(self, organization_id, account_id, role):
        return self.repository.update_role(organization_id, account_id, role)

    def remove_membership(self, organization_id, account_id):
        return self.repository.remove_membership(organization_id, account_id)
