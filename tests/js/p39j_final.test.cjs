'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const api=require('../../scripts/p39e_preview/view.js');
assert.ok(process.argv[2],'Generated HTML path required');
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
const csp=html.match(/http-equiv="Content-Security-Policy" content="([^"]+)"/)[1];
for(const asset of [source,css])assert.ok(csp.includes("'sha256-"+crypto.createHash('sha256').update(asset).digest('base64')+"'"));
for(const directive of ["default-src 'none'","connect-src 'none'","img-src 'none'","base-uri 'none'","form-action 'none'"])assert.ok(csp.includes(directive));
assert.doesNotMatch((html.replaceAll('http://www.w3.org/2000/svg','')),/https?:\/\/|<script\s+src=|<link\b|@import|url\s*\(|fetch\s*\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon|innerHTML|outerHTML|insertAdjacentHTML|document\.write/i);
for(const marker of [':focus-visible','@media(max-width:480px)','overflow-wrap:anywhere','prefers-reduced-motion','transition:none!important','animation:none!important'])assert.ok(css.includes(marker));
assert.deepEqual(Object.keys(data.cases).sort(),['normal','empty','unknown','legacy','foreign','future','filtered'].sort());
const walk=e=>[e,...e.children.flatMap(walk)];
for(const locale of ['en','ru']){
 const h=harness(locale,true),n=h.nodes;Element.prototype.focus=function(){h.document.activeElement=this;};
 // Denied storage defaults safely to EN; selecting RU works in memory.
 if(locale==='ru')n['lang-ru'].fire();
 assert.equal(h.document.documentElement.lang,locale);
 assert.ok(h.all.some(e=>e.tag==='title'&&e.textContent===api.translate(locale,'pageTitle')));
 assert.equal(n['storage-note'].textContent,api.translate(locale,'storageDenied'));
 for(const scenario of Object.keys(data.cases)){
  n.scenario.value=scenario;n.scenario.fire('change');const r=data.cases[scenario],p=api.analyticsEvidence(r);
  assert.ok(h.root.textContent.includes(api.translate(locale,'badge')));
  for(const attr of ['data-i18n','data-i18n-aria','data-i18n-placeholder'])for(const e of h.all.filter(e=>e.getAttribute(attr)))assert.equal(attr==='data-i18n'?e.textContent:e.getAttribute(attr==='data-i18n-aria'?'aria-label':'placeholder'),api.translate(locale,e.getAttribute(attr)));
  for(const panel of h.all.filter(e=>(e.attributes.class||'').includes('unavailable-panel'))){assert.ok(panel.textContent.includes(api.translate(locale,'insufficient')));assert.equal(walk(panel).filter(e=>['svg','button'].includes(e.tag)).length,0);}
  for(const k of ['countries','categories']){assert.equal(p[k].numerator,null);assert.equal(p[k].groups,null);}
  for(const [i,b]of n.cards.children.entries())assert.equal(b.children[1].textContent,r.kpis[api.names[i]].value===null?api.translate(locale,'noData'):new Intl.NumberFormat(locale).format(r.kpis[api.names[i]].value));
  assert.equal(n['top-records'].children.filter(e=>e.tag==='button').length,r.U.length);
  assert.equal(n['widget-activity'].children.filter(e=>e.getAttribute('data-event-id')!==undefined).length,r.selected_events.length);
  for(const e of walk(h.root)){
   if(e.tag==='button'){assert.ok(e.listeners.click,'Native keyboard button has click handler');assert.notEqual(e.getAttribute('tabindex'),'-1');}
   if(e.tag==='svg'){assert.ok(e.getAttribute('aria-hidden')==='true'||e.getAttribute('aria-label'));const box=e.getAttribute('viewBox').split(' ').map(Number);assert.equal(box.length,4);assert.ok(box.every(Number.isFinite));assert.ok(box[2]>0&&box[3]>0);}
   if(['rect','circle'].includes(e.tag))for(const attr of ['width','height','r','rx'])if(e.getAttribute(attr)!==undefined)assert.ok(Number.isFinite(Number(e.getAttribute(attr)))&&Number(e.getAttribute(attr))>=0);
  }
  const first=n.records.children.find(e=>e.tag==='button');
  if(first){first.fire();assert.notEqual(n['identity-body'].textContent,api.translate(locale,'recordHint'));n.search.value='<svg onload=alert(1)>'+ 'x'.repeat(10000);n.search.fire('input');assert.equal(n['identity-body'].textContent,api.translate(locale,'recordHint'));assert.equal(n.detail.textContent,api.translate(locale,'cleared'));assert.equal(n.records.textContent,api.translate(locale,'empty'));n.reset.fire();assert.ok(n.records.children.every(b=>b.getAttribute('aria-pressed')==='false'));}
  n.search.value='\u0000[.*';n.search.fire('input');assert.equal(n.records.textContent,api.translate(locale,'empty'));n.reset.fire();
  n.scenario.value='malformed';n.scenario.fire('change');assert.equal(n.status.textContent,api.translate(locale,'error'));for(const id of ['cards','chart-sources','top-records','widget-coverage','widget-activity','widget-sources','records','identity-body'])assert.equal(n[id].children.length,0);
 }
}
const clone=x=>JSON.parse(JSON.stringify(x));
for(const unit of ['Active Sources','Countries']){
 const r=clone(data.cases.normal),m=r.kpis[unit];m.identities.push(m.identities[0]);m.numerator=m.identities.length;m.denominator=Math.max(m.denominator,m.numerator);assert.throws(()=>api.analyticsEvidence(r));
 const x=clone(data.cases.normal);x.kpis[unit].identities[0]={bad:'membership'};assert.throws(()=>api.analyticsEvidence(x));
}
for(const value of [-1,NaN,Infinity,Number.MAX_SAFE_INTEGER+1,'10',null]){assert.throws(()=>api.width(value,4));assert.throws(()=>api.width(1,value));}
assert.equal(JSON.stringify(data),snapshot);
assert.deepEqual(api.names.map(n=>data.cases.normal.kpis[n].value),[4,2,2,1,1,1]);
// Preserve independent stage contracts, including long hostile source labels and exact drilldown.
require('./p39j_evidence.test.cjs');require('./p39j_charts.test.cjs');require('./p39j_widgets.test.cjs');require('./p39e_preview.test.cjs');require('./p39h_offline_contract.test.cjs');
console.log('QA FINAL PASS: generated assets/CSP, seven scenarios × EN/RU, native keyboard structure, geometry, stale selection, malformed input, immutable data. Real browser acceptance is separate.');
