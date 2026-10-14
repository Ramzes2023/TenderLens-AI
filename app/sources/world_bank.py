"""Official Finances One DS00979/RS00909 bounded public procurement feed."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
import math
from urllib.parse import urlsplit

import httpx

from .http import source_client
from .international import official_url, source_date, closed, request_json, diagnostic, retryable, english_day
from .models import TenderNotice
from .enrichment import enrichment

WORLD_BANK_URL = 'https://datacatalogapi.worldbank.org/dexapps/fone/api/apiservice'


class WorldBankSourceError(RuntimeError):
    pass


def parse_world_bank_response(payload, *, now=None, recent_from=None):
    if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
        raise WorldBankSourceError('World Bank returned an invalid data envelope.')
    now = now or datetime.now(timezone.utc)
    notices, seen = [], set()
    for raw in payload['data']:
        if not isinstance(raw, dict):
            raise WorldBankSourceError('World Bank returned an invalid record.')
        identity = raw.get('id')
        title = raw.get('bid_description')
        if isinstance(identity, bool) or not re.fullmatch(r'\d{1,30}', str(identity)):
            raise WorldBankSourceError('World Bank returned an invalid notice identity/title.')
        if not isinstance(title, str) or not title.strip():
            continue  # Sparse dataset rows cannot form a discovery opportunity.
        identity = str(identity)
        try:
            url = official_url(raw.get('url'), {'projects.worldbank.org'})
            if not re.fullmatch(r'/en/projects-operations/procurement-detail/OP\d+', urlsplit(url).path):
                raise ValueError('Unexpected notice path.')
            publication = source_date(raw.get('publication_date'))
            deadline = source_date(raw.get('deadline_date'))
        except ValueError:
            raise WorldBankSourceError('World Bank returned an invalid date or reference URL.') from None
        # A deadline is required to claim a currently actionable World Bank notice.
        if (not deadline or closed(deadline, now=now) or not publication
                or publication[:10] > now.date().isoformat()
                or recent_from and publication[:10] < recent_from):
            continue
        kind = str(raw.get('notice_type') or '').casefold()
        if any(word in kind for word in ('award', 'cancel', 'general procurement')):
            continue
        if identity in seen:
            continue
        seen.add(identity)
        notices.append(TenderNotice(
            source='world_bank', external_id=identity, title=' '.join(title.split())[:1000],
            url=url, published_at=publication, deadline=deadline,
            tender_number=str(raw.get('project_id'))[:500] if raw.get('project_id') else None,
            region=raw.get('country_name'),
            summary='; '.join(str(raw[key]) for key in ('notice_type', 'procurement_category', 'sector') if raw.get(key))[:4000] or None,
            enrichment=enrichment('world_bank', identity,
                public_metadata={'attribution': 'World Bank Group / Finances One',
                                 'license': 'CC BY 4.0', 'reference_url': url,
                                 'original_language': None, 'project_id': raw.get('project_id'),
                                 'notice_type': raw.get('notice_type'), 'sector': raw.get('sector'),
                                 'procurement_category': raw.get('procurement_category'),
                                 'raw_publication_date': raw.get('publication_date'),
                                 'raw_deadline_date': raw.get('deadline_date')},
                locations=[[{'path': key, 'value': raw[key]} for key in ('country_code', 'country_name') if raw.get(key)]],
                dates={'publication': {'path': 'publication_date', 'value': publication},
                       'deadline': {'path': 'deadline_date', 'value': deadline}}),
        ))
    return notices


@dataclass(frozen=True)
class WorldBankSource:
    timeout: float = 20.0
    name: str = 'world_bank'

    def __post_init__(self):
        if not math.isfinite(self.timeout) or not 0 < self.timeout <= 120:
            raise ValueError('timeout must be finite and between 0 and 120 seconds.')

    async def fetch(self, limit=20):
        limit = max(1, min(int(limit), 100))
        now = datetime.now(timezone.utc)
        start = english_day(now - timedelta(days=6))
        end = english_day(now)
        # Official API Explorer generates SQL-style filter predicates, not one
        # query parameter per field (the service silently ignores those).
        params = {'datasetId': 'DS00979', 'resourceId': 'RS00909', 'type': 'json',
                  'top': 100, 'filter': f"publication_date>='{start}' and publication_date<='{end}'"}
        records = []
        try:
            async with source_client(timeout=self.timeout, trust_env=False, follow_redirects=False,
                                     headers={'Accept': 'application/json', 'User-Agent': 'VALYQON-AI (+procurement-source)'}) as client:
                for page in range(2):
                    params['skip'] = page * 100
                    payload = await request_json(client, 'GET', WORLD_BANK_URL,
                                                 hosts={'datacatalogapi.worldbank.org'}, params=params)
                    if not isinstance(payload.get('data'), list):
                        raise WorldBankSourceError('World Bank returned an invalid data envelope.')
                    records.extend(payload['data'])
                    if len(payload['data']) < 100:
                        break
        except (httpx.HTTPError, OSError, ValueError) as error:
            failure = WorldBankSourceError('Unable to fetch World Bank notices. ' + diagnostic(error))
            failure.retryable = retryable(error)
            raise failure from None
        return parse_world_bank_response({'data': records}, now=now,
            recent_from=(now - timedelta(days=6)).date().isoformat())[:limit]
