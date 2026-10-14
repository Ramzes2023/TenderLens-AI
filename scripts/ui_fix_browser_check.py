"""Local presentation regression only. Synthetic state, no account/database/production access."""
import json
import os
from pathlib import Path
import sys
import threading
import types
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Render the real presentation package without importing the API composition root.
# This harness cannot create a database or load runtime settings.
package = types.ModuleType('app.api'); package.__path__ = [str(ROOT / 'app/api')]
sys.modules['app.api'] = package
from app.api.dashboard import dashboard_html
from playwright.sync_api import sync_playwright

OUT = ROOT / os.environ.get('VALYQON_BROWSER_OUTPUT', 'artifacts/valyqon-ui-fix-20261013_212738/local-results')
OUT.mkdir(exist_ok=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/':
            body, mime, status = dashboard_html().encode(), 'text/html; charset=utf-8', 200
        elif path.startswith('/assets/'):
            file = ROOT / 'app/api/static' / Path(path).name
            body = file.read_bytes() if file.is_file() else b''
            mime = 'application/javascript' if file.suffix == '.js' else 'text/css' if file.suffix == '.css' else 'application/geo+json'
            status = 200 if file.is_file() else 404
        else:
            # Deliberately fail workspace APIs, never forward requests.
            body, mime, status = b'{"detail":"Synthetic API unavailable"}', 'application/json', 503
        self.send_response(status); self.send_header('Content-Type', mime)
        self.end_headers(); self.wfile.write(body)


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for failure in (False, True, 'both'):
                page = browser.new_page(viewport={'width':1366,'height':768})
                errors = []; responses = []; console_errors=[]
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.on('console',lambda msg:console_errors.append('error') if msg.type=='error' else None)
                page.on('response', lambda r: responses.append({'path':r.url.split(f':{server.server_port}')[-1].split('?')[0], 'status':r.status}))
                if failure:
                    page.route('**/geography_world.geojson', lambda route: route.fulfill(status=404,body=''))
                if failure == 'both':
                    page.route('**/geography_fallback.js*',lambda route:route.fulfill(status=200,content_type='application/javascript',body='window.ValyqonWorldOutlines=null;'))
                page.goto(f'http://127.0.0.1:{server.server_port}/#geography')
                if failure == 'both':
                    page.wait_for_function("document.querySelector('.geo-status').textContent.includes('could not be loaded')")
                    assert page.locator('.geo-country').count()==0
                    assert page.get_by_role('button',name='Zoom in +').is_disabled()
                    page.screenshot(path=str(OUT/'grid-failure-reproduction.png'))
                    results.append({'scenario':'primary 404 and no backup: original grid-only failure reproduced','outlines':0,'page_errors':errors,'responses':responses})
                    page.close();continue
                page.wait_for_selector('.geo-country', state='attached')
                assert page.locator('.geo-country').count() == 176
                shape=page.locator('.geo-country').first;shape.focus();page.keyboard.press('Enter')
                assert shape.get_attribute('aria-pressed')=='true'
                page.select_option('#shellLocale','ru')
                page.fill('#geoSearch','FR'); page.select_option('#geoCountry',label='Франция')
                assert page.locator('#geoSelectedCountry').inner_text() == 'Франция'
                page.get_by_role('button',name='Приблизить +').click()
                assert page.locator('.geo-map').get_attribute('viewBox') != '0 0 1000 500'
                page.screenshot(path=str(OUT / f'map-ru-{failure}.png'))
                page.reload(); page.wait_for_selector('.geo-country',state='attached')
                assert page.locator('#shellLocale').input_value() == 'ru'
                for route in ['overview','discover','search-history','saved','monitoring','source-health','ai-analysis','documents','team','companies','billing','settings']:
                    page.evaluate('(route)=>{location.hash=route}',route)
                    page.wait_for_timeout(80)
                    assert page.locator('html').get_attribute('lang') == 'ru'
                page.evaluate("location.hash='billing'")
                page.wait_for_timeout(80)
                assert 'Оплата и платные тарифы пока недоступны.' in page.locator('#futureText').inner_text()
                page.set_viewport_size({'width':390,'height':844})
                page.evaluate("location.hash='geography'"); page.wait_for_timeout(80)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(OUT / f'map-mobile-{failure}.png'))
                assert not errors, errors
                assert page.locator('#globalSupportLauncher').evaluate("el=>getComputedStyle(el).position")=='static'
                results.append({'forced_geojson_404':failure,'outlines':176,'page_errors':errors,'console_error_count':len(console_errors),'responses':responses})
                page.close()
            browser.close()
    finally:
        server.shutdown()
    (OUT / 'map-browser.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print('Chromium: normal + forced-404 map, selection, zoom, RU persistence, route navigation, billing and mobile passed')


if __name__ == '__main__':
    main()
