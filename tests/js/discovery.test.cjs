const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const d=require('../../app/api/static/discovery.js');
const item={title:'<img src=x onerror=alert(1)>',source:'ted',customer:'Buyer',currency:'EUR',initial_price:100,full_ai_analyzed:false,preliminary_scoring:{fit_score:null,completeness_percent:20,criteria:[{label:'Budget',status:'not_scored',explanation:'Missing value',weight:20,earned_points:0}],missing_information:['Deadline']}};
assert.match(d.card(item,0),/Metadata preview/);assert.match(d.card(item,0),/Not enough data/);assert.match(d.card(item,0),/Data completeness 20%/);assert(!d.card(item,0).includes('<img'));
assert.match(d.detail(item),/Full AI analysis has not been run/);assert.match(d.detail(item),/Missing data — not scored/);
assert.equal(d.safeUrl('javascript:alert(1)'),null);assert.equal(d.safeUrl('https://user:secret@example.com'),null);
assert.equal(d.matches(item,{fit:'1',value:''}),false);assert.equal(d.matches({...item,preliminary_scoring:{fit_score:0}},{fit:'0',value:''}),true);
assert.equal(d.matches(item,{currency:'USD',value:''}),false);assert.equal(d.matches(item,{currency:'EUR',value:'101'}),false);
assert.equal(d.matches(item,{fit:'',value:'',deadline:'2026-12-01'}),false);
assert.match(d.sourceMessage({partial_failure:true}),/some procurement sources/);
const elements={},events={};
function node(id){return elements[id]??={value:'',textContent:'',innerHTML:'',disabled:false,options:[],open:false,replaceChildren(...children){this.innerHTML='';this.options=children;},add(o){this.options.push(o)},addEventListener(){},querySelectorAll(){return []},showModal(){this.open=true},close(){this.open=false}};}
let resolve,calls=[];const context={document:{getElementById:node},window:{addEventListener:(k,f)=>events[k]=f},state:{organizationId:11,activeCompanyId:2,activeCompanyName:'A',uiEpoch:0},usingSharedOrganization:()=>true,canWriteWorkspace:()=>true,AbortController,URL,Option:function(text,value){this.text=text;this.value=value},location:{hash:"",replace(){}},fetch:(url,opts)=>{calls.push({url,opts});return new Promise(r=>resolve=r);}};
vm.runInNewContext(fs.readFileSync('app/api/static/discovery.js','utf8'),context);
(async()=>{
 const pending=node('discoverButton').onclick();assert.equal(calls[0].url,'/api/v1/organizations/11/discover/tenders');assert.equal(calls[0].opts.credentials,'same-origin');assert.equal(calls[0].opts.method,'POST');
 context.state.organizationId=22;context.state.activeCompanyId=3;events['workspace-context']();resolve({ok:true,status:200,json:async()=>({items:[item]})});await pending;assert.equal(node('discoveryResults').innerHTML,'');
 const next=node('discoverButton').onclick();resolve({ok:true,status:200,json:async()=>({items:[item],partial_failure:true,attempted_sources:['ted','eis'],successful_sources:['ted'],failed_sources:['eis']})});await next;assert.match(node('discoveryMessage').textContent,/some procurement sources/);assert.match(node('discoveryResults').innerHTML,/Metadata preview/);
 const failure=node('discoverButton').onclick();resolve({ok:false,status:500,json:async()=>({detail:'SECRET RAW EXCEPTION'})});await failure;assert(!node('discoveryMessage').textContent.includes('SECRET'));assert.equal(node('discoveryResults').innerHTML,'');
 const retry=node('discoverButton').onclick();resolve({ok:true,status:200,json:async()=>({items:[],total_failure:true})});await retry;assert.match(node('discoveryMessage').textContent,/retry discovery/);
 console.log('Discovery rendering, filters, safe links, partial failure, repeatability and stale responses: passed');
})().catch(e=>{console.error(e);process.exitCode=1});
