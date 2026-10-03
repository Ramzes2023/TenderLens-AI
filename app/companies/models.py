"""Multi-company workspace models.

A Telegram user may own several independent company profiles and choose one as
active. The active profile drives scoring and source monitoring for that user.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.scoring.models import CompanyProfile


class CompanyWorkspace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    owner_user_id: int = Field(gt=0)
    organization_id: int | None = Field(default=None, gt=0)
    name: str = Field(min_length=1, max_length=200)
    profile: CompanyProfile
    is_active: bool = False
    created_at: str
    updated_at: str


class CompanyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_user_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    profile: CompanyProfile
    make_active: bool = True
