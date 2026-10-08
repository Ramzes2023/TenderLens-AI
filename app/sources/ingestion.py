"""Explicit approved public-source ingestion on the durable queue."""
from app.observability import observe
import asyncio
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from dataclasses import replace

import httpx

from app.database.backend import StorageError, StorageIntegrityError
from app.jobs.models import JobScope
from app.jobs.worker import PermanentJobError, RetryableJobError
from .eis_rss import SourceError
from .http import ConnectorTransportError, FetchPolicy, bounded_fetch
from .opportunities import validate_notice
from .registry import SourceRegistryError

JOB_TYPE = 'connector.sync.v1'
SYSTEM_SCOPE = JobScope()
# Explicit server-owned hosts. EIS custom operator URLs remain supported by live
# discovery; worker ingestion deliberately only permits the official EIS host.
HOSTS = {
    'eis': frozenset({'zakupki.gov.ru', 'www.zakupki.gov.ru'}),
    'ted': frozenset({'api.ted.europa.eu'}),
    'sam_gov': frozenset({'api.sam.gov'}),
    'uk_fts': frozenset({'www.find-tender.service.gov.uk'}),
    'canada_buys': frozenset({'canadabuys.canada.ca'}),
    'austender': frozenset({'www.tenders.gov.au', 'tenders.gov.au'}),
    'nz_gets': frozenset({'www.gets.govt.nz'}),
    'za_etenders': frozenset({'admin.etenders.gov.za'}),
    'india_cppp': frozenset({'eprocure.gov.in'}),
    'kz_goszakup': frozenset({'ows.goszakup.gov.kz'}),
}


def connector_version(source_id):
    return f'connector-sync-v1:{source_id}:adapter-r1'


def sync_window(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('UTC-aware sync time required.')
    return now.astimezone(timezone.utc).strftime('%Y-%m-%dT%HZ')


def load_max_records():
    value = int(os.environ.get('VALYQON_CONNECTOR_MAX_RECORDS', '20'))
    if not 1 <= value <= 100:
        raise ValueError('Invalid connector record bound.')
    return value


def validate_payload(payload, registry):
    if (type(payload) is not dict or set(payload) != {'schema', 'source_id', 'sync_window', 'connector_version'}
            or type(payload['schema']) is not int or payload['schema'] != 1):
        raise PermanentJobError('Invalid connector payload.')
    source = payload['source_id']
    window = payload['sync_window']
    if type(source) is not str or not re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}', source):
        raise PermanentJobError('Invalid source identity.')
    if type(window) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}Z', window):
        raise PermanentJobError('Invalid sync window.')
    try:
        datetime.strptime(window, '%Y-%m-%dT%HZ')
        registration = registry.get(source)
    except (ValueError, SourceRegistryError):
        raise PermanentJobError('Invalid connector routing.') from None
    if source not in HOSTS or not registration.enabled or payload['connector_version'] != connector_version(source):
        raise PermanentJobError('Unsupported connector configuration.')
    if source == 'eis' and hasattr(registration.source, 'urls') and not registration.source.urls:
        raise PermanentJobError('Static EIS feeds required for shared ingestion.')
    return registration


class ConnectorSyncService:
    def __init__(self, jobs, catalog):
        self.jobs, self.catalog = jobs, catalog

    def enqueue(self, source_id, *, now=None):
        # No caller-supplied window, endpoint, profile or credential. Clock injection
        # is an in-process test seam; the operator CLI always uses the current slot.
        payload = {'schema': 1, 'source_id': source_id, 'sync_window': sync_window(now),
                   'connector_version': connector_version(source_id)}
        validate_payload(payload, self.catalog.registry)
        identity = json.dumps([source_id, payload['sync_window'], payload['connector_version']], separators=(',', ':'))
        return self.jobs.enqueue(JOB_TYPE, payload, scope=SYSTEM_SCOPE, idempotency_key=identity)

    def status(self, job_id):
        try:
            if type(job_id) is not str or len(job_id) != 36 or str(uuid.UUID(job_id)) != job_id:
                return None
        except ValueError:
            return None
        job = self.jobs.get(job_id, scope=SYSTEM_SCOPE)
        if job is None or job.job_type != JOB_TYPE:
            return None
        return {'job_id': job.id, 'state': job.state, 'result': job.result, 'failure_code': job.failure_code}


class ConnectorSyncHandler:
    def __init__(self, catalog, opportunities, *, max_records=20):
        if type(max_records) is not int or not 1 <= max_records <= 100:
            raise ValueError('Invalid connector record bound.')
        self.catalog, self.opportunities, self.max_records = catalog, opportunities, max_records

    @observe("connector.sync")
    def __call__(self, context, payload):
        if context.job.scope != SYSTEM_SCOPE:
            raise PermanentJobError('Connector requires system scope.')
        registration = validate_payload(payload, self.catalog.registry)
        source_id = registration.key
        source = registration.source
        if source_id == 'austender' and hasattr(source, 'max_concurrency'):
            source = replace(source, max_concurrency=1)
        # At most five listing/feed requests; AusTender adds one detail per notice.
        request_limit = (self.max_records + 1 if source_id == 'austender'
                         else 5 if source_id in {'eis', 'india_cppp', 'kz_goszakup'} else 1)
        async def fetch():
            with bounded_fetch(FetchPolicy(HOSTS[source_id], request_limit)):
                return await asyncio.wait_for(source.fetch(self.max_records), timeout=180)
        try:
            notices = asyncio.run(fetch())
        except ConnectorTransportError as error:
            kind = RetryableJobError if error.retryable else PermanentJobError
            raise kind('Connector fetch failed.') from None
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            kind = RetryableJobError if status in (408, 429) or 500 <= status <= 599 else PermanentJobError
            raise kind('Connector fetch failed.') from None
        except (TimeoutError, httpx.TransportError, OSError):
            raise RetryableJobError('Connector unavailable.') from None
        except (SourceError, ValueError, TypeError):
            raise PermanentJobError('Connector schema/configuration failed.') from None
        if type(notices) is not list or len(notices) > self.max_records:
            raise PermanentJobError('Connector exceeded result contract.')
        result = {'schema': 1, 'source_id': source_id, 'sync_window': payload['sync_window'],
                  'fetched_count': len(notices), 'accepted_count': 0, 'skipped_count': 0,
                  'inserted_count': 0, 'updated_count': 0}
        seen = set()
        for notice in notices:
            if context.should_stop:
                raise RetryableJobError('Connector interrupted.')
            try:
                validate_notice(notice, source_id)
            except (ValueError, TypeError, OverflowError):
                result['skipped_count'] += 1
                continue
            if notice.identity in seen:
                result['skipped_count'] += 1
                continue
            seen.add(notice.identity)
            try:
                inserted = self.opportunities.upsert(notice, payload['connector_version'])
            except (StorageIntegrityError, sqlite3.IntegrityError):
                raise PermanentJobError('Invalid connector storage data.') from None
            except (StorageError, sqlite3.OperationalError):
                raise RetryableJobError('Connector storage unavailable.') from None
            result['accepted_count'] += 1
            result['inserted_count' if inserted else 'updated_count'] += 1
        return result
