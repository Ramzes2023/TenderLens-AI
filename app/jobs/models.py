"""Safe wire contracts. Job payloads are data, never executable instructions."""
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any


class JobValueError(ValueError):
    pass


def encode_json(value, limit):
    seen = set()
    count = 0
    budget = 0
    def consume_string(item):
        nonlocal budget
        if len(item) > limit:
            raise JobValueError('Job JSON exceeds size limit.')
        try:
            budget += len(json.dumps(item, ensure_ascii=False).encode('utf-8'))
        except (ValueError, UnicodeError):
            raise JobValueError('Invalid job JSON.') from None
        if budget > limit:
            raise JobValueError('Job JSON exceeds size limit.')
    def visit(item, depth):
        nonlocal count
        count += 1
        if depth > 32 or count > 10000:
            raise JobValueError('Job JSON structure exceeds bounds.')
        if type(item) in (dict, list):
            if id(item) in seen:
                raise JobValueError('Invalid job JSON.')
            seen.add(id(item))
            if type(item) is dict:
                for key, child in item.items():
                    if type(key) is not str:
                        raise JobValueError('Invalid job JSON.')
                    consume_string(key)
                    visit(child, depth + 1)
            else:
                for child in item:
                    visit(child, depth + 1)
            seen.remove(id(item))
        elif item is None or type(item) is bool:
            pass
        elif type(item) is str:
            consume_string(item)
        elif type(item) is int:
            if not -(2**63) <= item < 2**63:
                raise JobValueError('Job JSON integer exceeds bounds.')
        elif type(item) is float and math.isfinite(item):
            pass
        else:
            raise JobValueError('Invalid job JSON.')
    visit(value, 0)
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
        if len(encoded.encode('utf-8')) > limit:
            raise JobValueError('Job JSON exceeds size limit.')
        return encoded
    except (ValueError, UnicodeError, RecursionError):
        raise JobValueError('Invalid or oversized job JSON.') from None


def job_type_name(value):
    if type(value) is not str or not re.fullmatch(r'[a-z][a-z0-9_.-]{0,99}', value):
        raise JobValueError('Invalid job type.')
    return value


@dataclass(frozen=True)
class JobScope:
    account_id: int | None = None
    organization_id: int | None = None
    company_id: int | None = None

    def __post_init__(self):
        for value in self.values:
            if value is not None and (type(value) is not int or not 1 <= value < 2**63):
                raise JobValueError('Invalid job scope.')
        if (self.organization_id is not None and self.account_id is None) or (self.company_id is not None and self.organization_id is None):
            raise JobValueError('Invalid job scope.')

    @property
    def values(self):
        return self.account_id, self.organization_id, self.company_id


@dataclass(frozen=True)
class Job:
    id: str
    job_type: str
    state: str
    scope: JobScope
    payload: Any = field(repr=False)
    result: Any = field(repr=False)
    priority: int
    attempt_count: int
    max_attempts: int
    available_at: int
    created_at: int
    started_at: int | None
    finished_at: int | None
    lease_expires_at: int | None
    failure_code: str | None


@dataclass(frozen=True)
class Claim:
    job: Job
    token: str = field(repr=False)


def decode_job(row):
    if row is None:
        return None
    return Job(id=row['id'], job_type=row['job_type'], state=row['state'],
               scope=JobScope(row['account_id'], row['organization_id'], row['company_id']),
               payload=json.loads(row['payload_json']), result=json.loads(row['result_json']) if row['result_json'] is not None else None,
               **{name: row[name] for name in ('priority', 'attempt_count', 'max_attempts', 'available_at', 'created_at',
                                              'started_at', 'finished_at', 'lease_expires_at', 'failure_code')})
