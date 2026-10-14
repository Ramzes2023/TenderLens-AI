"""Immutable preliminary relevance policy; no I/O, rescore or probability inference."""
from dataclasses import dataclass
from datetime import datetime
import math
import re

from pydantic import BaseModel, ConfigDict
from app.scoring.preview import PREVIEW_ENGINE_VERSION

FIT_POLICY_VERSION = 'preliminary-fit-v1'
PREVIEW_STAGE = 'metadata_preview'


class PreviewProvenance(BaseModel):
    """Evidence sidecar, not an authorization token. Unknown future fields survive."""
    model_config = ConfigDict(frozen=True, extra='allow', strict=True)
    organization_id: int
    company_id: int
    profile_digest: str
    engine_version: str
    scoring_policy_version: str
    scoring_stage: str
    scored_at: str


@dataclass(frozen=True)
class VerifiedFitContext:
    """Server-only scope after membership/company checks; never deserialize clients.

    trusted_snapshot means server-generated Discover or scoped discovery-history,
    never the client-submitted Saved snapshot. Profile digest is read from the
    authorized current profile. This value does not itself perform authorization.
    """
    organization_id: int
    company_id: int
    current_profile_digest: str
    trusted_snapshot: bool = False


@dataclass(frozen=True)
class FitClassification:
    raw_score: object
    eligible: bool
    band: str
    matched: bool | None
    high_fit: bool | None
    reason: str | None
    basis: str
    policy_version: str = FIT_POLICY_VERSION


def classify_preliminary_fit(score, *, stage=None, provenance=None, context=None,
                             historical=False):
    """Classify only eligible values, preserving raw input even when unknown.

    Historical mode requires a trusted scoped snapshot and an explicitly stored
    preview stage, but allows missing old digest/engine/policy. Present conflicting
    versions fail closed. Current mode requires all immutable evidence and digest
    equality. All bands/matched predicates therefore share one eligible denominator.
    """
    basis = 'historical preview at search time' if historical else 'current profile preview'

    def unknown(reason):
        return FitClassification(score, False, 'unknown', None, None, reason, basis)

    if type(score) not in (int, float):
        return unknown('missing_or_malformed_score')
    try:
        if not math.isfinite(score) or not 0 <= score <= 90:
            return unknown('nonfinite_or_out_of_range')
    except OverflowError:
        return unknown('nonfinite_or_out_of_range')
    if stage != PREVIEW_STAGE:
        return unknown('unknown_or_nonpreview_stage')
    if not isinstance(context, VerifiedFitContext) or not context.trusted_snapshot:
        return unknown('untrusted_origin')
    if provenance is not None:
        if not isinstance(provenance, PreviewProvenance):
            return unknown('malformed_provenance')
        if (provenance.organization_id, provenance.company_id) != (
                context.organization_id, context.company_id):
            return unknown('scope_mismatch')
        if provenance.scoring_stage != PREVIEW_STAGE:
            return unknown('stage_conflict')
        if (provenance.engine_version != PREVIEW_ENGINE_VERSION or
                provenance.scoring_policy_version != FIT_POLICY_VERSION):
            return unknown('version_conflict')
    if not historical:
        if provenance is None:
            return unknown('missing_provenance')
        if not re.fullmatch('[a-f0-9]{64}', provenance.profile_digest):
            return unknown('missing_or_invalid_profile_digest')
        if provenance.profile_digest != context.current_profile_digest:
            return unknown('stale_profile_digest')
        try:
            instant = datetime.fromisoformat(provenance.scored_at.replace('Z', '+00:00'))
            if instant.utcoffset() is None:
                return unknown('unknown_scoring_time')
        except (ValueError, TypeError):
            return unknown('unknown_scoring_time')
    band = 'low' if score < 35 else 'medium' if score < 65 else 'high'
    return FitClassification(score, True, band, score >= 35, score >= 65, None, basis)


def classify_discovery_fit(item, *, context, historical=False):
    """Never substitute full_scoring or a schema-injected legacy stage default."""
    stage = item.analysis_stage if 'analysis_stage' in item.model_fields_set else None
    return classify_preliminary_fit(item.preliminary_scoring.fit_score, stage=stage,
                                    provenance=item.preliminary_provenance,
                                    context=context, historical=historical)
