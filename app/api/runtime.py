"""Composition root shared by FastAPI endpoints.

Every optional component is loaded independently so `/health` can report a
safe degraded state instead of crashing the whole service.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.database import TenderRepository
    from app.llm.base import LLMProvider
    from app.monitoring import TenderMonitorService
    from app.rag.service import RagService
    from app.scoring.models import CompanyProfile
    from app.companies import CompanyService
    from app.auth import AuthService
    from app.organizations import OrganizationService
    from app.sources import SourceCatalog
    from app.support import SupportRepository


@dataclass
class ApiRuntime:
    provider: "LLMProvider | Any | None" = None
    tender_max_chars: int = 20000
    company_profile: "CompanyProfile | Any | None" = None
    company_service: "CompanyService | Any | None" = None
    auth_service: "AuthService | Any | None" = None
    email_sender: "Any | None" = None
    organization_service: "OrganizationService | Any | None" = None
    tender_repository: "TenderRepository | Any | None" = None
    rag_service: "RagService | Any | None" = None
    monitoring_service: "TenderMonitorService | Any | None" = None
    tender_discovery_service: "TenderMonitorService | Any | None" = None
    source_catalog: "SourceCatalog | Any | None" = None
    support_repository: "SupportRepository | Any | None" = None
    database: "Any | None" = None
    component_errors: dict[str, str] = field(default_factory=dict)

    def component_status(self) -> dict[str, str]:
        database = self.database or getattr(self.tender_repository, "database", None)
        return {
            "database": "ready" if self.tender_repository is not None and (database is None or database.healthy()) else "unavailable",
            "llm": "ready" if self.provider is not None else "unavailable",
            "scoring": "ready" if (self.company_profile is not None or self.company_service is not None) else "unavailable",
            "companies": "ready" if self.company_service is not None else "unavailable",
            "auth": "ready" if self.auth_service is not None else "unavailable",
            "organizations": "ready" if self.organization_service is not None else "unavailable",
            "rag": "ready" if self.rag_service is not None else "unavailable",
            "monitoring": "ready" if self.monitoring_service is not None else "unavailable",
            "discovery": "ready" if self.tender_discovery_service is not None else "unavailable",
            "sources": "ready" if self.source_catalog is not None else "unavailable",
            "support": "ready" if self.support_repository is not None else "unavailable",
        }

    def close(self):
        if self.database is not None:
            self.database.close()


def build_runtime() -> ApiRuntime:
    runtime = ApiRuntime()

    from app.database import load_database_settings
    from app.database.backend import Database, StorageError

    # Fail closed for invalid configuration and failed PostgreSQL initialization.
    # No component may reinterpret a PostgreSQL URL as a local SQLite path.
    db_settings = load_database_settings()
    runtime.database = Database(db_settings)
    if runtime.database.backend == "postgresql":
        try:
            runtime.database.migrate()
        except Exception:
            runtime.close()
            raise StorageError("VALYQON AI database startup failed.") from None

    try:
        from app.llm.config import load_settings as load_llm_settings
        from app.llm.gigachat import GigaChatProvider
        from app.services.tender_analysis import configured_max_chars

        runtime.tender_max_chars = configured_max_chars()
        runtime.provider = GigaChatProvider(load_llm_settings())
    except Exception:
        runtime.component_errors["llm"] = "LLM configuration unavailable"

    try:
        from app.scoring.config import load_company_profile

        runtime.company_profile = load_company_profile()
    except Exception:
        runtime.component_errors["scoring"] = "Company profile unavailable"

    try:
        from app.database import TenderRepository

        repository = TenderRepository(runtime.database)
        repository.initialize()
        runtime.tender_repository = repository
    except Exception:
        runtime.component_errors["database"] = "Database unavailable"

    try:
        from app.companies import CompanyRepository, CompanyService

        db_path = runtime.database
        company_repository = CompanyRepository(db_path)
        company_repository.initialize()
        runtime.company_service = CompanyService(company_repository, fallback_profile=runtime.company_profile)
    except Exception:
        runtime.component_errors["companies"] = "Company workspaces unavailable"

    try:
        from app.auth import AuthRepository, AuthService

        db_path = runtime.database
        auth_repository = AuthRepository(db_path)
        auth_repository.initialize()
        runtime.auth_service = AuthService(auth_repository)
    except Exception:
        runtime.component_errors["auth"] = "Authentication unavailable"

    try:
        from app.auth.email_delivery import (
            load_email_sender_from_env,
        )

        runtime.email_sender = (
            load_email_sender_from_env()
        )

        if runtime.email_sender is None:
            runtime.component_errors[
                "email"
            ] = "Email delivery not configured"

    except Exception:
        runtime.component_errors[
            "email"
        ] = "Email delivery unavailable"

    try:
        from app.support import SupportRepository

        db_path = runtime.database

        support_repository = SupportRepository(
            db_path
        )

        support_repository.initialize()

        runtime.support_repository = (
            support_repository
        )

    except Exception:
        runtime.component_errors[
            "support"
        ] = "Support Center unavailable"

    try:
        from app.organizations import OrganizationRepository, OrganizationService

        if runtime.auth_service is None:
            raise RuntimeError("Authentication unavailable")

        organization_repository = OrganizationRepository(
            runtime.database
        )
        organization_repository.initialize()
        runtime.organization_service = OrganizationService(
            organization_repository
        )
    except Exception:
        runtime.component_errors["organizations"] = "Organizations unavailable"

    try:
        from app.rag import RagService, load_rag_settings

        rag_settings = load_rag_settings()
        if rag_settings.enabled:
            runtime.rag_service = RagService(rag_settings)
        else:
            runtime.component_errors["rag"] = "RAG disabled"
    except Exception:
        runtime.component_errors["rag"] = "RAG unavailable"

    monitor_settings = None

    try:
        from app.monitoring import load_monitoring_settings
        from app.sources import build_source_catalog

        monitor_settings = load_monitoring_settings()
        runtime.source_catalog = build_source_catalog(monitor_settings)
    except Exception:
        runtime.component_errors["sources"] = "Source catalog unavailable"

    try:
        from app.monitoring import MonitoringRepository, TenderMonitorService

        if monitor_settings is None or runtime.source_catalog is None:
            raise RuntimeError("Source catalog unavailable")

        eis_registration = (
            runtime.source_catalog.registry.get(
                "eis"
            )
        )

        db_path = runtime.database

        repository = MonitoringRepository(
            db_path
        )
        repository.initialize()

        runtime.tender_discovery_service = TenderMonitorService(
            monitor_settings,
            eis_registration.source,
            repository,
            runtime.company_profile,
            profile_resolver=(
                runtime.company_service.profile_for_owner
                if runtime.company_service
                else None
            ),
            scope_resolver=(
                runtime.company_service.scope_for_owner
                if runtime.company_service
                else None
            ),
        )

        # Background subscription monitoring remains EIS-only.
        if eis_registration.enabled:
            runtime.monitoring_service = (
                runtime.tender_discovery_service
            )
        else:
            runtime.component_errors["monitoring"] = (
                "EIS monitoring source not configured"
            )
    except Exception:
        runtime.component_errors["discovery"] = (
            "Tender discovery unavailable"
        )
        runtime.component_errors["monitoring"] = (
            "Monitoring unavailable"
        )

    return runtime
