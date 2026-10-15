'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const file = path.join(__dirname, '../../app/api/static/discovery.js');
const source = fs.readFileSync(file, 'utf8');
const discovery = require(file);
const item = {source:'ted', external_id:'synthetic', title:'Industrial pumps',
 full_ai_analyzed:false, metadata_analysis:{required_documents:[]},
 preliminary_scoring:{fit_score:null, criteria:[{code:'documents', status:'not_scored',
 explanation:'Document inventory unknown', evidence:[]}], missing_information:['Delivery unknown']}};
const card = discovery.card(item, 0);
assert.match(card, /Preliminary Match/);
assert.match(card, /available metadata/);
assert.match(card, /Review full documents/);
assert.match(card, /Not enough data/);
const detail = discovery.detail(item);
assert.match(detail, /Missing data.*not scored/);
assert.match(detail, /Document inventory unknown/);
assert.match(detail, /Delivery unknown/);
assert.match(detail, /Full AI analysis has not been run/);
assert.match(detail, /Document requirements in metadata/);
assert.match(discovery.sourceMessage({partial_failure:true}), /some procurement sources could not be reached/);
assert.match(discovery.sourceMessage({total_failure:true}), /Sources could not be reached/);
// Monitoring is a separate user action, never an automatic Discovery side effect.
assert.doesNotMatch(source, /\/monitoring\/scan/);
const nodes = {}, events = {};
function node(id) { return nodes[id] ||= {value:'', textContent:'', innerHTML:'', disabled:false,
 options:[], open:false, replaceChildren(...rows){this.innerHTML='';this.options=rows;},
 add(row){this.options.push(row);}, addEventListener(){}, querySelectorAll(){return [];},
 querySelector(){return null;}, close(){this.open=false;}}; }
let resolve;
const calls = [];
const context = {document:{getElementById:node}, window:{addEventListener:(key, fn)=>{events[key]=fn;}},
 state:{organizationId:11, activeCompanyId:21, activeCompanyName:'Synthetic A', uiEpoch:0},
 usingSharedOrganization:()=>true, canWriteWorkspace:()=>false, AbortController, URL,
 Option:function(text,value){this.text=text;this.value=value;}, location:{hash:'',replace(){}},
 fetch:(url,options)=>{calls.push({url,options});return new Promise(r=>{resolve=r;});}};
vm.runInNewContext(source, context);
(async()=>{
 const pending = node('discoverButton').onclick();
 assert.equal(calls[0].url, '/api/v1/organizations/11/discover/tenders');
 assert.equal(calls[0].options.method, 'POST');
 assert.equal(calls[0].options.credentials, 'same-origin');
 context.state.activeCompanyId=22; // Same organization, different active company.
 events['workspace-context']();
 assert.equal(calls[0].options.signal.aborted, true);
 resolve({ok:true,status:200,json:async()=>({items:[item]})});
 await pending;
 assert.equal(node('discoveryResults').innerHTML, '');
 assert.equal(calls.length, 1);
 assert.equal(node('sourceHealth').textContent, '');
 const current=node('discoverButton').onclick();
 resolve({ok:true,status:200,json:async()=>({items:[item],partial_failure:true,
  attempted_sources:['ted','uk_fts'],successful_sources:['ted'],failed_sources:['uk_fts']})});
 await current;
 assert.match(node('sourceHealth').textContent,/Reached: ted/);
 assert.match(node('sourceHealth').textContent,/Unavailable: uk_fts/);
 assert.match(node('discoveryMessage').textContent,/some procurement sources could not be reached/);
 assert.match(node('discoveryResults').innerHTML,/Preliminary Match/);
 assert.match(node('discoveryResults').innerHTML,/Metadata preview/);
 assert.equal(node('filterSource').options.length,2);
 assert.equal(node('filterSource').options[1].value,'ted');
 assert.equal(node('filterSource').options[1].text,'European Union - TED');
 assert.equal(node('discoveredCount').textContent,'1');
 assert.equal(node('scoredCount').textContent,'0');
 const late=node('discoverButton').onclick();
 const finish=resolve;
 context.state.organizationId=12;
 context.state.uiEpoch++;
 events['workspace-context']();
 finish({ok:true,status:200,json:async()=>({items:[item]})});
 await late;
 assert.equal(node('discoveryResults').innerHTML,'');
 const parsing=node('discoverButton').onclick();
 let finishJson;
 let markJsonStarted;
 const jsonStarted=new Promise(r=>{markJsonStarted=r;});
 // Synchronize on the real VM handler entering response.json(), not a guessed
 // number of host microtask turns. Early completion must fail, not hang/pass.
 resolve({ok:true,status:200,json:()=>new Promise(r=>{
  finishJson=r;
  markJsonStarted();
 })});
 await Promise.race([jsonStarted,parsing.then(()=>{
  assert.fail('Discovery completed before entering response.json()');
 })]);
 assert.equal(typeof finishJson,'function');
 context.state.activeCompanyId=23;
 events['workspace-context']();
 finishJson({items:[item],successful_sources:['ted']});
 await parsing;
 assert.equal(node('discoveryResults').innerHTML,'');
 assert.equal(node('sourceHealth').textContent,'');
 assert.equal(node('discoveredCount').textContent, 'Not run');
 assert.equal(node('scoredCount').textContent, 'Not run');
 console.log('PASS: honest Discovery labels and cross-company stale response isolation');
})().catch(error=>{console.error(error);process.exitCode=1;});

