"""Verified existing source fixtures plus explicit negative contract variants."""
from dataclasses import asdict, replace
import json
from types import SimpleNamespace

import pytest

from app.analytics.normalization import country_code, normalize_countries
from app.analytics.taxonomies import normalize_classifications
from app.api.organization_workflow_routes import _discovery_item
from app.api.schemas import TenderDiscoveryItem
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.sources.enrichment import NoticeEnrichment, validate_enrichment
from app.sources.models import TenderNotice
from app.sources.opportunities import OpportunityRepository
from app.sources.sam_gov_api import parse_sam_gov_response
from app.sources.austender_rss import parse_austender_detail_page, AUSTENDER_ATM_BASE_URL
from tests.test_austender_source import _detail_html, UUID_1
from tests.test_discovery_preview_scoring import profile


def location(*values):
    return [{'path': f'placeOfPerformance.country.{index}', 'value': value} for index, value in enumerate(values)]


def sam(country=None):
    # Same explicit place-of-performance field and values as test_sam_gov_source.
    return parse_sam_gov_response({'opportunitiesData': [{
        'noticeId': 'abc123def456', 'title': 'Medical equipment procurement',
        'postedDate': '2026-10-01', 'responseDeadLine': '2026-11-15T17:00:00-05:00',
        'placeOfPerformance': {'country': country if country is not None else {
            'code': 'USA', 'name': 'United States'}},
    }]})[0]


@pytest.mark.parametrize('value,expected', [('USA', 'US'), (' United States ', 'US'), ('us', 'US'),
    ('GBR', 'GB'), ('UK', 'GB'), ('Italy', 'IT'), ('Congo', None), ('UKE1', None),
    ('EUR', None), ('XX', None), ('SU', None), (123, None), (None, None)])
def test_exact_country_table(value, expected):
    assert country_code(value) == expected


@pytest.mark.parametrize('locations,status,codes', [([], 'missing', []),
    ([location('USA', 'United States')], 'verified', ['US']),
    ([location('US'), location('GB'), location('US')], 'multi_country', ['GB', 'US']),
    ([location('USA', 'Canada')], 'conflicting', []),
    ([location('Congo')], 'ambiguous', []), ([location(123)], 'invalid', []),
    ([location('UKE1')], 'unmapped', []), ([location('US'), location('ZZ')], 'partial', ['US'])])
def test_country_quality_and_multi_location(locations, status, codes):
    result = normalize_countries(locations)
    assert (result['status'], result['codes']) == (status, codes)


def test_source_fixture_raw_and_country_disagreement():
    notice = sam()
    assert notice.enrichment['country']['codes'] == ['US']
    assert notice.enrichment['country']['evidence'][0]['value'] == 'USA'
    assert notice.enrichment['dates']['publication']['value'] == '2026-10-01'
    assert notice.identity == ('sam_gov', 'abc123def456')
    assert hash(notice) == hash(replace(notice, enrichment=None))
    assert notice == replace(notice, enrichment=None)
    assert sam({'code': 'USA', 'name': 'Canada'}).enrichment['country']['status'] == 'conflicting'
    assert sam({}).enrichment['country']['status'] == 'missing'


def test_genuine_austender_category_fixture_without_country_guess():
    notice = parse_austender_detail_page(_detail_html(), external_id=UUID_1,
        url=AUSTENDER_ATM_BASE_URL + UUID_1, rss_title='ISO 9001 Certification Services')
    data = notice.enrichment
    assert data['country']['codes'] == []
    assert data['classification']['memberships'] == [['austender-category', '80100000']]
    assert data['classification']['entries'][0]['label'] == 'Management advisory services'
    assert data['classification']['industries'] == []
    assert data['dates']['deadline']['path'] == 'detail.TimeZone.CloseDateTime'
    assert data['dates']['deadline']['raw_status'] == 'decoded_timezone_parameter'
    assert data['dates']['deadline']['value'] == '10/05/2026 12:00:00'
    assert data['dates']['deadline']['display_value']
    validate_enrichment(data, notice.source, notice.external_id)


