"""Safety and normalization helpers scoped to anonymous international feeds."""
import asyncio
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

MONTH_NAMES = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')


def english_day(day):
    return f'{day.day:02d}-{MONTH_NAMES[day.month - 1]}-{day.year:04d}'


def official_url(value, hosts):
    if not isinstance(value, str) or len(value) > 2000:
        raise ValueError('Missing or oversized official notice URL.')
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or parsed.hostname not in hosts
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or '\\' in value or any(c.isspace() or ord(c) < 32 for c in value)):
        raise ValueError('Untrusted official notice URL.')
    return value


def source_date(value):
    """Keep date-only precision; convert explicitly offset timestamps to UTC."""
    if value is None or value == '':
        return None
    if not isinstance(value, str):
        raise ValueError('Invalid source date.')
    value = value.strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}[+-]\d{2}:\d{2}', value):
        # TED XML Schema date: the offset qualifies a calendar day, not midnight.
        if int(value[-5:-3]) > 23 or int(value[-2:]) > 59:
            raise ValueError('Invalid source date offset.')
        return datetime.strptime(value[:10], '%Y-%m-%d').date().isoformat()
    if len(value) == 10:
        return datetime.strptime(value, '%Y-%m-%d').date().isoformat()
    match = re.fullmatch(r'(\d{1,2})-([A-Za-z]{3})-(\d{4})', value)
    if match:
        months = {name.casefold(): i + 1 for i, name in enumerate(MONTH_NAMES)}
        month = months.get(match[2].casefold())
        if month is None:
            raise ValueError('Invalid source month.')
        return datetime(int(match[3]), month, int(match[1])).date().isoformat()
    if value.endswith('-00:00'):
        raise ValueError('Source timestamp has an unknown offset.')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Source timestamp has no timezone.')
    return parsed.astimezone(timezone.utc).isoformat()


def closed(deadline, *, now=None):
    if not deadline:
        return False  # Unknown is not proof of an open deadline.
    now = now or datetime.now(timezone.utc)
    if len(deadline) == 10:
        return datetime.fromisoformat(deadline).date() < now.date()
    return datetime.fromisoformat(deadline) <= now


async def request_json(client, method, url, *, hosts, **kwargs):
    """One bounded retry for 429/5xx; no auth, redirect or arbitrary URL follow."""
    official_url(url, hosts)
    for attempt in range(2):
        response = await getattr(client, method.lower())(url, **kwargs)
        status = getattr(response, 'status_code', 200)
        if attempt == 0 and (status == 429 or 500 <= status <= 599):
            delay = response.headers.get('Retry-After', '1')
            try:
                delay = float(delay)
            except ValueError:
                delay = 60  # HTTP-date/unknown: don't retry sooner than instructed.
            if 0 <= delay <= 2:
                await asyncio.sleep(delay)
                continue
        response.raise_for_status()
        if status != 200:
            raise ValueError(f'Unexpected HTTP {status}; redirects are not followed.')
        if len(response.content) > 2 * 1024 * 1024:
            raise ValueError('International response exceeds 2 MiB.')
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError('Invalid source JSON envelope.')
        return payload


def diagnostic(error):
    if isinstance(error, httpx.HTTPStatusError):
        code = error.response.status_code
        category = 'authentication_required' if code in (401, 403) else 'rate_limited' if code == 429 else 'http_error'
        return f'{category}: HTTP {code}'
    if isinstance(error, httpx.TimeoutException):
        return 'timeout: official endpoint did not respond within the request limit'
    if isinstance(error, (httpx.TransportError, OSError)):
        return f'network_unavailable: {type(error).__name__} (DNS/TCP/TLS)'
    return f'invalid_response: {type(error).__name__}'


def public_diagnostic(message):
    """Allowlisted customer diagnostics, never raw adapter exception text."""
    text = str(message or '')
    prefix = r'Unable to fetch (?:TED|UK Find a Tender|World Bank) notices\. '
    match = re.fullmatch(prefix + r'(authentication_required|rate_limited|http_error): HTTP ([45]\d\d)', text)
    if match:
        return f'{match[1]}: HTTP {match[2]}'
    if re.fullmatch(prefix + r'timeout: official endpoint did not respond within the request limit', text):
        return 'timeout: official endpoint did not respond within the request limit'
    if re.fullmatch(prefix + r'network_unavailable: [A-Za-z]+ \(DNS/TCP/TLS\)', text):
        return 'network_unavailable: DNS/TCP/TLS connection failed'
    return None


def retryable(error):
    from .http import _is_public_ip_error
    if _is_public_ip_error(error):
        return False
    return (isinstance(error, (httpx.TransportError, OSError))
            or isinstance(error, httpx.HTTPStatusError)
            and (error.response.status_code in (408, 429) or error.response.status_code >= 500))
