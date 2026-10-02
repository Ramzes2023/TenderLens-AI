"""Deterministic company-profile scoring models."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, max_length=500)]
KeywordList = Annotated[list[Text], Field(max_length=100)]
Percent = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
Money = Annotated[float, Field(gt=0, allow_inf_nan=False)]
NonNegativeMoney = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class CompanyProfile(BaseModel):
    """Versioned business constraints used by the deterministic scorer."""

    model_config = ConfigDict(extra="forbid")

    profile_version: Text
    company_name: Text
    business_mode: Literal["sell", "buy", "both"] = "sell"
    industry: Text | None = None
    product_keywords: KeywordList = Field(default_factory=list)
    search_keywords: KeywordList = Field(default_factory=list)
    excluded_keywords: KeywordList = Field(default_factory=list)
    allowed_regions: KeywordList = Field(default_factory=list)
    allowed_countries: KeywordList = Field(default_factory=list)
    accepted_currencies: KeywordList = Field(default_factory=lambda: ["RUB"])
    min_contract_value: NonNegativeMoney | None = None
    max_contract_value: Money | None = None
    max_bid_security_percent: Percent | None = None
    max_contract_security_percent: Percent | None = None
    available_document_keywords: KeywordList = Field(default_factory=list)

    hard_stop_on_region: bool = True
    hard_stop_on_budget: bool = True
    hard_stop_on_currency: bool = True
    hard_stop_on_bid_security: bool = False
    hard_stop_on_contract_security: bool = False

    @model_validator(mode="after")
    def validate_budget_range(self):
        if (self.min_contract_value is not None and self.max_contract_value is not None
                and self.min_contract_value > self.max_contract_value):
            raise ValueError("min_contract_value не может превышать max_contract_value")
        return self

    @property
    def monitoring_keywords(self) -> list[str]:
        """Search vocabulary used by source adapters; product keywords remain scoring truth."""
        return self.search_keywords or self.product_keywords

CriterionStatus = Literal["matched", "partial", "failed", "not_scored"]


class CriterionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Text
    label: Text
    weight: Annotated[int, Field(ge=0, le=100)]
    earned_points: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
    status: CriterionStatus
    explanation: Annotated[str, Field(min_length=1, max_length=2000)]
    evidence: Annotated[list[str], Field(max_length=30)] = Field(default_factory=list)


class ScoringResult(BaseModel):
    """Fit is deterministic profile compatibility, never win probability."""

    model_config = ConfigDict(extra="forbid")

    profile_name: Text
    profile_version: Text
    fit_score: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)] | None
    scorable_weight: Annotated[int, Field(ge=0, le=100)]
    completeness_percent: Annotated[int, Field(ge=0, le=100)]
    criteria: list[CriterionResult]
    stop_factors: list[str] = Field(default_factory=list)
    document_risks: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