def test_empty_publication_fallback_retains_update_semantics():
    from app.sources.eis_rss import parse_eis_feed
    notice = parse_eis_feed(b'''<rss><channel><item><guid>update-1</guid>
        <title>Medical equipment</title><link>https://example.test/1</link>
        <pubDate> </pubDate><updated> 2026-10-01T12:00:00Z </updated>
        </item></channel></rss>''')[0]
    assert notice.published_at == '2026-10-01T12:00:00Z'
    assert notice.enrichment['dates']['publication']['value'] == ' 2026-10-01T12:00:00Z '
    assert notice.enrichment['dates']['publication']['semantics'] == 'source_update'


def test_taxonomy_duplicates_conflicts_and_unsupported_cpv():
    entry = {'scheme': 'austender-category', 'code': '80100000', 'label': 'Management advisory services',
             'path': 'dataLayer.atmCategoryCode', 'role': 'reported'}
    result = normalize_classifications([entry, entry])
    assert len(result['memberships']) == 1
    assert len(result['entries']) == 2
    secondary = {'scheme': 'za-etenders-category', 'code': 'Services: General',
                 'label': 'Services: General', 'path': 'category', 'role': 'reported'}
    assert len(normalize_classifications([entry, secondary, entry])['memberships']) == 2
    assert normalize_classifications([{**entry, 'label': 'Guess'}])['entries'][0]['status'] == 'conflicting'
    for scheme, code in [('CPV', '45000000'), ('CPV', 'invalid'), ('CPV', '00000000'),
                         ('arbitrary', 'technology'), ('austender-category', '99999999')]:
        result = normalize_classifications([{**entry, 'scheme': scheme, 'code': code}])
        assert result['memberships'] == []
        assert result['industries'] == []


def test_discovery_new_snapshot_roundtrip_and_legacy():
    notice = sam()
    item = _discovery_item(SimpleNamespace(notice=notice, reasons=[]), profile())
    encoded = item.model_dump_json()
    assert TenderDiscoveryItem.model_validate_json(encoded).enrichment.model_dump() == notice.enrichment
    old = item.model_dump()
    del old['enrichment']
    assert TenderDiscoveryItem.model_validate(old).enrichment is None
    legacy = TenderNotice('sam_gov', 'old', 'Medical equipment', 'https://sam.gov/opp/old/view', currency='USD')
    assert _discovery_item(SimpleNamespace(notice=legacy, reasons=[]), profile()).enrichment is None


def test_provenance_identity_version_and_forged_normalization_rejected():
    data = sam().enrichment
    for change in ({'schema_version': 2}, {'observed_at': '2026-10-01'},
                   {'country': {**data['country'], 'codes': ['GB']}},
                   {'country': {**data['country'], 'evidence': [{}]}},
                   {'classification': {**data['classification'], 'entries': [{}]}}):
        with pytest.raises(ValueError):
            NoticeEnrichment.model_validate({**data, **change})
    with pytest.raises(ValueError):
        validate_enrichment(data, 'ted', data['external_id'])
    item = _discovery_item(SimpleNamespace(notice=sam(), reasons=[]), profile()).model_dump()
    item['external_id'] = 'another'
    with pytest.raises(ValueError):
        TenderDiscoveryItem.model_validate(item)


