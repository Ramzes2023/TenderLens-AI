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


@dataclass
class ApiRuntime:
    provider: "LLMProvider | Any | None" = None
    tender_max_chars: int = 20000
    company_profile: "CompanyProfile | Any | None" = None
    company_service: "CompanyService | Any | None" = None
    tender_repository: "TenderRepository | Any | None" = None
    rag_service: "RagService | Any | None" = None
    monitoring_service: "TenderMonitorService | Any | None" = None
    component_errors: dict[str, str] = field(default_factory=dict)

    def component_status(self) -> dict[str, str]:
        return {
            "database": "ready" if self.tender_repository is not None else "unavailable",
            "llm": "ready" if self.provider is not None else "unavailable",
            "scoring": "ready" if (self.company_profile is not None or self.company_service is not None) else "unavailable",
            "companies": "ready" if self.company_service is not None else "unavailable",
            "rag": "ready" if self.rag_service is not None else "unavailable",
            "monitoring": "ready" if self.monitoring_service is not None else "unavailable",
        }


def build_runtime() -> ApiRuntime:
    runtime = ApiRuntime()

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
        from app.database import TenderRepository, load_database_settings

        db_settings = load_database_settings()
        repository = TenderRepository(db_settings.path)
        repository.initialize()
        runtime.tender_repository = repository
    except Exception:
        runtime.component_errors["database"] = "Database unavailable"

    try:
        from app.companies import CompanyRepository, CompanyService
        from app.database import load_database_settings

        db_path = (
            runtime.tender_repository.path
            if runtime.tender_repository is not None
            else load_database_settings().path
        )
        company_repository = CompanyRepository(db_path)
        company_repository.initialize()
        runtime.company_service = CompanyService(company_repository, fallback_profile=runtime.company_profile)
    except Exception:
        runtime.component_errors["companies"] = "Company workspaces unavailable"

    try:
        from app.rag import RagService, load_rag_settings

        rag_settings = load_rag_settings()
        if rag_settings.enabled:
            runtime.rag_service = RagService(rag_settings)
        else:
            runtime.component_errors["rag"] = "RAG disabled"
    except Exception:
        runtime.component_errors["rag"] = "RAG unavailable"

    try:
        from app.database import load_database_settings
        from app.monitoring import MonitoringRepository, TenderMonitorService, load_monitoring_settings
        from app.sources import EisRssSource

        monitor_settings = load_monitoring_settings()
        if monitor_settings.source_configured:
            db_path = (
                runtime.tender_repository.path
                if runtime.tender_repository is not None
                else load_database_settings().path
            )
            repository = MonitoringRepository(db_path)
            repository.initialize()
            source = EisRssSource(
                urls=monitor_settings.eis_rss_urls,
                timeout=monitor_settings.request_timeout,
                ca_bundle_file=monitor_settings.ca_bundle_file,
            )
            runtime.monitoring_service = TenderMonitorService(
                monitor_settings, source, repository, runtime.company_profile,
                profile_resolver=(runtime.company_service.profile_for_owner if runtime.company_service else None),
                scope_resolver=(runtime.company_service.scope_for_owner if runtime.company_service else None),
            )
        else:
            runtime.component_errors["monitoring"] = "EIS RSS source not configured"
    except Exception:
        runtime.component_errors["monitoring"] = "Monitoring unavailable"

    return runtime
