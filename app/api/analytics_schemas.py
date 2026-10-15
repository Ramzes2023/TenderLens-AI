"""Public allowlist: no stored tender bodies, connector payloads or credentials."""
from typing import Literal
from pydantic import BaseModel, ConfigDict


class PublicModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Capability(PublicModel):
    state: Literal['available', 'unavailable']
    reason: str | None = None


class PopulationContract(PublicModel):
    version: Literal['company-analytics-v1'] = 'company-analytics-v1'
    population_id: str
    origin: Literal['H'] = 'H'
    organization_id: int
    company_id: int
    selected_event_ids: list[int]
    selected_run_ids: list[str] = []
    time_field: Literal['search_created_at'] = 'search_created_at'
    start: str | None
    end: str | None
    interval: Literal['[start,end)'] = '[start,end)'
    as_of: str
    retrieval_as_of: str
    watermark: int
    versions: dict[str, str | list[str]]
    profile_trust_mode: Literal['historical_preview_at_search_time'] = 'historical_preview_at_search_time'
    current_profile_digest: str
    timezone: str
    timezone_available: bool
    deadline_days: int
    filters: dict[str, str | None]
    coverage: str
    source_search_coverage: str
    observed_events: int
    union_count: int
    filtered_count: int
    unknown_fit_count: int
    unknowns: dict[str, int]
    exclusions: dict[str, int]
    lifetime_total: None = None
    capabilities: dict[str, Capability]


class Measure(PublicModel):
    value: int | None
    numerator: int
    denominator: int
    identities: list[tuple[str, str] | str]
    coverage: str
    reason: str | None
    time_field: str
    unit: str


class Distribution(PublicModel):
    key: list[str]
    measure: Measure


class AnalyticsRow(PublicModel):
    row_id: str
    identity: tuple[str, str]
    event_id: int
    ordinal: int
    snapshot_sha256: str
    historical_fit_band: str
    historical_fit_score: float | None
    historical_fit_reason: str | None
    current_fit_band: str
    current_fit_reason: str | None
    # Full analysis is deliberately absent: tender identity is not an immutable binding.


class AnalyticsResponse(PublicModel):
    population: PopulationContract
    population_token: str
    kpis: dict[str, Measure]
    drilldowns: dict[str, list[tuple[str, str]]]
    distributions: dict[str, list[Distribution]]
    deadline_buckets: list[Distribution]
    search_activity: dict[str, list[tuple[str, str]]]
    metadata_counts: dict[str, int | float | None]
    source_observations: dict[str, dict[str, int | float | None]]
    rows: list[AnalyticsRow]
    total: int
    next_cursor: str | None
    order: Literal['identity', 'top']


class CapabilityResponse(PublicModel):
    version: Literal['company-analytics-v1'] = 'company-analytics-v1'
    organization_id: int
    company_id: int
    origin: Literal['D', 'R', 'P']
    capability: Capability