def test_opportunity_json_roundtrip_and_old_json_no_rewrite(tmp_path):
    database = Database(DatabaseSettings('', tmp_path / 'enrichment.db'))
    store = OpportunityRepository(database)
    store.initialize()
    notice = sam()
    store.upsert(notice, 'connector-sync-v1:sam_gov:adapter-r1')
    loaded = store.read('sam_gov')[0]
    assert loaded.enrichment['country'] == notice.enrichment['country']
    assert loaded.enrichment['observed_at'] == notice.enrichment['observed_at']
    assert loaded.enrichment['connector_version'] == 'connector-sync-v1:sam_gov:adapter-r1'
    # Provenance never becomes a new discovery keyword match.
    assert store.read('sam_gov', search_terms=['iso3166-location']) == []
    legacy = asdict(replace(notice, external_id='legacy', enrichment=None))
    legacy.pop('enrichment')
    encoded = json.dumps(legacy)
    with database.connect() as connection:
        connection.execute('INSERT INTO source_opportunities VALUES(?,?,?,?,?,?)',
            ('sam_gov', 'legacy', encoded, 'connector-sync-v1:sam_gov:adapter-r1', '2026-10-01', '2026-10-01'))
        connection.commit()
    assert next(n for n in store.read('sam_gov') if n.external_id == 'legacy').enrichment is None
    with database.connect() as connection:
        assert connection.execute("SELECT notice_json FROM source_opportunities WHERE external_id='legacy'").fetchone()[0] == encoded
    database.close()


@pytest.mark.parametrize('with_cpv', [False, True])
def test_enriched_discovery_authorization_and_history_no_refetch(with_cpv):
    from tests.test_organization_workflows import OrganizationWorkflowTests
    from app.database.repository import TenderRepository
    helper = OrganizationWorkflowTests()
    helper.setUp()
    try:
        helper.as_account(helper.owner)
        first_company = helper.create_company('Enriched Medical Supplier', 'medical')
        repository = TenderRepository(helper.path)
        repository.initialize()
        helper.client.app.state.runtime.tender_repository = repository
        notice = sam()
        if with_cpv:
            notice = replace(notice, enrichment={**notice.enrichment,
                'classification': normalize_classifications([{'scheme': 'cpv-2008',
                    'code': '45000000', 'path': 'synthetic.test', 'role': 'reported'}])})
        helper.catalog.notices = (notice,)
        url = helper.base('/discover/tenders')
        response = helper.client.post(url)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['items'][0]['enrichment']['country']['codes'] == ['US']
        if with_cpv:
            assert body['items'][0]['enrichment']['classification']['memberships'] == [['cpv-2008', '45000000']]
        history_id = body['history_id']
        assert history_id is not None
        calls = len(helper.catalog.calls)
        saved = helper.client.get(helper.base(f'/discovery/history/{history_id}'))
        assert saved.status_code == 200, saved.text
        assert saved.json()['discovery']['items'][0]['enrichment'] == body['items'][0]['enrichment']
        assert len(helper.catalog.calls) == calls
        saved_opportunity = helper.client.post(helper.base('/shortlist'), json=body['items'][0])
        assert saved_opportunity.status_code in (200, 201), saved_opportunity.text
        shortlist = helper.client.get(helper.base('/shortlist'))
        assert shortlist.status_code == 200, shortlist.text
        assert shortlist.json()[0]['opportunity']['enrichment'] == body['items'][0]['enrichment']
        assert len(helper.catalog.calls) == calls
        if with_cpv:
            other_company = helper.create_company('Other Medical Supplier', 'medical')
            assert helper.client.post(helper.base(f"/companies/{other_company['id']}/activate")).status_code == 200
            assert helper.client.get(helper.base(f'/discovery/history/{history_id}')).status_code == 404
            assert helper.client.get(helper.base('/discovery/history')).json() == []
            assert helper.client.post(helper.base(f"/companies/{first_company['id']}/activate")).status_code == 200
            assert helper.client.get(helper.base(f'/discovery/history/{history_id}')).status_code == 200
            assert len(helper.catalog.calls) == calls
        helper.as_account(helper.viewer)
        assert helper.client.get(helper.base(f'/discovery/history/{history_id}')).status_code == 200
        # Existing read access does not grant Saved mutations.
        assert helper.client.post(helper.base('/shortlist'), json=body['items'][0]).status_code == 403
        helper.as_account(helper.outsider)
        assert helper.client.post(url).status_code == 403
        assert helper.client.get(helper.base(f'/discovery/history/{history_id}')).status_code == 403
        helper.client.cookies.clear()
        assert helper.client.post(url).status_code == 401
        assert len(helper.catalog.calls) == calls
    finally:
        helper.doCleanups()
