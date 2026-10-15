'use strict';
// OFFLINE_FIXTURE: runs actual UI handlers with a fake HTTP boundary; no browser/live AI claims.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const discovery=require('../../app/api/static/discovery.js');
const rag=require('../../app/api/static/rag.js');
const filters={keyword:'',source:'',buyer:'',currency:'',value:'',fit:'50',deadline:'',published:''};
const item={source:'ted',external_id:'fixture-1',url:'https://ted.europa.eu/en/notice/1',currency:'EUR',initial_price:1000,
 preliminary_scoring:{fit_score:90},full_ai_analyzed:true,full_analysis:{currency:'EUR'},
 full_scoring:{fit_score:20,criteria:[{code:'budget',label:'Budget',explanation:'Above company budget',evidence:['<img src=x onerror=alert(1)>']}],document_risks:['Certificate missing'],stop_factors:['Budget exceeded']}};
assert.equal(discovery.matches(item,filters),false,'filter must agree with displayed document score');
assert.equal(discovery.matches({...item,full_ai_analyzed:false},filters),true);
assert.equal(discovery.matches({...item,full_scoring:{fit_score:NaN}},filters),false);
assert.equal(discovery.matches(item,{...filters,fit:'',currency:'EUR',value:'garbage'}),false);
assert.equal(discovery.matches({...item,initial_price:NaN},{...filters,fit:'',currency:'EUR',value:'100'}),false);
const card=discovery.card(item,0);
assert.match(card,/Score evidence/);assert.match(card,/Certificate missing/);assert.match(card,/Budget exceeded/);
assert.match(card,/amounts are not converted/);assert.match(card,/not a probability of winning/);
assert.match(card,/&lt;img/);assert.doesNotMatch(card,/<img/);
for(const key of ['api_key','APIKEY','token','access_token','password','secret'])assert.equal(discovery.officialUrl({...item,url:item.url+'?'+key+'=fixture'}),null);
assert.equal(discovery.officialUrl({...item,url:'https://ted.europa.eu.evil.invalid/notice/1'}),null);
assert.equal(rag.validPdf({name:'catalog.PDF',size:1},10),true);
assert.equal(rag.validPdf({name:'catalog.pdf',size:11},10),false);
assert.equal(rag.validPdf({name:'catalog.pdf',size:0},10),false);
assert.equal(rag.readyJob({state:'queued',ready:true}),false);

const source=fs.readFileSync(path.join(__dirname,'../../app/api/static/rag.js'),'utf8');
function boot(){
 const ids=['ragWorkspace','ragStatus','ragServices','ragFile','ragUpload','ragCheck','ragQuestion','ragAsk','ragAnswer'];
 const node=()=>({disabled:false,value:'',files:[],textContent:'',style:{},children:[],append(...nodes){this.children.push(...nodes);},replaceChildren(...nodes){this.children=nodes;}});
 const nodes=Object.fromEntries(ids.map(id=>[id,node()])),events={},requests=[];
 const state={accountId:1,organizationId:2,activeCompanyId:3,uiEpoch:1,companies:[{id:3}]};
 let respond=async url=>url.endsWith('/capabilities')?{configured:true,can_upload:true,max_pdf_bytes:10*1024*1024,message:'Configured; worker unverified.'}:{job_id:'fixture-job',state:'queued',ready:false};
 const context={state,location:{hash:'#ai-analysis',port:''},AbortController,FormData:class {append(...v){this.value=v;}},
  usingSharedOrganization:()=>true,canWriteWorkspace:()=>true,
  fetch:async(url,opt)=>{requests.push({url,opt});const body=await respond(url,opt);return {ok:true,json:async()=>body};},
  document:{getElementById:id=>nodes[id],createElement:node},window:{MainLocale:{locale:'en'},addEventListener:(name,fn)=>events[name]=fn}};
 vm.runInNewContext(source,context);
 return {nodes,events,requests,state,context,respond:fn=>respond=fn};
}
const flush=async()=>{for(let n=0;n<12;n++)await Promise.resolve();};
(async()=>{
 const x=boot();await flush();assert.equal(x.nodes.ragUpload.disabled,false);assert.equal(x.nodes.ragAsk.disabled,true);
 assert.equal(x.requests.length,1);assert.match(x.requests[0].url,/organizations\/2\/companies\/3\/rag\/capabilities$/);
 x.nodes.ragFile.files=[{name:'fixture.pdf',size:42}];x.nodes.ragUpload.onclick();await flush();
 assert.equal(x.nodes.ragAsk.disabled,true);assert.equal(x.nodes.ragCheck.disabled,false);assert.match(x.nodes.ragStatus.textContent,/queued/);
 assert.equal(x.requests[1].opt.method,'POST');assert.equal(x.requests[1].opt.credentials,'same-origin');
 x.respond(async url=>url.endsWith('/ask')?{answer:'<script>hostile PDF</script>',sources:[{page_number:2,chunk_index:1}]}:{job_id:'fixture-job',state:'succeeded',ready:true});
 x.nodes.ragCheck.onclick();await flush();assert.equal(x.nodes.ragAsk.disabled,false);
 x.nodes.ragQuestion.value='  delivery?  ';x.nodes.ragAsk.onclick();await flush();
 assert.equal(JSON.parse(x.requests.at(-1).opt.body).question,'delivery?');
 assert.equal(x.nodes.ragAnswer.children[0].textContent,'<script>hostile PDF</script>','answer uses textContent');
 assert.match(x.nodes.ragAnswer.children[1].children[0].textContent,/Page 2/);
 // An in-flight answer cannot populate a newly selected company's document workspace.
 let release;x.respond(()=>new Promise(resolve=>release=resolve));
 x.nodes.ragAsk.onclick();x.state.activeCompanyId=null;x.state.uiEpoch++;x.events['workspace-context']();
 assert.equal(x.nodes.ragAnswer.children.length,0);assert.equal(x.nodes.ragFile.value,'');assert.equal(x.nodes.ragQuestion.value,'');
 release({answer:'old company answer',sources:[]});await flush();assert.equal(x.nodes.ragAnswer.children.length,0);assert.equal(x.nodes.ragAsk.disabled,true);
 const unavailable=boot();await flush();unavailable.respond(async()=>({configured:false,can_upload:false,message:'Unavailable'}));
 unavailable.nodes.ragServices.onclick();await flush();assert.equal(unavailable.nodes.ragUpload.disabled,true);assert.match(unavailable.nodes.ragStatus.textContent,/Unavailable/);
 const viewer=boot();await flush();viewer.context.canWriteWorkspace=()=>false;viewer.events['workspace-context']();assert.equal(viewer.nodes.ragUpload.disabled,true);
 viewer.context.window.MainLocale.locale='ru';viewer.events['shell-locale-change']();assert.match(viewer.nodes.ragStatus.textContent,/Сервисы/);
 const preview=boot();await flush();preview.context.location.port='8765';preview.state.uiEpoch++;preview.events['workspace-context']();assert.equal(preview.nodes.ragServices.disabled,true);
 console.log('Pilot document workflow offline contracts passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
