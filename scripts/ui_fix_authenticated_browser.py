"""Real HTTP/browser cookies over isolated TestClient runtime; never proxy externally."""
from pathlib import Path
import importlib.util
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright


def main():
    spec=importlib.util.spec_from_file_location('synthetic_api_fixture',ROOT/'tests/test_private_preview_api.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    fixture=module.PrivatePreviewApiTests()
    lock=threading.Lock(); statuses=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def handle_request(self):
            # Clear the transport's own cookie jar so only browser cookies authenticate.
            with lock:
                fixture.client.cookies.clear()
                headers={k:v for k,v in self.headers.items() if k.lower() not in ['connection','content-length']}
                content=self.rfile.read(int(self.headers.get('Content-Length',0)))
                response=fixture.client.request(self.command,self.path,headers=headers,content=content,follow_redirects=False)
            statuses.append({'path':urlsplit(self.path).path,'status':response.status_code,'content_type':response.headers.get('content-type','')})
            self.send_response(response.status_code)
            for key,value in response.headers.multi_items():
                if key.lower() not in ['content-length','content-encoding','transfer-encoding','connection']:
                    self.send_header(key,value)
            self.end_headers();self.wfile.write(response.content)
        do_GET=handle_request;do_POST=handle_request;do_PUT=handle_request;do_DELETE=handle_request
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    base=f'http://127.0.0.1:{server.server_port}'
    out=ROOT/os.environ.get('VALYQON_BROWSER_OUTPUT','artifacts/valyqon-ui-fix-20261013_212738/local-results');out.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch()
        fixture.setUp()
        try:
            threading.Thread(target=server.serve_forever,daemon=True).start()
            page=browser.new_page(viewport={'width':1920,'height':1080})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(base+'/register')
            page.fill('#email','browser@example.test');page.fill('#password',module.PASSWORD)
            if page.locator('#confirmPassword').count():page.fill('#confirmPassword',module.PASSWORD)
            with page.expect_response('**/api/v1/auth/register') as registration:
                page.click('#submit')
            assert registration.value.status == 201
            page.wait_for_url('**/verify-email?email=*')
            assert fixture.sender.messages
            token=parse_qs(urlsplit(fixture.sender.messages[-1]['verification_url']).query)['token'][0]
            page.goto(base+'/verify-email?token='+token)
            page.wait_for_url(lambda url:urlsplit(url).path=='/dashboard',timeout=15000)
            page.select_option('#shellLocale','ru')
            page.evaluate("location.hash='team'")
            page.fill('#newOrganizationName','Synthetic organization');page.click('#createOrganizationButton')
            page.wait_for_function("usingSharedOrganization() && canWriteWorkspace()")
            page.evaluate("location.hash='companies'");page.click('#addCompanyButton')
            page.fill('#companyName','Synthetic company');page.fill('#keywords','paper');page.fill('#searchKeywords','paper');page.fill('#currencies','EUR')
            with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/companies')) as company:
                page.click('#createCompanyButton')
            assert company.value.status==201
            page.wait_for_function('state.activeCompanyId !== null')
            page.evaluate("location.hash='discover'")
            page.wait_for_function("!document.querySelector('#discoverButton').disabled")
            page.click('#discoverButton')
            page.wait_for_function("!document.querySelector('#discoverButton').disabled")
            # Disabled catalog is an honest result; no fake procurement integration is added.
            page.evaluate("location.hash='geography'");page.wait_for_selector('.geo-country',state='attached')
            assert page.locator('.geo-country').count()==176
            page.screenshot(path=str(out/'authenticated-map-ru.png'))
            page.reload();page.wait_for_function("state.activeCompanyId !== null")
            assert page.locator('#shellLocale').input_value()=='ru'
            untranslated={}
            for route in ['overview','discover','search-history','recommended','saved','geography','monitoring','source-health','ai-analysis','documents','notifications','team','companies','billing','settings','support']:
                page.evaluate('(route)=>{location.hash=route}',route);page.wait_for_timeout(100)
                untranslated[route]=page.locator('button,a,label,h2,h3,p,small,[role=status]').evaluate_all("""nodes=>[...new Set(nodes.filter(n=>n.getClientRects().length && !n.closest('#email,#organizationSelect,#companies .title,#companies .sub,#selectedOrganizationName')).map(n=>n.innerText.trim()).filter(t=>/^[A-Za-z]/.test(t)&&!/[А-Яа-яЁё]/.test(t)))];""")
            (out/'untranslated-ui.json').write_text(json.dumps(untranslated,ensure_ascii=False,indent=2),encoding='utf-8')
            allowed={'VALYQON AI','Telegram'}
            allowed |= {'AusTender','CanadaBuys','India Central Public Procurement Portal','Kazakhstan Public Procurement','New Zealand Government Electronic Tenders Service','Russian Unified Procurement Information System (EIS)','SAM.gov','South Africa eTenders','Tenders Electronic Daily (TED)','UK Find a Tender'}
            assert all(text in allowed for texts in untranslated.values() for text in texts), 'Untranslated operational UI copy; see untranslated-ui.json'
            page.evaluate("localStorage.setItem(`valyqon.organization.${state.accountId}`,'999999')")
            page.reload();page.wait_for_function("state.organizations.length>0 && !String(state.activeCompanyName).startsWith('Loading')")
            assert page.evaluate('selectedOrganization().personal')
            assert not errors,errors
            (out/'authenticated-browser.json').write_text(json.dumps({'journey':'registration, verification, organization, company, activation, disabled-source discovery, map, reload and navigation','page_errors':errors,'responses':statuses},indent=2),encoding='utf-8')
            print('Authenticated Chromium synthetic journey passed; source catalog disabled; no live procurement or PDF provider claimed')
        finally:
            server.shutdown();fixture.doCleanups();browser.close()


if __name__=='__main__':main()
