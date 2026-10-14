"""Pinned real-source Genericode regressions; no synthetic TED response claims."""
import json
from pathlib import Path
import pytest
from scripts.verify_cpv_hierarchy import extract
from app.analytics.cpv import cpv_parent, cpv_ancestors, cpv_descendants, cpv_category_match
from app.analytics.taxonomies import normalize_classifications, LEGACY_TAXONOMY_VERSION


def test_full_source_equality_and_packaged_graph():
    raw = Path('.cache/phase24p33-completion/official_eforms_cpv.gc').read_bytes()
    result = extract(raw)
    assert result == json.loads(Path('app/analytics/cpv_2008_parents.json').read_text(encoding='utf-8'))
    assert (result['rows'], result['explicit_edges'], result['verified_edges']) == (9454,9409,9400)
    assert len(result['missing_parent']) == 45
    assert len(result['label_mismatches']) == 7
    assert len(result['withheld_edges']) == 9
    assert result['orphans'] == result['cycles'] == 0
    with pytest.raises(ValueError, match='checksum'):
        extract(raw+b'changed')


def test_explicit_traversal_unknowns_and_invalid_types():
    assert cpv_ancestors('03111100')['ancestors'] == ['03111000','03110000','03100000','03000000']
    assert '03111100' in cpv_descendants('03000000')['descendants']
    assert '45000000' not in cpv_descendants('03000000')['descendants']
    assert cpv_parent('03000000')['status'] == 'unknown_parent'
    assert cpv_parent('03331100')['status'] == 'unknown_parent'
    for code in ([], None, 45000000, '450000007'):
        assert cpv_ancestors(code)['status'] == 'invalid'
        assert cpv_descendants(code)['descendants'] == []
    assert cpv_ancestors('00000000')['status'] == 'unknown'
    assert cpv_parent('45000000-7')['status'] == 'unsupported_check_digit'


def test_multi_code_dedup_match_and_legacy():
    entries = [{'scheme':'cpv-2008','code':code,'path':'synthetic','role':'reported'}
               for code in ('03111100','03111100','45000000')]
    data = normalize_classifications(entries)
    assert len(data['memberships']) == 2
    assert cpv_category_match(data,'03000000') is True
    assert cpv_category_match(data,'03111100') is True
    assert cpv_category_match(data,'03000000',include_descendants=False) is False
    assert cpv_category_match(data,'99999999') is None
    assert cpv_category_match(data,'98000000') is None
    assert cpv_category_match(normalize_classifications(entries,version=LEGACY_TAXONOMY_VERSION),'03000000') is None
    bad = normalize_classifications([{**entries[0],'label':'Wrong'}])
    assert cpv_category_match(bad,'03000000') is None
    sibling = normalize_classifications([entries[0]])
    assert cpv_category_match(sibling,'03111200') is False
    assert cpv_category_match(sibling,'03131300') is False
    independent = normalize_classifications([{**entries[0],'scheme':'austender-category','code':'80100000'}])
    assert cpv_category_match(independent,'80000000') is None


def test_graph_rejects_orphans_cycles_metadata_and_duplicates(monkeypatch):
    import hashlib
    import xml.etree.ElementTree as ET
    import scripts.verify_cpv_hierarchy as verifier
    raw = Path('.cache/phase24p33-completion/official_eforms_cpv.gc').read_bytes()
    for kind, message in [('orphan','Orphan'),('cycle','cycle'),('metadata','Metadata'),('duplicate','Duplicate')]:
        root = ET.fromstring(raw)
        rows = root.find('SimpleCodeList')
        if kind == 'metadata':
            root.find('Identification/Version').text = '2099'
        elif kind == 'duplicate':
            import copy
            rows.append(copy.deepcopy(rows[0]))
        else:
            row = rows[1]
            parent = next(v for v in row.findall('Value') if v.attrib['ColumnRef']=='parentCode')
            parent.find('SimpleValue').text = '00000000' if kind=='orphan' else '03100000'
        changed = ET.tostring(root)
        # Exercise structural validation after a hypothetical newly pinned reference.
        monkeypatch.setattr(verifier,'SHA256',hashlib.sha256(changed).hexdigest())
        with pytest.raises(ValueError,match=message):
            verifier.extract(changed)


def test_official_ted_search_field_contexts_are_not_response_schema():
    from scripts.verify_ted_classification_fields import inspect
    raw = Path('.cache/phase24p33-completion/official_ted_search_fields.html').read_bytes()
    evidence = inspect(raw)
    assert evidence == json.loads(Path('tests/fixtures/ted_classification_field_evidence.json').read_text(encoding='utf-8'))
    assert evidence['extraction_status'] == 'pending'
    assert len(evidence['rows']) == 7
    with pytest.raises(ValueError,match='checksum'):
        inspect(raw+b'changed')


@pytest.mark.parametrize('value',['45000000',['45000000'],45000000,{'lot-1':['45000000']},None])
def test_unproven_ted_classification_response_shapes_stay_unextracted(value):
    from app.sources.ted_api import TED_FIELDS, parse_ted_search_response
    evidence = json.loads(Path('tests/fixtures/ted_classification_field_evidence.json').read_text(encoding='utf-8'))
    raw = {'publication-number':'offline-negative', **{row[0]:value for row in evidence['rows']}}
    notice = parse_ted_search_response({'notices':[raw]})[0]
    assert notice.enrichment['classification']['memberships'] == []
    assert all(row[0] not in TED_FIELDS for row in evidence['rows'])
