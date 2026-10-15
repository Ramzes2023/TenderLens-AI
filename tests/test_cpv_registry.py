"""Reference-backed registry tests; synthetic values are not TED field evidence."""
import copy
from pathlib import Path
import re

import pytest

from app.analytics.cpv import CPV_LABELS, CPV_METADATA, cpv_parent, validate_cpv, verify_reference
from app.analytics.taxonomies import normalize_classifications, LEGACY_TAXONOMY_VERSION
from app.sources.enrichment import enrichment, validate_enrichment
from app.sources.ted_api import TED_FIELDS, parse_ted_search_response


def entry(code, **values):
    return {'scheme': 'cpv-2008', 'code': code, 'path': 'synthetic.classification',
            'role': 'reported', **values}


def test_reference_coverage_and_integrity():
    assert len(CPV_LABELS) == 9454
    assert CPV_METADATA['version'] == '2008'
    assert CPV_METADATA['declared_structure'] == 'hierarchical'
    assert CPV_LABELS['03000000'].startswith('Agricultural, farming')
    assert CPV_LABELS['45000000'] == 'Construction work'
    assert CPV_LABELS['98910000'] == 'Services specific to international organisations and bodies'
    assert all(re.fullmatch('[0-9]{8}', code) and label for code, label in CPV_LABELS.items())
    reference = Path('.cache/phase24p3/official_ted_cpv_2008.html')
    if reference.exists():
        raw = reference.read_bytes()
        assert verify_reference(raw)
        assert not verify_reference(raw + b'changed')
        # Full-table equality, not just selected positive examples.
        from html import unescape
        rows = re.findall(r'<code>([0-9]{8})</code>\s*</td>\s*<td class="hdlist2">\s*<p>(.*?)</p>', raw.decode(), re.S)
        assert len(rows) == 9454
        assert {code: ' '.join(unescape(label).split()) for code, label in rows} == dict(CPV_LABELS)


@pytest.mark.parametrize('code,status', [('45000000','verified'),('03111100','verified'),
    ('00000000','unknown'),('99999999','unknown'),('45000000-7','unsupported_check_digit'),
    ('45000000-8','unsupported_check_digit'),('450000007','invalid'),(' 45000000','invalid'),
    ('４５００００００','invalid'),(45000000,'invalid'),(None,'invalid'),([], 'invalid')])
def test_exact_validation(code, status):
    assert validate_cpv(code) == status


def test_no_unverified_parents_digits_obsolescence_or_nace():
    assert cpv_parent('03111100') == {'code':'03111100','parent':'03111000','status':'verified'}
    assert cpv_parent('00000000')['status'] == 'unknown'
    result = normalize_classifications([entry('03111100')])
    assert result['industries'] == result['hierarchies'] == []
    assert result['industry_status'] == 'unmapped'


def test_multiple_memberships_raw_roles_conflicts_and_independent_schemes():
    entries = [entry('45000000', role='primary'), entry('45000000', role='secondary'),
               entry('03111100'), entry('00000000'), entry('45000000', label='Wrong'),
               entry('80100000', scheme='austender-category', label='Management advisory services'),
               entry('Services: General', scheme='za-etenders-category')]
    original = copy.deepcopy(entries)
    result = normalize_classifications(entries)
    assert entries == original
    assert len(result['entries']) == 7 and len(result['memberships']) == 4
    assert result['status'] == 'partial'
    assert result['entries'][4]['status'] == 'conflicting'
    assert result['entries'][4]['canonical_label'] is None
    assert result['entries'][0]['role'] == 'primary'
    assert result['entries'][1]['role'] == 'secondary'
    assert normalize_classifications([entry('45000000', scheme='CPV')])['memberships'] == []


def test_legacy_policy_snapshot_stays_readable_without_reinterpretation():
    data = enrichment('ted', 'legacy')
    data['classification'] = normalize_classifications([entry('45000000')], version=LEGACY_TAXONOMY_VERSION)
    assert validate_enrichment(data, 'ted', 'legacy').classification == data['classification']
    assert data['classification']['memberships'] == []
    with pytest.raises(ValueError):
        normalize_classifications([], version='future')


def test_cpv_roundtrip_forgery_and_identity_binding():
    data = enrichment('ted', 'test', classifications=[entry('45000000'), entry('00000000')])
    assert validate_enrichment(data, 'ted', 'test').model_dump() == data
    for key, value in [('memberships', [['cpv-2008','99999999']]), ('industries',['NACE-F'])]:
        forged = copy.deepcopy(data)
        forged['classification'][key] = value
        with pytest.raises(ValueError):
            validate_enrichment(forged, 'ted', 'test')
    with pytest.raises(ValueError):
        validate_enrichment(data, 'ted', 'other')


def test_equal_numeric_codes_keep_independent_taxonomies():
    result = normalize_classifications([entry('80100000'),
        entry('80100000', scheme='austender-category', label='Management advisory services')])
    assert result['memberships'] == [['austender-category', '80100000'], ['cpv-2008', '80100000']]
    assert result['entries'][0]['canonical_label'] == 'Primary education services'
    assert result['entries'][1]['canonical_label'] == 'Management advisory services'


def test_unverified_ted_field_names_are_neither_requested_nor_guessed():
    notice = parse_ted_search_response({'notices':[{'publication-number':'test',
        'cpv':'45000000', 'classification-cpv':['45000000'], 'notice-title':'Construction work'}]})[0]
    assert notice.enrichment['classification']['memberships'] == []
    assert not any('cpv' in field for field in TED_FIELDS)
