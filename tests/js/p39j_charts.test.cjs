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
 addEventListener(k,f){this.listeners[k]=f;}fire(k='click'){assert.ok(this.listeners[k],this.tag+' '+k);this.listeners[k]();}
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

const crypto=require('node:crypto');
const css=html.match(/<style>([\s\S]*?)<\/style>/)[1];
for(const asset of [source,css])assert.ok(html.includes("'sha256-"+crypto.createHash('sha256').update(asset).digest('base64')+"'"));
assert.equal(css,fs.readFileSync('scripts/p39e_preview/style.css','utf8').replace(/\r\n/g,'\n'));
assert.ok(html.includes("connect-src 'none'"));
assert.doesNotMatch(source,/innerHTML|outerHTML|insertAdjacentHTML|fetch\(|XMLHttpRequest/);
for(const marker of ['repeat(2,minmax(0,1fr))','@media(max-width:480px)','overflow-wrap:anywhere','prefers-reduced-motion',':focus-visible','.source-row[aria-pressed=true]'])assert.ok(css.includes(marker));
assert.deepEqual(Object.keys(data.cases).sort(),['normal','empty','unknown','legacy','foreign','future','filtered'].sort());
assert.deepEqual(api.names.map(n=>data.cases.normal.kpis[n].value),[4,2,2,1,1,1]);
const walk=e=>[e,...e.children.flatMap(walk)];
for(const locale of ['en','ru']){
 const h=harness(locale),n=h.nodes;Element.prototype.focus=function(){h.document.activeElement=this;};
 for(const scenario of Object.keys(data.cases)){
  n.scenario.value=scenario;n.scenario.fire('change');
  const r=data.cases[scenario],p=api.analyticsEvidence(r);
  for(const k of ['chartActivity','chartGeography','chartIndustry','chartSources','insufficient','trendMissing','countryMissing','industryMissing','sourceBasis','calendarScale'])assert.ok(h.all.some(e=>e.getAttribute('data-i18n')===k&&e.textContent===api.translate(locale,k)),k);
  for(const panel of h.all.filter(e=>(e.attributes.class||'').includes('unavailable-panel')))assert.equal(walk(panel).filter(e=>e.tag==='button'||e.tag==='svg').length,0);
  const buttons=n['chart-sources'].children.filter(e=>e.tag==='button');assert.equal(buttons.length,p.sources.groups.length);
  if(!r.U.length)assert.equal(n['chart-sources'].textContent,api.translate(locale,'sourceEmpty'));
  buttons.forEach((b,i)=>{
   const g=p.sources.groups[i];assert.equal(b.getAttribute('data-source'),g.label);assert.equal(b.getAttribute('aria-controls'),'records detail');assert.ok(b.getAttribute('aria-label').includes(api.translate(locale,'sourceGroup')));assert.ok(b.getAttribute('title').includes(api.translate(locale,'keyboardEvidence')));
   const rects=walk(b).filter(e=>e.tag==='rect');assert.equal(Number(rects[1].getAttribute('width')),g.numerator/g.denominator*300);assert.equal(Number(rects[0].getAttribute('width')),300);
   b.focus();assert.equal(h.document.activeElement,b);b.fire();assert.equal(b.getAttribute('aria-pressed'),'true');
   assert.deepEqual(n.records.children.filter(e=>e.tag==='button').map(e=>JSON.parse(e.getAttribute('data-record-id'))),g.identities);for(const id of g.identities)assert.ok(n.detail.textContent.includes(id.join(' / ')));
   n['clear-group'].fire();assert.equal(b.getAttribute('aria-pressed'),'false');
  });
  for(const track of n.deadline.children){
   const bs=track.children.filter(e=>e.tag==='button');for(const b of bs){
    const type=b.getAttribute('data-deadline-type'),day=b.getAttribute('data-day'),g=p.deadlines.groups.find(g=>g.type===type&&g.day===day);assert.ok(g);
    const rect=walk(b).find(e=>e.tag==='rect');assert.equal(Number(rect.getAttribute('width')),api.width(g.numerator,g.denominator)*1.6);
    b.fire();assert.equal(b.getAttribute('aria-pressed'),'true');assert.deepEqual(n.records.children.filter(e=>e.tag==='button').map(e=>JSON.parse(e.getAttribute('data-record-id'))),g.identities);n.reset.fire();
   }
  }
  for(const e of walk(h.root))if(e.tag==='rect')for(const attr of ['width','height','x','y','rx'])assert.ok(Number.isFinite(Number(e.getAttribute(attr)))&&Number(e.getAttribute(attr))>=0);
  const unknown=api.model(r).find(m=>m.name==='Fit unknown');assert.equal(unknown.n,Object.values(r.unknown_fit).flat().length);assert.equal(unknown.d,r.U.length);
  for(const b of n.cards.children)assert.equal(b.children[1].textContent,r.kpis[api.names[Number(b.getAttribute('data-metric'))]].value===null?api.translate(locale,'noData'):new Intl.NumberFormat(locale).format(r.kpis[api.names[Number(b.getAttribute('data-metric'))]].value));
  n['lang-'+(locale==='en'?'ru':'en')].fire();assert.ok(n['chart-sources'].children.every(e=>e.tag!=='button'||e.getAttribute('aria-pressed')==='false'));n['lang-'+locale].fire();
 }
}
assert.deepEqual([...new Set(data.cases.normal.deadline_grouping.buckets.map(b=>b[0]))].sort(),['date_only','instant']);
assert.equal(JSON.stringify(data),snapshot);
// Long official source strings remain inert and the visual uses bounded SVG coordinates.
const long='<img src=x onerror=alert(1)>'+ 'X'.repeat(1000),hostile=JSON.parse(JSON.stringify(data));
const r=hostile.cases.normal;const replace=ids=>ids.map(i=>[long,i[1]]);r.U=replace(r.U);for(const m of Object.values(r.kpis))if(m.unit==='unique_tender_identity')m.identities=replace(m.identities);for(const m of Object.values(r.fit_bands))m.identities=replace(m.identities);for(const k of Object.keys(r.unknown_fit))r.unknown_fit[k]=replace(r.unknown_fit[k]);for(const f of r.fits)f.identity=[long,f.identity[1]];for(const a of [...r.deadline_grouping.buckets,...r.deadline_grouping.states])a[2]=replace(a[2]);
const originalNormal=data.cases.normal;data.cases.normal=r;try{const h=harness();const b=h.nodes['chart-sources'].children[0];assert.equal(b.children[0].textContent,long);assert.equal(walk(b).filter(e=>e.tag==='img').length,0);b.fire();assert.equal(h.nodes.records.children.length,r.U.length);}finally{data.cases.normal=originalNormal;}
require('./p39h_i18n.test.cjs');require('./p39h_interactions.test.cjs');require('./p39h_visual.test.cjs');
console.log('P4B CHARTS PASS: seven scenarios × EN/RU, exact groups, typed dates, geometry, missing evidence, CSP, redraw and safe long labels');
