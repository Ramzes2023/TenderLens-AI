const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(process.argv[2], 'utf8');

function element() {
  return {textContent:'', dataset:{}, hidden:false, attributes:{},
    classList:{remove(){}, toggle(){return true}, contains(){return false}},
    setAttribute(k,v){this.attributes[k]=v}, removeAttribute(k){delete this.attributes[k]},
    addEventListener(){}, focus(){}, append(){}, closest(){return this}};
}

// Execute the actual navigation code against every generated destination.
const nodes = {}, get = id => nodes[id] ||= element();
const links = [...html.matchAll(/<a href="#([^"]+)" data-nav="([^"]+)">[\s\S]*?<span>([^<]+)<\/span>/g)]
  .map(m => Object.assign(element(), {dataset:{nav:m[2]},textContent:m[3]}));
assert.equal(links.length,15);
const articles = ['companies','companyCreator','tenders','monitoringCenter','organizationCard','telegramCard'].map(get);
const sections = [...html.matchAll(/data-page="([^"]+)"/g)]
  .map(m => Object.assign(element(), {dataset:{page:m[1]}}));
const events = {}, location = {hash:''};
const context = {document:{getElementById:get,
  querySelector(selector){return selector==='.workspace-context'?get('context'):links.find(l=>selector.includes(`"${l.dataset.nav}"`))},
  querySelectorAll(selector){return selector==='[data-nav]'?links:selector==='[data-page]'?[...sections,...articles]:[]}},
  location, CSS:{escape:x=>x}, window:{addEventListener:(k,f)=>events[k]=f,
    dispatchEvent(){},matchMedia:()=>({addEventListener(){}})}, Event:class {}};
vm.runInNewContext(fs.readFileSync('app/api/static/shell.js','utf8').split('/* Workspace lifecycle:')[0],context);
for (const link of links) {
  location.hash='#'+link.dataset.nav; events.hashchange();
  assert.equal(get('pageHeading').textContent,link.textContent);
  assert.equal(link.attributes['aria-current'],'page');
  const future=['recommended','notifications','billing','ai-analysis'].includes(link.dataset.nav);
  assert.equal(get('futurePage').hidden,!future);
  if(future) assert.match(get('futureText').textContent,/not available/);
  if(link.dataset.nav==='billing') assert.equal(get('futureNext').hidden,true);
  if(link.dataset.nav==='recommended') assert.equal(get('futureNext').href,'#discover');
  if(link.dataset.nav==='notifications') assert.equal(get('futureNext').href,'#settings');
}
location.hash='#missing-page';events.hashchange();
assert.equal(get('pageHeading').textContent,'Overview');

// Command palette buttons are derived from those same real navigation links.
get('commandPalette').close=()=>{};get('commandPalette').showModal=()=>{};
get('commandQuery').value='';get('commandResults').children=[];
get('commandResults').replaceChildren=function(){this.children=[]};
get('commandResults').append=function(child){this.children.push(child)};
context.document.createElement=element;
vm.runInNewContext(fs.readFileSync('app/api/static/premium.js','utf8').split('/* VALYQON OVERVIEW V2 */')[0],context);
get('openCommands').onclick();
assert.equal(get('commandResults').children.length,links.length);
for (const [i,button] of get('commandResults').children.entries()) {
  button.onclick();assert.equal(location.hash,links[i].dataset.nav);
}

// Exercise real Discover action listeners with mocked requests only.
const dnodes={},dget=id=>dnodes[id]||=(Object.assign(element(),{
  value:'',innerHTML:'',disabled:false,options:[],open:false,
  replaceChildren(...children){this.innerHTML='';this.options=children},add(o){this.options.push(o)},
  querySelector(){return dget('shortlistStatus')},querySelectorAll(){return []},
  showModal(){this.open=true},close(){this.open=false}}));
let failure=false, saved=true, writable=true;
const item={source:'ted',external_id:'audit',title:'Opportunity',currency:'EUR'};
const calls=[];
const dcontext={document:{getElementById:dget},window:{addEventListener(){},dispatchEvent(){}},
  state:{organizationId:1,activeCompanyId:2,activeCompanyName:'Company',uiEpoch:0},
  usingSharedOrganization:()=>true,canWriteWorkspace:()=>writable,
  AbortController,URL,location:{hash:'#discover',replace(){}},
  Option:function(text,value){this.text=text;this.value=value},
  fetch:async(url,options={})=>{
    calls.push([url,options]);
    if(failure && options.method) return {ok:false,status:500,json:async()=>({detail:'SQL SECRET'})};
    return {ok:true,status:200,json:async()=>url.endsWith('/discover/tenders')
      ? {items:[item]} : saved?[{id:3,opportunity:item}]:[]};
  }};
vm.runInNewContext(fs.readFileSync('app/api/static/discovery.js','utf8'),dcontext);
const settle=()=>new Promise(resolve=>setImmediate(resolve));
async function run(){
  const copyFunction=html.match(/async function copyInviteLink\(\)\{[\s\S]*?\n\}/)[0];
  const inviteNodes={inviteLink:{value:'http://localhost/invite/audit',focus(){},select(){}},inviteMessage:{}};
  const copyContext={navigator:{clipboard:{writeText:async()=>{throw new Error('denied')}}},
    document:{getElementById:id=>inviteNodes[id],execCommand:()=>false}};
  vm.runInNewContext(copyFunction,copyContext);
  await copyContext.copyInviteLink();
  assert.match(inviteNodes.inviteMessage.innerHTML,/copy the invitation link manually/);
  copyContext.document.execCommand=()=>true;
  await copyContext.copyInviteLink();
  assert.match(inviteNodes.inviteMessage.innerHTML,/Invitation link copied/);
  await dget('discoverButton').onclick();await settle();
  dget('discoveryResults').onclick({target:{closest:s=>s==='[data-detail]'?{dataset:{detail:'0'}}:null}});
  failure=true;
  const remove=Object.assign(element(),{dataset:{remove:'0'}});
  dget('detailBody').onclick({target:{closest:s=>s==='[data-remove]'?remove:null}});await settle();
  assert.match(dget('shortlistStatus').textContent,/could not be removed/);
  assert.equal(remove.disabled,false);
  failure=false;saved=false;
  await dget('discoverButton').onclick();await settle();failure=true;
  const save=Object.assign(element(),{dataset:{save:'0'}});
  dget('discoveryResults').onclick({target:{closest:s=>s==='[data-save]'?save:null}});await settle();
  assert.match(dget('discoveryMessage').textContent,/could not be saved/);
  assert.equal(save.disabled,false);
  assert(!dget('discoveryMessage').textContent.includes('SQL SECRET'));
  failure=false;writable=false;
  await dget('discoverButton').onclick();await settle();
  assert(!dget('discoveryResults').innerHTML.includes('data-save='));
  assert(calls.every(([url])=>url.startsWith('/api/v1/organizations/1/')));
  console.log('All navigation, future pages, palette commands and shortlist failure states passed.');
}
run().catch(error=>{console.error(error);process.exitCode=1});
