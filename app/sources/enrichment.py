"""Additive v1 public-field provenance. Never copy credentials or whole payloads."""
from dataclasses import replace
from datetime import datetime, timezone
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.analytics.normalization import normalize_countries
from app.analytics.dates import normalize_date
from app.analytics.taxonomies import normalize_classifications


class NoticeEnrichment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal[1] = 1
    normalizer_version: Literal['notice-enrichment-v1'] = 'notice-enrichment-v1'
    adapter_version: str
    source: str
    external_id: str
    observed_at: str
    connector_version: str | None = None
    country: dict[str, Any]
    classification: dict[str, Any]
    dates: dict[str, Any] = Field(default_factory=dict)
    scoring_provenance: Literal['unavailable_in_source_notice'] = 'unavailable_in_source_notice'
    public_metadata: dict[str, Any] | None = None

    @model_validator(mode='after')
    def validate_evidence(self):
        observed = datetime.fromisoformat(self.observed_at)
        if observed.tzinfo is None:
            raise ValueError('Enrichment observation must have an offset.')
        if len(json.dumps(self.model_dump(), allow_nan=False)) > 65536:
            raise ValueError('Enrichment exceeds 64 KiB.')
        locations = {}
        country_entries = self.country.get('evidence', [])
        if not isinstance(country_entries, list):
            raise ValueError('Invalid country evidence.')
        for entry in country_entries:
            if (not isinstance(entry, dict) or not {'location', 'path', 'value'} <= entry.keys()
                    or type(entry['location']) is not int or entry['location'] < 0
                    or not isinstance(entry['path'], str)):
                raise ValueError('Invalid country evidence.')
            locations.setdefault(entry['location'], []).append({'path': entry['path'], 'value': entry['value']})
        if self.country != normalize_countries(list(locations.values())):
            raise ValueError('Country evidence mismatch.')
        raw_entries = self.classification.get('entries', [])
        if not isinstance(raw_entries, list) or any(
            not isinstance(entry, dict) or not {'scheme', 'code', 'path', 'role'} <= entry.keys()
            or not isinstance(entry['path'], str) or not isinstance(entry['role'], str)
            or entry['role'] not in {'reported', 'primary', 'secondary'}
            for entry in raw_entries
        ):
            raise ValueError('Invalid classification evidence.')
        entries = [{key: value for key, value in entry.items() if key not in {'status', 'canonical_label'}}
                   for entry in raw_entries]
        if self.classification != normalize_classifications(entries, version=self.classification.get('version')):
            raise ValueError('Classification evidence mismatch.')
        for key, entry in self.dates.items():
            if isinstance(entry, dict) and 'normalized' in entry:
                if key not in {'publication', 'deadline'} or not isinstance(entry.get('path'), str):
                    raise ValueError('Invalid date evidence.')
                if not isinstance(entry['normalized'], dict):
                    raise ValueError('Invalid normalized date contract.')
                if entry['normalized'].get('version') != 'source-date-v1':
                    # Preserve future/unknown metadata; consumers fail unavailable.
                    continue
                expected = normalize_date(entry.get('value'), source=self.source, path=entry['path'],
                    field='published_at' if key == 'publication' else 'deadline',
                    semantics=entry.get('semantics')).model_dump(mode='json')
                if entry['normalized'] != expected:
                    raise ValueError('Date evidence mismatch.')
        return self


def enrichment(source, external_id, *, locations=(), classifications=(), dates=None, public_metadata=None):
    return NoticeEnrichment(
        source=source, external_id=external_id, adapter_version=f'{source}:metadata-r1',
        observed_at=datetime.now(timezone.utc).isoformat(),
        country=normalize_countries(locations),
        classification=normalize_classifications(classifications),
        public_metadata=public_metadata,
        dates={key: {**entry, 'status': 'missing' if entry.get('value') is None else 'reported_unparsed',
                    'normalized': normalize_date(entry.get('value'), source=source, path=entry['path'],
                        field='published_at' if key == 'publication' else 'deadline',
                        semantics=entry.get('semantics')).model_dump(mode='json')}
               for key, entry in (dates or {}).items()},
    ).model_dump(exclude={'public_metadata'} if public_metadata is None else set())


def validate_enrichment(value, source, external_id):
    parsed = NoticeEnrichment.model_validate(value)
    if (parsed.source, parsed.external_id) != (source, external_id):
        raise ValueError('Enrichment identity mismatch.')
    return parsed


def with_connector(notice, version):
    if notice.enrichment is None:
        return notice
    validate_enrichment(notice.enrichment, notice.source, notice.external_id)
    return replace(notice, enrichment={**notice.enrichment, 'connector_version': version})
