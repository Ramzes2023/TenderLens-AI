"""Application service for company workspaces."""
from __future__ import annotations

from app.scoring.models import CompanyProfile

from .models import CompanyWorkspace
from .repository import CompanyRepository


class CompanyService:
    def __init__(self, repository: CompanyRepository, fallback_profile: CompanyProfile | None = None):
        self.repository = repository
        self.fallback_profile = fallback_profile

    def list(self, owner_user_id: int) -> list[CompanyWorkspace]:
        return self.repository.list_for_owner(owner_user_id)

    def active(self, owner_user_id: int) -> CompanyWorkspace | None:
        return self.repository.active(owner_user_id)

    def profile_for_owner(self, owner_user_id: int) -> CompanyProfile | None:
        workspace = self.active(owner_user_id)
        return workspace.profile if workspace is not None else self.fallback_profile

    def scope_for_owner(self, owner_user_id: int) -> str | None:
        workspace = self.active(owner_user_id)
        return str(workspace.id) if workspace is not None else None

    def create(self, owner_user_id: int, name: str, profile: CompanyProfile,
               *, make_active: bool = True) -> CompanyWorkspace:
        return self.repository.create(owner_user_id, name, profile, make_active=make_active)

    def set_active(self, owner_user_id: int, company_id: int) -> CompanyWorkspace:
        return self.repository.set_active(owner_user_id, company_id)

    def get(self, owner_user_id: int, company_id: int) -> CompanyWorkspace | None:
        return self.repository.get(owner_user_id, company_id)

    def update(self, owner_user_id: int, company_id: int, profile: CompanyProfile,
               *, name: str | None = None) -> CompanyWorkspace:
        return self.repository.update_profile(owner_user_id, company_id, profile, name=name)

    def delete(self, owner_user_id: int, company_id: int) -> bool:
        return self.repository.delete(owner_user_id, company_id)

    # Phase 18C organization-scoped API.
    def list_for_organization(
        self,
        account_id: int,
        organization_id: int,
    ) -> list[CompanyWorkspace]:
        return self.repository.list_for_organization(
            account_id,
            organization_id,
        )

    def get_for_organization(
        self,
        account_id: int,
        organization_id: int,
        company_id: int,
    ) -> CompanyWorkspace | None:
        return self.repository.get_for_organization(
            account_id,
            organization_id,
            company_id,
        )

    def create_for_organization(
        self,
        account,
        organization_id: int,
        name: str,
        profile: CompanyProfile,
    ) -> CompanyWorkspace:
        return self.repository.create_for_organization(
            account_id=account.id,
            organization_id=organization_id,
            name=name,
            profile=profile,
        )

    def active_for_organization(
        self,
        account_id: int,
        organization_id: int,
    ) -> CompanyWorkspace | None:
        return self.repository.active_for_organization(
            account_id,
            organization_id,
        )

    def set_active_for_organization(
        self,
        account_id: int,
        organization_id: int,
        company_id: int,
    ) -> CompanyWorkspace:
        return self.repository.set_active_for_organization(
            account_id=account_id,
            organization_id=organization_id,
            company_id=company_id,
        )

    def update_for_organization(
        self,
        account_id: int,
        organization_id: int,
        company_id: int,
        *,
        profile: CompanyProfile | None = None,
        name: str | None = None,
    ) -> CompanyWorkspace:
        return self.repository.update_for_organization(
            account_id=account_id,
            organization_id=organization_id,
            company_id=company_id,
            profile=profile,
            name=name,
        )

    def delete_for_organization(
        self,
        account_id: int,
        organization_id: int,
        company_id: int,
    ) -> None:
        return self.repository.delete_for_organization(
            account_id=account_id,
            organization_id=organization_id,
            company_id=company_id,
        )
