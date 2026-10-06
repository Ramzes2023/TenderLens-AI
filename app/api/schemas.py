"""HTTP request/response schemas for Phase 10."""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.tender import TenderAnalysis
from app.scoring.models import CompanyProfile, ScoringResult

PositiveId = Annotated[int, Field(gt=0)]
Hash64 = Annotated[str, Field(pattern=r"^[0-9a-fA-F]{64}$")]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    components: dict[str, str]


class TenderListItem(BaseModel):
    id: int
    source_filename: str
    pdf_sha256: str
    pages: int | None
    title: str | None
    tender_number: str | None
    customer: str | None
    initial_price: float | None
    currency: str | None
    fit_score: float | None
    created_at: str
    updated_at: str


class TenderDetail(BaseModel):
    id: int
    owner_user_id: int
    source_filename: str
    pdf_sha256: str
    pages: int | None
    characters: int
    analysis_truncated: bool
    analysis: TenderAnalysis
    scoring: ScoringResult | None
    created_at: str
    updated_at: str


class RagAskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_user_id: PositiveId
    pdf_sha256: Hash64
    question: Annotated[str, Field(min_length=1, max_length=2000)]


class RagSource(BaseModel):
    page_number: int
    chunk_index: int
    score: float


class RagAskResponse(BaseModel):
    answer: str
    sources: list[RagSource]


class MonitorStatusResponse(BaseModel):
    background_enabled: bool
    interval_seconds: int
    rss_feeds: int
    subscription_enabled: bool
    active_company: str | None = None
    feed_mode: str = "static"


class MonitorScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_user_id: PositiveId


class MonitorNoticeResponse(BaseModel):
    source: str
    external_id: str
    title: str
    url: str
    tender_number: str | None = None
    customer: str | None = None
    initial_price: float | None = None
    currency: str | None = None
    deadline: str | None = None
    region: str | None = None
    reasons: list[str]


class TenderDiscoveryItem(MonitorNoticeResponse):
    published_at: str | None = None
    summary: str | None = None
    analysis_stage: str = "metadata_preview"
    metadata_analysis: TenderAnalysis
    preliminary_scoring: ScoringResult
    full_ai_analyzed: bool = False


class TenderDiscoveryResponse(BaseModel):
    items: list[TenderDiscoveryItem]
    attempted_sources: list[str]
    successful_sources: list[str]
    failed_sources: list[str]
    partial_failure: bool
    total_failure: bool
    history_id: int | None = None


class PdfAnalysisResponse(BaseModel):
    duplicate: bool
    record_id: int
    pdf_sha256: str
    source_filename: str
    pages: int | None
    characters: int
    analysis_truncated: bool
    analysis: TenderAnalysis
    scoring: ScoringResult | None
    rag_indexed_chunks: int | None = None
    warnings: list[str] = Field(default_factory=list)


class CompanyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_user_id: PositiveId
    name: Annotated[str, Field(min_length=1, max_length=200)]
    profile: CompanyProfile
    make_active: bool = True


class CompanyActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_user_id: PositiveId


class CompanyResponse(BaseModel):
    id: int
    owner_user_id: int
    name: str
    profile: CompanyProfile
    is_active: bool
    created_at: str
    updated_at: str
