'use strict';
// No app functions are replaced: execute the shipped browser script, mock fetch only.
// Minimal DOM surface records rendered HTML and dispatches the actual installed handlers.
async function run(source, assert) {
 const fixture = {source:'ted',external_id:'TEST-ONLY-1',title:'Pumps <img src=x onerror=alert(1)>',
  url:'https://ted.europa.eu/en/notice/TEST-ONLY-1/html',customer:'Test buyer',currency:null,
  metadata_analysis:{required_documents:[]}, preliminary_scoring:{fit_score:72,completeness_percent:40,
   criteria:[{label:'Products',status:'matched',earned_points:12,weight:20,explanation:'Pump capability matches',evidence:['Test evidence']}],
   stop_factors:['Verify certification'],missing_information:['Delivery location unknown']}};
 const response=(data,status=200)=>({ok:status>=200&&status<300,status,json:async()=>data});
 function browser({write=true,port='',shared=true}={}) {
  const nodes={},events={},calls=[],pending=[];
  const node=id=>nodes[id] ||= {id,value:'',dataset:{},textContent:'',innerHTML:'',disabled:false,options:[],open:false,
   replaceChildren(...rows){this.innerHTML='';this.textContent='';this.options=rows;},add(row){this.options.push(row);},
   addEventListener(name,fn){this.listeners ||= {};this.listeners[name]=fn;},querySelectorAll(){return id==='discoveryWorkspace'?['Keyword','Source','Buyer','Currency','Value','Fit','Deadline','Published'].map(k=>node('filter'+k)):[];},querySelector(){return null;},
   showModal(){this.open=true;},close(){this.open=false;this.listeners?.close?.();}};
  const state={organizationId:11,activeCompanyId:21,activeCompanyName:'TEST company A',uiEpoch:0,
   companies:[{id:21,profile:{search_keywords:['pumps']}}]};
  const window={addEventListener:(name,fn)=>{(events[name] ||= []).push(fn);},dispatchEvent:e=>{for(const f of events[e.type]||[])f(e);}};
  const location={hash:'#discover',port,replace(url){this.redirect=url;}};
  const globals={document:{getElementById:node},window,state,location,URL,AbortController,
   Option:function(text,value){this.text=text;this.value=value;},
   CustomEvent:function(type,opts){this.type=type;this.detail=opts.detail;},
   usingSharedOrganization:()=>shared,canWriteWorkspace:()=>write,
   fetch:(url,options={})=>{calls.push({url,options});return new Promise(resolve=>pending.push({url,resolve}));}};
  // Explicit bindings reproduce classic script globals without mocking business logic.
  const api=Function(...Object.keys(globals),source+'\nreturn globalThis.ValyqonDiscovery;')(...Object.values(globals));
  const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
  const settle=async(data,status=200)=>{assert.ok(pending.length,'expected a pending network request');pending.shift().resolve(response(data,status));await tick();};
  const click=async(parent,attr,index=0)=>{const button={disabled:false,textContent:'',dataset:{[attr]:String(index)}};
   await node(parent).onclick({target:{closest:selector=>selector===`[data-${attr}]`?button:null}});return button;};
  return {node,state,window,location,calls,pending,settle,tick,click,api,setWrite:value=>{write=value;}};
 }
 const report={items:[fixture],partial_failure:true,total_failure:false,attempted_sources:['ted','uk_fts'],
  successful_sources:['ted'],failed_sources:['uk_fts'],source_statuses:[
   {source:'ted',display_name:'TED',state:'healthy',notice_count:1},
   {source:'uk_fts',display_name:'Find a Tender',state:'failed',error_type:'ConnectorTransportError'},
   {source:'sam_gov',display_name:'SAM.gov',state:'disabled',authentication_required:true,notice_count:null}]};
 let checks=0;
 async function test(name,fn){await fn();checks++;console.log('PASS:',name);}
 await test('explicit Find click, partial outcomes, criteria, official HTTPS and XSS-safe cards/detail',async()=>{
  const b=browser();assert.equal(b.calls.length,0);assert.match(b.node('discoveryGuide').textContent,/pumps/);
  const running=b.node('discoverButton').onclick();assert.equal(b.node('discoverButton').disabled,true);
  assert.equal(b.calls[0].url,'/api/v1/organizations/11/discover/tenders');assert.equal(b.calls[0].options.method,'POST');
  assert.equal(b.calls[0].options.credentials,'same-origin');await b.settle(report);await running;
  assert.match(b.node('discoveryMessage').textContent,/some procurement sources/);
  assert.match(b.node('discoverySourceOutcomes').innerHTML,/ConnectorTransportError/);
  assert.match(b.node('discoverySourceOutcomes').innerHTML,/Authentication required/);
  const html=b.node('discoveryResults').innerHTML;
  for(const label of ['Preliminary Match: 72%','Pump capability matches','Verify certification','Delivery location unknown','data-save="0"'])assert.ok(html.includes(label));
  assert.ok(!html.includes('<img'));assert.ok(html.includes('&lt;img'));await b.settle([]);
  assert.match(html,/href="https:\/\/ted.europa.eu/);
  await b.click('discoveryResults','detail');assert.equal(b.node('tenderDetail').open,true);
  assert.match(b.node('detailBody').innerHTML,/href="https:\/\/ted.europa.eu/);
  assert.match(b.node('detailBody').innerHTML,/noopener noreferrer/);
  assert.match(b.node('detailBody').innerHTML,/Test evidence/);
  assert.equal(b.api.officialUrl({...fixture,url:'http://ted.europa.eu/x'}),null);
  assert.equal(b.api.officialUrl({...fixture,url:'https://ted.europa.eu.evil.test/x'}),null);
  assert.equal(b.api.officialUrl({...fixture,url:'https://u:p@ted.europa.eu/x'}),null);
  assert.equal(b.api.officialUrl({...fixture,source:'unknown'}),null);
  assert.ok(!b.calls.some(c=>c.url.includes('monitoring')||c.url.includes('scoring/evaluate')));
 });
 await test('company switch aborts and prevents stale result or source flash, including late JSON',async()=>{
  const b=browser();const running=b.node('discoverButton').onclick();
  b.state.activeCompanyId=22;b.state.activeCompanyName='TEST company B';b.state.uiEpoch++;
  b.window.dispatchEvent({type:'workspace-context'});
  assert.equal(b.calls[0].options.signal.aborted,true);
  await b.settle(report);await running;assert.equal(b.node('discoveryResults').innerHTML,'');
  assert.equal(b.node('discoverySourceOutcomes').innerHTML,'');assert.match(b.node('discoveryGuide').textContent,/company B/);
  if(b.pending.length)await b.settle([]); // Existing context handler reads the new company's shortlist.
  // A company change between headers and JSON must also discard the payload.
  const next=b.node('discoverButton').onclick();let release;
  b.pending.shift().resolve({ok:true,status:200,json:()=>new Promise(r=>{release=r;})});await b.tick();
  b.state.activeCompanyId=23;b.window.dispatchEvent({type:'workspace-context'});release(report);await next;
  assert.equal(b.node('discoveryResults').innerHTML,'');assert.equal(b.node('discoveredCount').textContent,'Not run');
 });
 await test('permitted Save uses existing API and provides saved state; role downgrade blocks forged Save/Remove',async()=>{
  const b=browser();let running=b.node('discoverButton').onclick();await b.settle(report);await running;await b.settle([]);
  const saving=b.click('discoveryResults','save');assert.equal(b.calls.at(-1).options.method,'POST');
  assert.equal(JSON.parse(b.calls.at(-1).options.body).external_id,fixture.external_id);
  await b.settle({id:7,opportunity:fixture});await saving;assert.match(b.node('discoveryResults').innerHTML,/aria-disabled="true">Saved/);
  await b.click('discoveryResults','detail');assert.match(b.node('detailBody').innerHTML,/data-remove/);
  b.setWrite(false);const before=b.calls.length;await b.click('detailBody','remove');await b.click('discoveryResults','save');assert.equal(b.calls.length,before);
  b.setWrite(true);
  const removing=b.click('detailBody','remove');assert.equal(b.calls.at(-1).url,'/api/v1/organizations/11/shortlist/7');
  await b.settle(null,204);await removing;assert.match(b.node('discoveryResults').innerHTML,/data-save/);
  const viewer=browser({write:false});running=viewer.node('discoverButton').onclick();await viewer.settle(report);await running;await viewer.settle([]);
  assert.ok(!viewer.node('discoveryResults').innerHTML.includes('data-save'));
  const count=viewer.calls.length;await viewer.click('discoveryResults','save');await viewer.click('detailBody','remove');assert.equal(viewer.calls.length,count);
 });
 await test('repeat search closes detail and ignores an older Save completion',async()=>{
  const b=browser();let running=b.node('discoverButton').onclick();await b.settle(report);await running;await b.settle([]);
  await b.click('discoveryResults','detail');const saving=b.click('detailBody','save');
  running=b.node('discoverButton').onclick();assert.equal(b.node('tenderDetail').open,false);assert.equal(b.node('detailBody').innerHTML,'');
  await b.settle({id:9,opportunity:fixture});await saving;assert.equal(b.node('discoveryResults').innerHTML,'');
  await b.settle({...report,items:[]});await running;await b.settle([]);assert.equal(b.node('discoveryResults').innerHTML,'');
 });
 await test('denied Save stays retryable and a company switch discards late Save UI updates',async()=>{
  const b=browser();const running=b.node('discoverButton').onclick();await b.settle(report);await running;await b.settle([]);
  let saving=b.click('discoveryResults','save');await b.settle({},403);const button=await saving;
  assert.equal(button.disabled,false);assert.match(b.node('discoveryMessage').textContent,/role cannot save/);
  saving=b.click('discoveryResults','save');b.location.hash='#overview';b.state.activeCompanyId=22;
  b.window.dispatchEvent({type:'workspace-context'});await b.settle({id:8,opportunity:fixture});await saving;
  assert.equal(b.node('discoveryResults').innerHTML,'');assert.equal(b.node('detailBody').innerHTML,'');
 });
 await test('empty, total failure, unavailable, forbidden, unauthorized and preview states are honest',async()=>{
  for(const [data,status,pattern] of [[{...report,items:[],partial_failure:false},200,/No tenders found/],
   [{...report,total_failure:true},200,/Sources could not be reached/],[{},503,/unavailable/],[{},403,/access/],[{},409,/activate/]]){
   const b=browser();const running=b.node('discoverButton').onclick();await b.settle(data,status);await running;
   assert.match(b.node('discoveryMessage').textContent,pattern);assert.equal(b.node('discoverButton').disabled,false);
   assert.equal(b.node('discoveryResults').innerHTML,'');if(b.pending.length)await b.settle([]);
  }
  const b=browser();const running=b.node('discoverButton').onclick();await b.settle({},401);await running;assert.equal(b.location.redirect,'/login');
  const preview=browser({port:'8765'});assert.equal(preview.node('discoverButton').disabled,true);
  await preview.node('discoverButton').onclick();assert.equal(preview.calls.length,0);assert.match(preview.node('discoveryGuide').textContent,/API unavailable/);
  const privateWorkspace=browser({shared:false});await privateWorkspace.node('discoverButton').onclick();assert.equal(privateWorkspace.calls.length,0);
 });
 await test('local filters, missing defaults and document-backed fit distinction',async()=>{
  const b=browser();const running=b.node('discoverButton').onclick();await b.settle(report);await running;await b.settle([]);
  b.node('filterKeyword').value='does not match';b.node('filterKeyword').listeners.input();
  assert.equal(b.node('discoveryResults').innerHTML,'');assert.match(b.node('discoveryMessage').textContent,/No results match/);
  b.node('resetFilters').onclick(); // actual reset handler
  assert.match(b.node('discoveryResults').innerHTML,/Pumps/);
  const full=b.api.card({...fixture,full_ai_analyzed:true,full_scoring:{fit_score:81,criteria:[]}},0);
  assert.match(full,/Full Document Match: 81%/);assert.match(full,/eligibility is not confirmed/);
  assert.match(b.api.card({...fixture,preliminary_scoring:{}},0),/Not enough data/);
  assert.ok(!b.api.matches(fixture,{keyword:'absent',value:'',fit:''}));
  assert.ok(!b.api.matches(fixture,{currency:'EUR',value:'',fit:''}));
 });
 console.log(`PASS: ${checks} customer discovery behavioral groups (synthetic test fixtures only)`);
 return checks;
}
module.exports=run;
if(require.main===module){const fs=require('node:fs');const path=require('node:path');
 run(fs.readFileSync(path.join(__dirname,'../../app/api/static/discovery.js'),'utf8'),require('node:assert/strict'))
 .catch(error=>{console.error(error);process.exitCode=1;});}
