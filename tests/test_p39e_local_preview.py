import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import p39e_local_h_preview as preview
from app.analytics.offline_fixture import CASES, calculate, fixture_payload, stable, FixtureError


def test_disabled_does_not_build(capsys):
    with patch.object(preview, 'build', side_effect=AssertionError('must not build')):
        assert preview.main([]) == 0
    assert 'DISABLED' in capsys.readouterr().out


@pytest.fixture(scope='module')
def committed():
    return asyncio.run(preview.collect())


@pytest.mark.parametrize('case', CASES)
def test_real_child_contract(committed, case):
    assert stable(committed['cases'][case]) == stable(calculate(fixture_payload(case)))


def test_semantics(committed):
    c = committed['cases']
    assert [c['normal']['kpis'][k]['value'] for k in ('Discovered','Matched','High Fit','Active Sources','Countries','Closing Soon')] == [4,2,2,1,1,1]
    assert c['empty']['kpis']['Discovered']['value'] == 0
    assert c['unknown']['kpis']['Matched']['value'] is None
    assert c['unknown']['kpis']['Matched']['denominator'] == 0
    assert c['filtered']['selected_identities'] == [['ted','zero']]
    assert c['filtered']['kpis']['High Fit']['value'] == 0
    assert c['filtered']['kpis']['Discovered']['value'] == 1
    assert {b[0] for b in c['normal']['deadline_grouping']['buckets']} == {'instant','date_only'}
    for name in ('legacy','foreign','future'):
        assert c[name]['current_fit_unknown']


def test_html_contract_and_safe_json(committed):
    html = preview.render(committed)
    for marker in ('OFFLINE TEST FIXTURE', 'Discovered', 'Matched', 'High Fit', 'Active Sources', 'Countries', 'Closing Soon', 'Content-Security-Policy', "connect-src 'none'", '<table', 'viewport', 'P4 public rollout BLOCKED'):
        assert marker in html
    for forbidden in ('fetch(', 'XMLHttpRequest', 'innerHTML', '<script src=', '<link ', 'https://', 'http://', 'bearer', '.env'):
        # Namespace URI is not an asset or request.
        assert forbidden not in html.replace('http://www.w3.org/2000/svg', '')
    raw = preview.escaped_json({'x':'</script><script>alert(1)</script>\u2028\u2029&'})
    assert '<' not in raw and '\u2028' not in raw and '\u2029' not in raw
    assert json.loads(raw)['x'].startswith('</script>')
    assert len(html.encode()) < 256 * 1024


def test_atomic_success_and_failure(tmp_path, committed):
    target = tmp_path / 'index.html'
    async def good():
        return committed
    with patch.object(preview, 'collect', good):
        assert preview.build(target) == target.resolve()
    assert target.read_text(encoding='utf-8').startswith('<!doctype')
    async def bad():
        raise FixtureError('fixture_commitment')
    with patch.object(preview, 'collect', bad), pytest.raises(FixtureError):
        preview.build(target)
    assert not target.exists()
    assert not list(tmp_path.glob('*.tmp'))


def test_atomic_replace_failure(tmp_path, committed):
    async def good():
        return committed
    target = tmp_path / 'index.html'
    with patch.object(preview, 'collect', good), patch.object(preview.os, 'replace', side_effect=OSError()), pytest.raises(OSError):
        preview.build(target)
    assert not target.exists() and not list(tmp_path.glob('*.tmp'))


def test_checksum_fail_closed(tmp_path):
    from app.analytics import offline_fixture
    altered = tmp_path / 'fixture.json'
    altered.write_bytes(b'{}')
    with patch.object(offline_fixture, 'FIXTURE', altered), pytest.raises(FixtureError):
        asyncio.run(preview.collect())


def test_entrypoint_has_no_server_or_app_mutation():
    source = Path(preview.__file__).read_text(encoding='utf-8')
    for forbidden in ('import socket', 'HTTPServer', 'sqlite', 'app.api', 'premium.js', 'premium.css'):
        assert forbidden not in source


