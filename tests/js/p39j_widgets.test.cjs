'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const api=require('../../scripts/p39e_preview/view.js');
const html=fs.readFileSync(process.argv[2],'utf8');
const source=html.match(/<script>([\s\S]*?)<\/script>/)[1];
assert.equal(source,fs.readFileSync('scripts/p39e_preview/view.js','utf8').replace(/\r\n/g,'\n'),'Test the final builder output, never a stale bundle');
const data=JSON.parse(html.match(/<script id="fixture" type="application\/json">([\s\S]*?)<\/script>/)[1]);
const snapshot=JSON.stringify(data);
assert.match(html,/<html lang="en">/);
assert.ok(api.validateDictionary());
for(const k of Object.keys(api.dictionary)){
 for(const l of ['en','ru'])assert.ok(api.translate(l,k));
 assert.doesNotMatch(api.translate('en',k),/[А-Яа-яЁё]/);
 const ru=api.translate('ru',k).replace(/VALYQON AI|CPV|P3\.9|P4|P5|\bH\b|ted\s*\/\s*(?:high|zero)/g,'');
 assert.doesNotMatch(ru,/[A-Za-z]/,'Russian translation contains English prose: '+k);
}
for(const l of ['en','ru'])assert.throws(()=>api.translate(l,'missing.key'));
const saved=api.dictionary.noData.ru;api.dictionary.noData.ru=undefined;
assert.throws(()=>api.translate('ru','noData'),/Отсутствует перевод/);assert.throws(()=>api.validateDictionary());api.dictionary.noData.ru=saved;
assert.equal(api.initialLanguage({getItem:()=>null}),'en');assert.equal(api.initialLanguage({getItem:()=> 'invalid'}),'en');assert.equal(api.initialLanguage({getItem:()=> 'ru'}),'ru');assert.equal(api.initialLanguage({getItem(){throw Error('denied');}}),'en');
class Element{
 constructor(tag='div'){this.tag=tag;this.children=[];this.attributes={};this.listeners={};this.value='';this.own='';}
 get textContent(){return this.own+this.children.map(x=>x.textContent).join('');}
 set textContent(v){this.own=String(v);this.children=[];}
 append(...xs){this.children.push(...xs);if(this.tag==='select'&&this.children.length===xs.length&&xs[0])this.value=xs[0].value;}
 replaceChildren(...xs){this.children=[];this.own='';this.append(...xs);}
 setAttribute(k,v){this.attributes[k]=String(v);if(k==='value')this.value=String(v);}
 getAttribute(k){return this.attributes[k];}removeAttribute(k){delete this.attributes[k];}
 addEventListener(k,f){this.listeners[k]=f;}fire(k='click'){assert.ok(this.listeners[k],this.tag+' '+k);this.listeners[k]({key:'Enter'});}
}
function harness(savedLanguage=null,denied=false){
 const all=[],nodes={},root=new Element('root'),stack=[root];
 const markup=html.replace(/<style>[\s\S]*?<\/style>/g,'').replace(/<script[^>]*>[\s\S]*?<\/script>/g,'').replace(/<noscript>[\s\S]*?<\/noscript>/g,'');
 for(const token of markup.match(/<[^>]+>|[^<]+/g)){
  if(token.startsWith('</')){if(stack.length>1)stack.pop();continue;}
  if(token.startsWith('<!'))continue;
  if(token.startsWith('<')){const tag=token.match(/^<([^\s>]+)/)[1],e=new Element(tag);for(const m of token.matchAll(/([\w-]+)="([^"]*)"/g))e.setAttribute(m[1],m[2]);all.push(e);if(e.attributes.id)nodes[e.attributes.id]=e;stack.at(-1).append(e);if(!['meta','input','br'].includes(tag))stack.push(e);}
  else stack.at(-1).own+=' '+token;
 }
 nodes.fixture=new Element('script');nodes.fixture.textContent=JSON.stringify(data);
 const document={documentElement:all.find(e=>e.tag==='html'),getElementById:id=>nodes[id],createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag),querySelectorAll:s=>s==='nav a'?all.filter(e=>e.tag==='a'):all.filter(e=>Object.hasOwn(e.attributes,s.slice(1,-1)))};
 const memory=new Map(savedLanguage?[['valyqon.preview.language',savedLanguage]]:[]);
 const localStorage={getItem(k){if(denied)throw Error('denied');return memory.get(k)||null;},setItem(k,v){if(denied)throw Error('denied');memory.set(k,v);}};
 vm.runInNewContext(source,{document,localStorage,Intl});return {nodes,document,all,memory,root};
}