// Exercise actual renderer provenance and URL escaping, with declared synthetic data.
const official = {...item, tender_number:'100001-2026', title:'<script>bad</script>',
 url:'https://ted.europa.eu/en/notice/100001-2026/html?x=1&y=%22',
 preliminary_scoring:{fit_score:100, completeness_percent:30}};
assert.match(discovery.card(official,0), /&lt;script&gt;bad/);
const officialDetail=discovery.detail(official);
assert.match(officialDetail,/Source<\/dt><dd>ted/);
assert.match(officialDetail,/100001-2026/);
assert.match(officialDetail,/x=1&amp;y=%22/);
assert.match(officialDetail,/rel="noopener noreferrer"/);
assert.match(officialDetail,/Preliminary Match: 100%/);
assert.match(officialDetail,/Data completeness 30%/);
assert.doesNotMatch(officialDetail,/Full Document Match/);
assert.equal(discovery.safeUrl(official.url),official.url);
assert.match(officialDetail,/href="https:\/\/ted\.europa\.eu\/en\/notice\/100001-2026\/html\?x=1&amp;y=%22"/);
const hostile={...official,source:'<img src=x onerror="bad">',
 customer:'<script>buyer</script>',tender_number:'" onmouseover="bad',
 summary:'<img src=x onerror="bad">',
 preliminary_scoring:{criteria:[{code:'<script>criterion</script>',
 explanation:'<img src=x onerror="bad">',evidence:['<script>evidence</script>']}],
 missing_information:['<script>missing</script>']}};
for(const html of [discovery.card(hostile,0),discovery.detail(hostile)]){
 assert.doesNotMatch(html,/<script|<img/);
 assert.match(html,/&lt;img src=x onerror=&quot;bad&quot;&gt;/);
 assert.match(html,/&lt;script&gt;buyer&lt;\/script&gt;/);
 assert.match(html,/&quot; onmouseover=&quot;bad/);
}
assert.match(discovery.detail(hostile),/&lt;script&gt;evidence&lt;\/script&gt;/);
assert.match(discovery.detail(hostile),/&lt;script&gt;missing&lt;\/script&gt;/);
for(const url of ['javascript:alert(1)','data:text/html,bad','https://user:pass@ted.europa.eu/']){
 assert.equal(discovery.safeUrl(url),null);
 assert.match(discovery.detail({...official,url}),/No safe source link available/);
}
