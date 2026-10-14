"""Pinned official SDK example and explicitly synthetic context/security cases."""
import copy
import hashlib
from pathlib import Path
import socket
import xml.etree.ElementTree as ET

import pytest

from app.analytics.eforms_xml import (
    EXAMPLE_SHA256, MAX_BYTES, NS, SCHEMA_SHA256, extract_eforms_classifications, q,
)
from app.sources.ted_api import parse_ted_search_response

FIXTURES = Path(__file__).with_name('fixtures') / 'eforms'


def extract(raw, kind='synthetic_test'):
    return extract_eforms_classifications(raw, evidence_kind=kind,
                                          source_reference='offline fixture')


def synthetic():
    return (FIXTURES / 'synthetic_multiple_lots.xml').read_bytes()


def test_official_example_bytes_contexts_versions_and_provenance(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('No network permitted')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    raw = (FIXTURES / 'official_sdk_cn_24_minimal.xml').read_bytes()
    assert raw == Path('.cache/phase24p33-xml-context/official_sdk_cn_24_minimal.xml').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EXAMPLE_SHA256
    assert hashlib.sha256(Path('.cache/phase24p33-xml-context/official_eforms_lot_schema.html').read_bytes()).hexdigest() == SCHEMA_SHA256
    result = extract(raw, 'sdk_example')
    assert result == extract(raw, 'sdk_example')
    assert [(e['scope'], e['code'], e['role']) for e in result['entries']] == [
        ('procedure', '72230000', 'main'), ('lot', '72230000', 'main')]
    assert result['contexts'][1]['id']['value'] == 'LOT-0000'
    assert result['contexts'][1]['internal_id']['value'] == '1'
    assert result['entries'][0]['context_id']['value'] == '4805c409-5939-4be9-8abd-837f7a5fee23'
    assert result['versions']['CustomizationID']['value'] == 'eforms-sdk-1.16'
    assert result['versions']['UBLVersionID']['value'] == '2.3'
    assert result['versions']['VersionID']['value'] == '01'
    assert result['provenance']['evidence_kind'] == 'sdk_example'
    assert 'memberships' not in result
    with pytest.raises(ValueError, match='SDK example'):
        extract(raw, 'published_notice')


def test_synthetic_multiple_lots_do_not_flatten_and_preserve_roles_paths():
    result = extract(synthetic())
    assert [(e['scope'], e['context_id']['value'], e['role'], e['code'])
            for e in result['entries']] == [
        ('procedure', 'procedure-synthetic', 'main', '45000000'),
        ('lot', 'LOT-0001', 'main', '72230000'),
        ('lot', 'LOT-0001', 'additional', '72200000'),
        ('lot', 'LOT-0002', 'main', '03111100')]
    assert result['contexts'][3]['scope'] == 'group_of_lots'
    assert result['contexts'][3]['id']['value'] == 'GLO-0001'
    assert len({e['path'] for e in result['entries']}) == 4
    for e in result['entries']:
        assert e['attributes'] == {'listName': 'cpv'}
        assert 'CommodityClassification' in e['path']
        assert e['validation'] == 'verified' and e['cpv_version'] == '2008'
    assert result['provenance']['evidence_kind'] == 'synthetic_test'


def test_synthetic_part_is_separate_and_not_lot():
    result = extract((FIXTURES / 'synthetic_part.xml').read_bytes())
    assert [c['scope'] for c in result['contexts']] == ['procedure', 'part']
    assert result['entries'][-1]['context_id']['value'] == 'PAR-0001'
    assert result['entries'][-1]['scope'] == 'part'


@pytest.mark.parametrize('before,after', [
    (b'72230000', b'00000000'), (b'72230000', b'72230000-0'),
    (b'72230000', b' 72230000 '), (b'72230000', b'abc'),
    (b'listName="cpv"', b'listName="CPV"'),
    (b'listName="cpv"', b'listName="nace"'),
    (b'listName="cpv"', b'listName="cpv" listVersionID="1998"'),
    (b'listName="cpv"', b''), (b'LOT-0002', b'LOT-0001'),
    (b'schemeName="Lot"', b'schemeName="Unknown"'),
    (b'LOT-0001', b'LOT-1'),
    (b'MainCommodityClassification', b'UnknownCommodityClassification'),
    (b'CommonBasicComponents-2', b'UnknownComponents-2'),
    (b'<cac:ProcurementProject>', b'<cac:TenderingTerms>'),
])
def test_synthetic_invalid_unknown_or_ambiguous_rejected(before, after):
    with pytest.raises(ValueError):
        extract(synthetic().replace(before, after))


@pytest.mark.parametrize('raw', [
    b'<!DOCTYPE x [<!ENTITY x "45000000">]><x>&x;</x>',
    b'<!DOCTYPE x SYSTEM "file:///secret"><x/>',
    b'<!DOCTYPE x SYSTEM "https://untrusted.invalid/a"><x/>',
    b'<broken', b'x' * (MAX_BYTES + 1),
    '<?xml version="1.0"?><x/>'.encode('utf-16'),
    b'<?xml version="1.0" encoding="iso-8859-1"?><x/>',
    b'<x xmlns="urn:unknown"/>',
], ids=['entity', 'local-dtd', 'remote-dtd', 'malformed', 'oversize',
        'utf16', 'non-utf8-declaration', 'namespace'])
def test_parser_security(raw):
    with pytest.raises(ValueError):
        extract(raw)


def test_structure_limits_and_namespace_declarations():
    for raw in (
        ('<cn:ContractNotice xmlns:cn="' + NS['cn'] + '">' +
         '<cn:x>' * 65 + '</cn:x>' * 65 + '</cn:ContractNotice>').encode(),
        synthetic().replace(b'<cn:ContractNotice', b'<cn:ContractNotice xmlns:evil="urn:evil"'),
        ('<cn:ContractNotice xmlns:cn="' + NS['cn'] + '">' +
         '<cn:x/>' * 20001 + '</cn:ContractNotice>').encode(),
    ):
        with pytest.raises(ValueError):
            extract(raw)


def test_duplicate_ids_main_nodes_and_off_path_classifications():
    for mutation in ('id', 'main', 'offpath', 'group', 'mixed'):
        root = ET.fromstring(synthetic())
        lot = root.findall(q('cac:ProcurementProjectLot'))[0]
        project = lot.find(q('cac:ProcurementProject'))
        if mutation == 'id':
            lot.append(copy.deepcopy(lot.find(q('cbc:ID'))))
        elif mutation == 'main':
            project.append(copy.deepcopy(project.find(q('cac:MainCommodityClassification'))))
        elif mutation == 'offpath':
            root.append(copy.deepcopy(project.find(q('cac:MainCommodityClassification'))))
        elif mutation == 'group':
            root.findall(q('cac:ProcurementProjectLot'))[-1].append(copy.deepcopy(project))
        else:
            part = copy.deepcopy(lot)
            part.find(q('cbc:ID')).text = 'PAR-0001'
            part.find(q('cbc:ID')).set('schemeName', 'Part')
            root.append(part)
        with pytest.raises(ValueError):
            extract(ET.tostring(root))


def test_search_aggregate_stays_unbound_and_default_adapter_unchanged():
    notice = parse_ted_search_response({'notices': [{'publication-number': 'test',
        'classification-cpv': ['45000000', '72230000'],
        'links': {'xml': {'MUL': 'https://untrusted.invalid/xml'}}}]})[0]
    assert notice.enrichment['classification']['memberships'] == []
    assert notice.enrichment['classification']['entries'] == []