const crypto=require('node:crypto'),css=html.match(/<style>([\s\S]*?)<\/style>/)[1];
assert.equal(css,fs.readFileSync('scripts/p39e_preview/style.css','utf8').replace(/\r\n/g,'\n'));
for(const asset of [source,css])assert.ok(html.includes("'sha256-"+crypto.createHash('sha256').update(asset).digest('base64')+"'"));
assert.ok(html.includes("connect-src 'none'"));
assert.doesNotMatch(source,/innerHTML|outerHTML|insertAdjacentHTML|fetch\(|XMLHttpRequest/);
const walk=e=>[e,...e.children.flatMap(walk)];
for(const locale of ['en','ru']){
 const h=harness(locale),n=h.nodes;Element.prototype.focus=function(){h.document.activeElement=this;};
 for(const scenario of Object.keys(data.cases)){
  n.scenario.value=scenario;n.scenario.fire('change');const r=data.cases[scenario],p=api.analyticsEvidence(r);
  const frozen=JSON.stringify(r),cards=n.cards.textContent;
  const top=n['top-records'].children.filter(e=>e.tag==='button');
  assert.deepEqual(top.map(b=>JSON.parse(b.getAttribute('data-widget-id'))),api.project(api.rows(r),'','','','fit').map(x=>x.identity));
  assert.equal(top.length,r.U.length);
  for(const b of top){
   assert.equal(b.tag,'button');assert.equal(b.getAttribute('aria-controls'),'records detail identity-body');assert.ok(b.getAttribute('aria-label').startsWith(api.translate(locale,'open')));
   b.focus();assert.equal(h.document.activeElement,b);b.fire();
   const id=b.getAttribute('data-widget-id');assert.ok(n['identity-body'].textContent.includes(JSON.parse(id).join(' / ')));
   assert.ok(n['identity-body'].textContent.includes(api.translate(locale,'noScores')));
   assert.equal(h.document.activeElement.getAttribute('data-record-id'),id);
   assert.equal(n.records.children.filter(e=>e.tag==='button').length,r.U.length);
   const close=n['identity-body'].children.at(-1);assert.equal(close.textContent,api.translate(locale,'closeDetails'));close.fire();
   assert.equal(n['identity-body'].textContent,api.translate(locale,'recordHint'));assert.equal(h.document.activeElement.getAttribute('data-record-id'),id);
  }
  const coverage=n['widget-coverage'].children.filter(e=>e.tag==='button');
  assert.equal(coverage.length,2);
  coverage.forEach((b,i)=>{const g=p.coverage.groups[i];assert.equal(b.children[1].textContent,g.numerator+' / '+g.denominator);b.fire();assert.deepEqual(n.records.children.filter(e=>e.tag==='button').map(b=>JSON.parse(b.getAttribute('data-record-id'))),api.project(api.rows(r),'','','','identity',new Set(g.identities.map(api.key))).map(x=>x.identity));assert.equal(n['filter-chips'].children.at(-1).getAttribute('data-clear-filter'),'group');n['filter-chips'].children.at(-1).fire();assert.equal(n.records.children.filter(e=>e.tag==='button').length,r.U.length);});
  const events=r.selected_events.slice().sort((a,b)=>Date.parse(b[1])-Date.parse(a[1])||a[0]-b[0]);
  assert.deepEqual(n['widget-activity'].children.filter(e=>e.getAttribute('data-event-id')!==undefined).map(e=>Number(e.getAttribute('data-event-id'))),events.map(e=>e[0]));
  assert.equal(walk(n['widget-activity']).filter(e=>e.tag==='button'||e.tag==='svg').length,0);
  if(!events.length)assert.equal(n['widget-activity'].textContent,api.translate(locale,'activityEmpty'));
  assert.ok(n['widget-coverage'].textContent.includes(api.translate(locale,'analyticsUnavailable')));
  assert.equal(p.countries.numerator,null);assert.equal(p.categories.groups,null);
  const sourceButtons=n['widget-sources'].children.filter(e=>e.tag==='button');
  assert.equal(sourceButtons.length,p.sources.groups.length);
  sourceButtons.forEach((b,i)=>{b.fire();assert.deepEqual(n.records.children.filter(e=>e.tag==='button').map(b=>JSON.parse(b.getAttribute('data-record-id'))),api.project(api.rows(r),'','','','identity',new Set(p.sources.groups[i].identities.map(api.key))).map(x=>x.identity));n.reset.fire();});
  for(const [id,value,event]of [['search','zero','input'],['fit-filter','unknown','change'],['deadline-filter',r.deadline_grouping.states[0]?.slice(0,2).join(' / ')||'','change']]){
   if(!value)continue;n[id].value=value;n[id].fire(event);
   const chip=n['filter-chips'].children.find(e=>e.getAttribute('data-clear-filter')===id);assert.ok(chip);assert.ok(chip.getAttribute('aria-label').startsWith(api.translate(locale,'clearFilter')));chip.fire();assert.equal(n[id].value,'');assert.equal(h.document.activeElement,n[id]);
  }
  n.search.value='zero';n.search.fire('input');n['fit-filter'].value='low';n['fit-filter'].fire('change');
  const opposite=locale==='en'?'ru':'en';n['lang-'+opposite].fire();assert.equal(n.search.value,'zero');assert.equal(n['fit-filter'].value,'low');assert.equal(n['identity-body'].textContent,api.translate(opposite,'recordHint'));n['lang-'+locale].fire();
  n.reset.fire();assert.equal(n['filter-chips'].children.length,0);assert.equal(n.search.value,'');assert.equal(n['fit-filter'].value,'');
  assert.equal(n.cards.textContent,cards);assert.equal(JSON.stringify(r),frozen);
  if(top.length)top[0].fire();n.scenario.value='empty';n.scenario.fire('change');assert.equal(n['identity-body'].textContent,api.translate(locale,'recordHint'));assert.equal(n['top-records'].children.filter(e=>e.tag==='button').length,0);assert.equal(n['filter-chips'].children.length,0);
 }
 n.scenario.value='invalid';n.scenario.fire('change');for(const id of ['top-records','widget-coverage','widget-activity','widget-sources','filter-chips','identity-body'])assert.equal(n[id].children.length,0);
}
assert.equal(JSON.stringify(data),snapshot);
assert.deepEqual(api.names.map(n=>data.cases.normal.kpis[n].value),[4,2,2,1,1,1]);
require('./p39h_i18n.test.cjs');require('./p39h_interactions.test.cjs');require('./p39h_visual.test.cjs');
console.log('P5A WIDGETS PASS: generated HTML, seven scenarios × EN/RU, sorted identities, exact coverage/events/sources, chips/reset, focus structure, isolation, immutable KPIs');
