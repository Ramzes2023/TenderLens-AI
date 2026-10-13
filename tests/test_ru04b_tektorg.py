"""Synthetic per documented schema; these are NOT authentic live snapshots."""
import asyncio
from dataclasses import replace
import hashlib

import pytest

from app.sources.base import TenderSource
from app.sources.models import TenderNotice
from app.sources.registry import SourceRegistry, SourceRegistration
from app.sources.tektorg import (
    MAX_BYTES, TekTorgOfflineSource, parse_export_fragment,
    validate_filters, validate_procedure_url,
)


def synthetic(section='synthetic-section', identifier='synthetic-id', current=1, total=1):
    # Root is a local extraction convention, NOT a documented SOAP wrapper.
    return (f'<syntheticFragment><totalProcedures>{total}</totalProcedures>'
            f'<currentPage>{current}</currentPage><totalPage>{total}</totalPage>'
            '<limitProceduresInPage>1</limitProceduresInPage>'
            f'<sectionName>Synthetic section</sectionName><sectionCode>{section}</sectionCode>'
            f'<procedures><procedure><id>{identifier}</id></procedure></procedures>'
            '</syntheticFragment>').encode()


def project(record, page):
    # Explicit synthetic title/link; not inferred fields or a real procurement.
    return TenderNotice('tektorg', record.external_id, 'Synthetic notice',
                        'https://www.tektorg.ru/synthetic-test-only',
                        summary=f'Offline synthetic; sha256={page.payload_sha256}')


def test_parser_provenance_and_section_identity():
    first = parse_export_fragment(synthetic())
    second = parse_export_fragment(synthetic(section='other-synthetic'))
    assert len(first.payload_sha256) == 64
    assert first.procedures[0].external_id != second.procedures[0].external_id
    assert b'synthetic-id' in first.procedures[0].xml


def test_opt_in_and_existing_protocol_registry():
    source = TekTorgOfflineSource((synthetic(),), project)
    assert isinstance(source, TenderSource)
    assert asyncio.run(source.fetch()) == []
    registry = SourceRegistry([SourceRegistration('tektorg', 'Offline synthetic', source, enabled=False)])
    assert registry.keys(enabled_only=True) == ()
    notices = asyncio.run(replace(source, enabled=True).fetch())
    assert notices[0].identity == ('tektorg', '["synthetic-section","synthetic-id"]')


def test_pagination_limit_and_duplicates():
    source = TekTorgOfflineSource((synthetic(identifier='one', total=2),
                                   synthetic(identifier='two', current=2, total=2)), project, True)
    assert len(asyncio.run(source.fetch(1))) == 1
    assert len(asyncio.run(source.fetch(2))) == 2
    for pages in ((synthetic(total=2), synthetic(current=2, total=2)),
                  (synthetic(current=2, total=2),),
                  (synthetic(),) * 6):
        with pytest.raises(ValueError):
            asyncio.run(TekTorgOfflineSource(pages, project, True).fetch())


@pytest.mark.parametrize('payload', [
    b'<!DOCTYPE x [<!ENTITY a SYSTEM "file:///synthetic">]><x>&a;</x>',
    b'<!DOCTYPE x><x/>', b'<broken>', b'',
    synthetic().replace(b'<id>synthetic-id</id>', b'<id>a</id><id>b</id>'),
    synthetic().replace(b'<currentPage>1', b'<currentPage>6'),
    synthetic().replace(b'<totalPage>1', b'<totalPage>2'),
    synthetic().replace(b'<sectionCode>', b'<sectionCode xmlns="urn:synthetic">'),
    synthetic().replace(b'<procedure>', b'<procedure xmlns:x="urn:synthetic" x:flag="1">'),
    synthetic().replace(b'</id>', b'</id><detail xml:lang="en">Synthetic</detail>'),
    synthetic().decode().encode('utf-16'),
])
def test_reject_invalid_xml(payload):
    with pytest.raises(ValueError):
        parse_export_fragment(payload)


def test_xml_payload_byte_bounds():
    # Build large bytes locally: parametrized reprs can overflow Windows'
    # PYTEST_CURRENT_TEST environment variable before the parser is called.
    fragment = synthetic()
    payload = fragment.replace(
        b'</procedure>',
        b'<detail>' + b'x' * (MAX_BYTES - len(fragment) - len(b'<detail></detail>'))
        + b'</detail></procedure>',
    )
    assert len(payload) == MAX_BYTES
    page = parse_export_fragment(payload)
    assert page.procedures[0].external_id == '["synthetic-section","synthetic-id"]'
    assert page.payload_sha256 == hashlib.sha256(payload).hexdigest()
    assert page.procedures[0].xml == payload.split(b'<procedures>', 1)[1].split(
        b'</procedures>', 1)[0]
    with pytest.raises(ValueError, match='Invalid payload bound'):
        parse_export_fragment(payload + b' ')
    with pytest.raises(ValueError, match='Invalid payload bound'):
        parse_export_fragment(b'x' * (MAX_BYTES + 1))


@pytest.mark.parametrize('url', [
    'http://www.tektorg.ru/synthetic', 'https://www.tektorg.ru.evil.test/synthetic',
    'https://user@www.tektorg.ru/synthetic', 'https://www.tektorg.ru:443/synthetic',
    'https://127.0.0.1/synthetic', 'https://www.tektorg.ru/synthetic#fragment',
    'https://www.tektorg.ru/synthetic?token=x', 'https://www.tektorg.ru/%2fsynthetic',
    'https://www.tektorg.ru/synthetic?token=',
    'https://www.tektorg.ru/synthetic?ACCESS_TOKEN',
    'https://www.tektorg.ru/synthetic?view=public&api_key=',
    'https://www.tektorg.ru/', 'https://www.tektorg.ru/ synthetic',
    'https://api.tektorg.ru/procedures/soap',
])
def test_url_fail_closed(url):
    with pytest.raises(ValueError):
        validate_procedure_url(url)


def test_filters_no_guessed_wire_request():
    assert validate_filters({'limitPage': '500', 'page': '5'})['page'] == '5'
    for values in ({'limitPage': '501'}, {'page': '6'}, {'namespace': 'invented'},
                   {'sort': '<xml>'}, {'page': True}):
        with pytest.raises(ValueError):
            validate_filters(values)


def test_public_url_without_credentials():
    url = 'https://www.tektorg.ru/synthetic-test-only?view=public&flag='
    assert validate_procedure_url(url) == url


def test_projection_cannot_change_identity_or_host():
    for projector in (lambda r, p: replace(project(r, p), external_id='wrong'),
                      lambda r, p: replace(project(r, p), url='https://evil.test/synthetic')):
        with pytest.raises(ValueError):
            asyncio.run(TekTorgOfflineSource((synthetic(),), projector, True).fetch())


def test_empty_and_cross_section_export():
    empty = synthetic().replace(b'<totalProcedures>1', b'<totalProcedures>0')
    empty = empty.replace(b'<totalPage>1', b'<totalPage>0')
    empty = empty.replace(b'<procedure><id>synthetic-id</id></procedure>', b'')
    assert parse_export_fragment(empty).procedures == ()
    source = TekTorgOfflineSource((synthetic(), synthetic(section='other-synthetic')), project, True)
    assert len({n.identity for n in asyncio.run(source.fetch())}) == 2


@pytest.mark.parametrize('limit', [0, 101, True, '20'])
def test_invalid_fetch_bound(limit):
    with pytest.raises(ValueError):
        asyncio.run(TekTorgOfflineSource((synthetic(),), project, True).fetch(limit))
