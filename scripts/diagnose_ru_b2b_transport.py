"""Read-only official listing diagnostics through the production safe transport.

Exactly two dispatches, 2 MiB per response, strict TLS and public-IP checks.
No response bodies, cookies, credentials or environment values are printed.
This probe is never a substitute for Worker/SQL/scoring live acceptance.
"""
import asyncio
import json
import ssl

from app.sources.b2b_center import (
    B2B_CENTER_HOSTS, B2B_CENTER_LIST_URL, B2B_CENTER_OFFICE_LIST_URL,
    MAX_BYTES, parse_b2b_center_listing,
    _Document, _property,
)
from urllib.parse import urlsplit
from app.sources.http import ConnectorTransportError, FetchPolicy, bounded_fetch, source_client
from app.sources.http_transport import resolve_addresses
from app.sources.eis_rss import SourceError


async def diagnose():
    evidence = {'tls_verification': True, 'max_bytes': MAX_BYTES, 'pages': []}
    try:
        evidence['dns_addresses'] = list(await resolve_addresses('www.b2b-center.ru', 443))
    except OSError as error:
        evidence['dns_error_class'] = type(error).__name__
    policy = FetchPolicy(B2B_CENTER_HOSTS, 2, max_bytes=MAX_BYTES)
    with bounded_fetch(policy):
        for label, url in (('root', B2B_CENTER_LIST_URL), ('office', B2B_CENTER_OFFICE_LIST_URL)):
            row = {'listing': label}

            async def observed(response):
                row['http_status'] = response.status_code
                stream = response.extensions.get('network_stream')
                tls = stream.get_extra_info('ssl_object') if stream else None
                if tls:
                    row['tls_version'] = tls.version()

            try:
                async with source_client(timeout=25, follow_redirects=False, trust_env=False,
                                         event_hooks={'response': [observed]}) as client:
                    response = await client.get(url)
                row['decoded_bytes'] = len(response.content)
                doc = _Document()
                doc.feed(response.content.decode('utf-8-sig'))
                doc.close()
                demands, hosts, native_refs = 0, {}, []
                for node in doc.root.walk():
                    if node.attrs.get('itemtype') == 'https://schema.org/Demand':
                        demands += 1
                        for anchor in node.walk():
                            if anchor.tag != 'a' or not anchor.text().startswith('\u0417\u0430\u043a\u0443\u043f\u043a\u0430'):
                                continue
                            parts = urlsplit(anchor.attrs.get('href') or '')
                            hosts[parts.hostname] = hosts.get(parts.hostname, 0) + 1
                            if parts.hostname in B2B_CENTER_HOSTS:
                                native_refs.append({'label': anchor.text(), 'path': parts.path,
                                                    'search_url': _property(node, 'url', 'link')})
                row.update(demand_count=demands, reference_hosts=hosts, native_references=native_refs[:10])
                try:
                    notices = parse_b2b_center_listing(response.content, limit=10, listing_url=url)
                    row['native_notice_urls'] = [n.url for n in notices]
                except SourceError as error:
                    row['parser'] = 'no_valid_native_listing'
                    row['parser_error'] = str(error)
            except ConnectorTransportError as error:
                row.update(error_class=type(error).__name__, reason=error.reason,
                           retryable=error.retryable)
                chain, cause = [], error.__cause__
                while cause is not None and len(chain) < 8:
                    chain.append(type(cause).__name__)
                    if isinstance(cause, ssl.SSLCertVerificationError):
                        row['tls_certificate_verify_code'] = cause.verify_code
                    cause = cause.__cause__
                row['cause_classes'] = chain
            evidence['pages'].append(row)
    evidence['requests_used'] = policy.requests
    return evidence


if __name__ == '__main__':
    print(json.dumps(asyncio.run(diagnose()), sort_keys=True))