@pytest.mark.parametrize('event,args', [('socket.connect', ()), ('socket.getaddrinfo', ('example.invalid',)), ('open', ('C:/unused/.env',)), ('open', ('C:/unused/.ENV.example',))])
def test_guard_denies_before_io(event, args):
    with pytest.raises(RuntimeError):
        preview.offline_guard(event, args)


def test_output_mismatch_fails_closed():
    from app.analytics.offline_spike import FixtureSpike
    async def invalid(self, case):
        result = calculate(fixture_payload(case))
        result['kpis']['Discovered']['value'] = 999
        return {'result': result}
    with patch.object(FixtureSpike, 'run', invalid), pytest.raises(ValueError, match='output_contract'):
        asyncio.run(preview.collect())


def test_output_limit_fails_closed():
    from app.analytics import offline_fixture
    with patch.object(offline_fixture, 'OUTPUT_LIMIT', 1), pytest.raises(FixtureError):
        asyncio.run(preview.collect())


def test_polished_labels_layout_and_csp_hashes(committed):
    import base64
    import hashlib
    import re
    html = preview.render(committed)
    for label in ('Найдено закупок', 'Успешные источники', 'Скоро завершатся', 'Нет данных', 'Часовой пояс', 'Календарная дата', 'Текстовая таблица распределения', 'не вероятность победы'):
        assert label in html
    for pattern in (r'<style>(.*?)</style>', r'<script>(.*?)</script>'):
        text = re.search(pattern, html, re.S)[1]
        digest = base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()
        assert "'sha256-" + digest + "'" in html
    assert 'background:#07101f' in html
    assert 'color-scheme:dark' in html
    assert 'color-scheme:light' not in html
    assert 'OPPORTUNITY EXPLORER' in html
    assert 'pathLength:100' in html
    assert 'barrow' not in html
    assert '@media(max-width:480px)' in html
    assert 'overflow-x:auto' in html
    assert 'aria-label' in html and ':focus-visible' in html
    assert 'fixture_sha256:data.fixture_sha256' in html


def test_i18n_english_fallback_and_accessible_switch(committed):
    import re
    html = preview.render(committed)
    fallback = re.sub(r'<script[^>]*>.*?</script>|<style>.*?</style>', '', html, flags=re.S)
    assert '<html lang="en">' in fallback
    assert 'OFFLINE TEST FIXTURE — NO CUSTOMER DATA' in fallback
    assert not re.search('[А-Яа-яЁё]', fallback)
    assert 'id="lang-en" aria-pressed="true"' in fallback
    assert 'id="lang-ru" aria-pressed="false"' in fallback
    assert 'role="group" data-i18n-aria="language"' in fallback
    assert 'data-i18n-placeholder="searchHint"' in fallback
    assert 'data-i18n-aria="six"' in fallback
    assert '<details><summary data-i18n="technical">' in fallback


def test_i18n_local_contract(committed):
    html = preview.render(committed)
    for marker in ('const dictionary=', 'function translate(', 'Missing translation',
                   'Отсутствует перевод', 'validateDictionary()', 'localStorage.getItem',
                   'localStorage.setItem', 'document.documentElement.lang=locale',
                   'Intl.DateTimeFormat', 'Intl.NumberFormat', 'storageDenied',
                   'technicalReference', 'scenario.normal', 'scenario.filtered'):
        assert marker in html
    assert 'document.cookie' not in html
    # Existing byte bound, worker equivalence, forbidden IO and CSP assertions remain above.

def test_stage_b_dark_instruments_and_responsive_contract(committed):
    html = preview.render(committed)
    for marker in ('class="investigation"', 'deadline-glyph', 'coverageGraphic',
                   'keyboardEvidence', 'bucketGraphic', 'data-metric',
                   'radial-gradient', 'transition:none!important',
                   '@media(max-width:1200px)', '@media(max-width:850px)'):
        assert marker in html
    assert 'background:white' not in html
    assert 'stroke-dasharray' in html
    assert 'r:98' in html
