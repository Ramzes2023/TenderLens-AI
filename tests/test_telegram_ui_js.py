"""Exercise dashboard JavaScript with Node's built-in VM; no browser/network."""
import json
import shutil
import subprocess
import unittest
from app.api.telegram_ui import TELEGRAM_SCRIPT


class TelegramJavascriptTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is needed for JS behavior tests")
    def test_link_refresh_errors_and_double_click(self):
        script = r"""
const vm=require('node:vm'),assert=require('node:assert/strict');
const nodes={};
const element=id=>nodes[id]??=( {hidden:false,disabled:false,textContent:'',className:'',
  removeAttribute(key){delete this[key]}} );
let calls=[],resolveRequest,timers=[],now=0,blocked=false,nextResponse;
const popup={opener:{},location:{replace(url){popup.url=url}},close(){popup.closed=true}};
const context={
  document:{getElementById:element},
  window:{open:()=>blocked?null:popup,addEventListener:(event,fn)=>{context[event]=fn}},
  location:{replace(){}},state:{},Date:{now:()=>now},AbortController,
  setTimeout:(fn,ms)=>{timers.push({fn,ms});return timers.length},
  clearTimeout:()=>{},
  fetch:async(path,options)=>{calls.push({path,options});return await nextResponse()},
  loadCompanies:async()=>{},loadMonitoring:async()=>{},loadTenders:async()=>{}
};
vm.createContext(context);
vm.runInContext(SOURCE,context);
const response=(status,data)=>({ok:status===200,status,json:async()=>data});
(async()=>{
 nextResponse=()=>new Promise(resolve=>resolveRequest=resolve);
 const first=context.connectTelegram();
 await context.connectTelegram();
 assert.equal(calls.length,1,'double click creates only one ticket');
 assert.equal(element('connectTelegram').disabled,true);
 resolveRequest(response(200,{start_parameter:'link_safe_test'}));await first;
 assert.equal(popup.url,'https://t.me/TenderLensAI_bot?start=link_safe_test');
 assert(timers.some(t=>t.ms===2500));
 nextResponse=async()=>response(200,{telegram_connected:true,owner_user_id:42});
 await context.refreshTelegramStatus();
 assert.equal(element('connectTelegram').hidden,true);
 assert.equal(element('telegramOpen').href,undefined);
 assert.equal(context.state.ownerId,42);
 assert.equal(calls.filter(c=>c.options.method==='POST').length,1);
 context.renderTelegram({telegram_connected:false});
 blocked=true;
 nextResponse=async()=>response(200,{start_parameter:'link_again'});
 await context.connectTelegram();
 assert.equal(element('telegramOpen').hidden,false,'fallback link with blocked popup');
 now=130000;const before=calls.length;await context.refreshTelegramStatus();
 assert.equal(calls.length,before,'timeout stops requests');
 let attempt=0;
 nextResponse=async()=>++attempt===1?response(409,{}):response(200,{telegram_connected:true,owner_user_id:42});
 await context.connectTelegram();
 assert.equal(element('connectTelegram').hidden,true,'409 rechecks authoritative status');
 context.renderTelegram({telegram_connected:false});
 nextResponse=async()=>response(503,{});
 await context.connectTelegram();
 assert.equal(element('connectTelegram').disabled,false);
 assert.match(element('telegramMessage').textContent,/Unable/);
 context.pagehide();const count=calls.length;await context.connectTelegram();
 assert.equal(calls.length,count);
 console.log('JS behavior PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
""".replace("SOURCE", json.dumps(TELEGRAM_SCRIPT))
        result = subprocess.run(["node", "-"], input=script, capture_output=True,
                                text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
