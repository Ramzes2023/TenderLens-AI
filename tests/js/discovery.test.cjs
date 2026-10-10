const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const d=require('../../app/api/static/discovery.js');
const item={title:'<img src=x onerror=alert(1)>',source:'ted',customer:'Buyer',currency:'EUR',initial_price:100,full_ai_analyzed:false,preliminary_scoring:{fit_score:null,completeness_percent:20,criteria:[{label:'Budget',status:'not_scored',explanation:'Missing value',weight:20,earned_points:0}],missing_information:['Deadline']}};
assert.match(d.card(item,0),/Metadata preview/);assert.match(d.card(item,0),/Not enough data/);assert.match(d.card(item,0),/Data completeness 20%/);assert(!d.card(item,0).includes('<img'));
assert.match(d.detail(item),/Full AI analysis has not been run/);assert.match(d.detail(item),/Missing data — not scored/);
assert.equal(d.safeUrl('javascript:alert(1)'),null);assert.equal(d.safeUrl('https://user:secret@example.com'),null);
assert.equal(d.matches(item,{fit:'1',value:''}),false);assert.equal(d.matches({...item,preliminary_scoring:{fit_score:0}},{fit:'0',value:''}),true);
assert.equal(d.matches(item,{source:'sam_gov',fit:'',currency:'EUR',value:''}),false);
assert.equal(d.matches(item,{source:'ted',fit:'',currency:'EUR',value:''}),true);
assert.equal(d.matches(item,{currency:'USD',value:''}),false);assert.equal(d.matches(item,{currency:'EUR',value:'101'}),false);
assert.equal(d.matches(item,{fit:'',value:'',deadline:'2026-12-01'}),false);
assert.match(d.sourceMessage({partial_failure:true}),/some procurement sources/);
const elements={},events={},listeners={};
function node(id){return elements[id]??={value:'',textContent:'',innerHTML:'',disabled:false,options:[],open:false,replaceChildren(...children){this.innerHTML='';this.options=children;},add(o){this.options.push(o)},addEventListener(){},querySelectorAll(){return []},closest(){return null},showModal(){this.open=true},close(){this.open=false}};}
let resolve,reject,calls=[];const context={document:{body:{classList:{toggle(){},remove(){}}},getElementById:id=>id==='onboarding'?null:node(id),querySelector:()=>null,querySelectorAll:()=>[],readyState:'complete'},window:{addEventListener:(k,f)=>{(listeners[k]??=[]).push(f);events[k]=e=>listeners[k].forEach(listener=>listener(e));},setTimeout:f=>f()},state:{organizationId:11,activeCompanyId:2,activeCompanyName:'A',uiEpoch:0},usingSharedOrganization:()=>true,canWriteWorkspace:()=>true,AbortController,URL,Option:function(text,value){this.text=text;this.value=value},location:{hash:"",replace(){}},fetch:(url,opts)=>{calls.push({url,opts});return new Promise((r,j)=>{resolve=r;reject=j;});}};
vm.runInNewContext(fs.readFileSync('app/api/static/discovery.js','utf8'),context);
// Load the actual premium script too: navigation must never hydrate a static catalog.
vm.runInNewContext(fs.readFileSync('app/api/static/premium.js','utf8'),context);
(async()=>{
 const pending=node('discoverButton').onclick();assert.equal(calls[0].url,'/api/v1/organizations/11/discover/tenders');assert.equal(calls[0].opts.credentials,'same-origin');assert.equal(calls[0].opts.method,'POST');
 context.state.organizationId=22;context.state.activeCompanyId=3;events['workspace-context']();resolve({ok:true,status:200,json:async()=>({items:[item]})});await pending;assert.equal(node('discoveryResults').innerHTML,'');
 // Two workspace epochs overlap: the newer response must win.
 const stale=node('discoverButton').onclick(),oldResolve=resolve;
 context.state.uiEpoch++;events['workspace-context']();
 const current=node('discoverButton').onclick();
 assert.equal(node('filterSource').disabled,true);assert.equal(node('filterCurrency').disabled,true);
 resolve({ok:true,status:200,json:async()=>({items:[{...item,source:'sam_gov',currency:'USD'}]})});await current;
 oldResolve({ok:true,status:200,json:async()=>({items:[item]})});await stale;
 assert.deepEqual(node('filterSource').options.map(o=>o.value),['','sam_gov']);
 assert.deepEqual(node('filterCurrency').options.map(o=>o.value),['','USD']);
 const next=node('discoverButton').onclick();resolve({ok:true,status:200,json:async()=>({items:[item],partial_failure:true,attempted_sources:['ted','eis'],successful_sources:['ted'],failed_sources:['eis']})});await next;assert.match(node('discoveryMessage').textContent,/some procurement sources/);assert.match(node('discoveryResults').innerHTML,/Metadata preview/);
 assert.equal(node('filterSource').disabled,false);assert.equal(node('filterCurrency').disabled,false);
 const values=id=>node(id).options.map(o=>o.value);
 const labels=id=>node(id).options.map(o=>o.text);
 assert.deepEqual(values('filterSource'),['','ted']);
 assert.deepEqual(labels('filterSource'),['All fetched sources','European Union - TED']);
 assert.deepEqual(labels('filterCurrency'),['All currencies','EUR']);
 assert.match(node('sourceHealth').textContent,/Unavailable: eis/);
 node('filterSource').value='ted';node('filterCurrency').value='EUR';
 async function runReport(data){const pending=node('discoverButton').onclick();resolve({ok:true,status:200,json:async()=>data});await pending;}
 const mixed={items:[item,{...item,source:'sam_gov',currency:'USD'},item,{...item,source:'custom_source',currency:'XYZ'},{...item,source:null,currency:null},{...item,source:'',currency:''},{...item,source:'  ',currency:'  '},{...item,source:123,currency:456},{...item,source:'toString',currency:' abc '},{...item,source:' ted ',currency:' EUR ' }]};
 await runReport(mixed);
 assert.deepEqual(values('filterSource'),['',' ted ','custom_source','sam_gov','ted','toString']);
 assert.deepEqual(values('filterCurrency'),['',' EUR ',' abc ','EUR','USD','XYZ']);
 assert.equal(node('filterSource').value,'ted');assert.equal(node('filterCurrency').value,'EUR');
 const stable=labels('filterSource');
 events['workspace-context']();
 assert.equal(node('filterSource').value,'ted');assert.equal(node('filterCurrency').value,'EUR');
 context.location.hash='#discover';events['hashchange']();events['workspace-context']();context.location.hash='#overview';events['hashchange']();events['workspace-context']();
 assert.deepEqual(labels('filterSource'),stable);

 await runReport({items:[...mixed.items].reverse()});
 assert.deepEqual(labels('filterSource'),stable);
 await runReport({items:[{...item,source:'sam_gov',currency:'USD'}],partial_failure:true,failed_sources:['ted']});
 assert.equal(node('filterSource').value,'');assert.equal(node('filterCurrency').value,'');
 assert.equal(node('filterValue').disabled,true);
 assert.deepEqual(values('filterSource'),['','sam_gov']);
 node('filterSource').value='sam_gov';node('filterCurrency').value='USD';
 context.state.activeCompanyId=4;context.state.uiEpoch++;events['workspace-context']();
 assert.deepEqual(values('filterSource'),['']);assert.deepEqual(values('filterCurrency'),['']);
 assert.equal(node('filterSource').value,'');assert.equal(node('filterCurrency').value,'');
 await runReport({items:[]});assert.deepEqual(values('filterSource'),['']);
 assert.match(node('discoveryMessage').textContent,/No tenders found/);
 await runReport({items:[item]});
 const failure=node('discoverButton').onclick();resolve({ok:false,status:500,json:async()=>({detail:'SECRET RAW EXCEPTION'})});await failure;assert(!node('discoveryMessage').textContent.includes('SECRET'));assert.equal(node('discoveryResults').innerHTML,'');assert.deepEqual(values('filterSource'),['']);assert.deepEqual(values('filterCurrency'),['']);
 const retry=node('discoverButton').onclick();resolve({ok:true,status:200,json:async()=>({items:[item],total_failure:true,failed_sources:['ted']})});await retry;assert.match(node('discoveryMessage').textContent,/retry discovery/);assert.deepEqual(values('filterSource'),['']);assert.deepEqual(values('filterCurrency'),['']);
 await runReport({items:[item]});
 const network=node('discoverButton').onclick();reject(new Error('offline'));await network;assert.deepEqual(values('filterSource'),['']);assert.match(node('discoveryMessage').textContent,/Network unavailable/);
 for(const status of [403,409]){await runReport({items:[item]});const denied=node('discoverButton').onclick();resolve({ok:false,status});await denied;assert.deepEqual(values('filterSource'),['']);assert.deepEqual(values('filterCurrency'),['']);assert.match(node('discoveryMessage').textContent,status===403?/access to this organization/:/activate an organization company/);}
 await runReport({items:[item]});
 const staleError=node('discoverButton').onclick(),oldReject=reject;context.state.organizationId=33;context.state.uiEpoch++;events['workspace-context']();await runReport({items:[{...item,source:'sam_gov',currency:'USD'}]});oldReject(new Error('stale offline'));await staleError;assert.deepEqual(values('filterSource'),['','sam_gov']);assert(!node('discoveryMessage').textContent.includes('Network unavailable'));
 let redirected='';context.location.replace=url=>redirected=url;const unauthenticated=node('discoverButton').onclick();resolve({ok:false,status:401});await unauthenticated;assert.equal(redirected,'/login');
 console.log('Discovery rendering, filters, safe links, partial failure, repeatability and stale responses: passed');
})().catch(e=>{console.error(e);process.exitCode=1});
