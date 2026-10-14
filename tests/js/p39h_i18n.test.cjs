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
function audit(h,locale){
 assert.equal(h.document.documentElement.lang,locale);
 for(const [attr,target]of [['data-i18n',null],['data-i18n-aria','aria-label'],['data-i18n-placeholder','placeholder']])for(const node of h.all.filter(e=>e.getAttribute(attr))){const expected=api.translate(locale,node.getAttribute(attr));assert.equal(target?node.getAttribute(target):node.textContent,expected);}
 function geometry(e){if(e.tag==='circle')for(const k of ['cx','cy','r'])assert.ok(Number.isFinite(Number(e.attributes[k]))&&Number(e.attributes[k])>=0);if(e.attributes['stroke-dasharray'])for(const n of e.attributes['stroke-dasharray'].split(' '))assert.ok(Number.isFinite(Number(n))&&Number(n)>=0);if(e.tag==='path')assert.equal(e.attributes.d,'M 4 12 L 156 12');e.children.forEach(geometry);}geometry(h.root);
 for(const b of [...h.nodes.cards.children,...h.nodes.fit.children]){assert.equal(b.tag,'button');assert.ok(b.getAttribute('title').includes(api.translate(locale,'keyboardEvidence')));}
 assert.ok(h.nodes.ring.textContent.includes(api.translate(locale,'coverageGraphic')));
 for(const track of h.nodes.deadline.children)assert.ok(track.textContent.includes(api.translate(locale,'bucketGraphic')));
 const texts=[];function visit(e){if(e===h.nodes.provenance||e===h.nodes.fixture)return;texts.push(e.own,...['aria-label','title','placeholder'].map(k=>e.attributes[k]||''));e.children.forEach(visit);}visit(h.root);
 const text=texts.join('\n');if(locale==='en')assert.doesNotMatch(text,/[А-Яа-яЁё]/,'No Russian in English visible or accessible strings');
 else assert.doesNotMatch(text,/High Fit|Opportunity Explorer|OFFLINE TEST FIXTURE|Population commitment|Historical|Closing Soon|No data|Unavailable|closing_soon|date_only|missing_or_malformed_score|scope_mismatch|version_conflict|source \/ notice|TEST DATA|public rollout|BLOCKED|PARTIAL/,'No English UI or untranslated enums in Russian');
 if(locale==='ru'){
  const allowed=new Set(['VALYQON','AI','V','EN','RU','H','CPV','P3','P4','P5']);
  for(const r of Object.values(data.cases)){
   for(const pair of r.U)for(const value of pair)for(const token of value.match(/[A-Za-z]+[0-9]*/g)||[])allowed.add(token);
   for(const value of [...r.kpis['Active Sources'].identities,...r.kpis.Countries.identities,r.context.timezone])for(const token of String(value).match(/[A-Za-z]+[0-9]*/g)||[])allowed.add(token);
  }
  for(const token of text.match(/[A-Za-z]+[0-9]*/g)||[])assert.ok(allowed.has(token),'Unexpected English token in Russian UI: '+token);
 }
 assert.ok(h.nodes.cards.children.length===6);assert.equal(h.nodes['lang-'+locale].getAttribute('aria-pressed'),'true');
 assert.equal(h.nodes.ring.children[0].getAttribute('aria-label'),api.translate(locale,'ringAria'));
}
const h=harness();assert.equal(h.document.documentElement.lang,'en');assert.equal(h.nodes['storage-note'].textContent,'');
for(const locale of ['en','ru']){
 h.nodes['lang-'+locale].fire();
 for(const scenario of Object.keys(data.cases)){
  h.nodes.scenario.value=scenario;h.nodes.scenario.fire('change');audit(h,locale);
  assert.deepEqual(h.nodes.cards.children.map(b=>b.children[1].textContent),api.names.map(n=>data.cases[scenario].kpis[n].value===null?api.translate(locale,'noData'):new Intl.NumberFormat(locale).format(data.cases[scenario].kpis[n].value)));
  assert.equal(h.nodes.scenario.children.find(o=>o.value===scenario).textContent,api.translate(locale,'scenario.'+scenario));
  assert.equal(h.nodes.records.children.filter(b=>b.tag==='button').length,data.cases[scenario].U.length);
  const provenance=h.nodes.provenance.textContent;assert.equal(JSON.stringify(JSON.parse(provenance).U),JSON.stringify(data.cases[scenario].U));
  for(const button of [...h.nodes.cards.children,...h.nodes.fit.children,...h.nodes['deadline-states'].children,...h.nodes.deadline.children.flatMap(t=>t.children.filter(b=>b.tag==='button'))]){button.fire();audit(h,locale);assert.ok(h.nodes.detail.textContent.includes(api.translate(locale,'commitment')));assert.ok(h.nodes.status.textContent.startsWith(api.translate(locale,'opened')));}
  h.nodes.reset.fire();for(const b of [...h.nodes.records.children].filter(b=>b.tag==='button')){b.fire();audit(h,locale);}h.nodes.reset.fire();
  h.nodes.search.value='nonexistent';h.nodes.search.fire('input');assert.equal(h.nodes.records.children[0].textContent,api.translate(locale,'empty'));audit(h,locale);
  h.nodes.reset.fire();for(const band of ['high','medium','low','unknown']){h.nodes['fit-filter'].value=band;h.nodes['fit-filter'].fire('change');assert.equal(h.nodes.records.children.filter(b=>b.tag==='button').length,api.project(api.rows(data.cases[scenario]),'',band).length);audit(h,locale);}
  h.nodes.reset.fire();for(const state of data.cases[scenario].deadline_grouping.states){h.nodes['deadline-filter'].value=state[0]+' / '+state[1];h.nodes['deadline-filter'].fire('change');assert.equal(h.nodes.records.children.filter(b=>b.tag==='button').length,state[2].length);audit(h,locale);}
  for(const sort of ['identity','identity-desc','fit','deadline']){h.nodes.sort.value=sort;h.nodes.sort.fire('change');audit(h,locale);}
  h.nodes.reset.fire();assert.equal(h.nodes.detail.textContent,api.translate(locale,'cleared'));
 }
 h.nodes.scenario.value='invalid';h.nodes.scenario.fire('change');assert.equal(h.nodes.status.textContent,api.translate(locale,'error'));assert.equal(h.nodes.cards.children.length,0);assert.equal(h.nodes.provenance.textContent,'');h.nodes.search.fire('input');h.nodes.scenario.value='normal';h.nodes.retry.fire();audit(h,locale);
}
h.nodes.search.value='high';h.nodes['fit-filter'].value='high';h.nodes.sort.value='identity-desc';h.nodes.search.fire('input');h.nodes.cards.children[2].fire();h.nodes.search.value='high';h.nodes['fit-filter'].value='high';h.nodes.sort.value='identity-desc';h.nodes['lang-en'].fire();assert.equal(h.nodes.scenario.value,'normal');assert.equal(h.nodes.search.value,'high');assert.equal(h.nodes['fit-filter'].value,'high');assert.equal(h.nodes.sort.value,'identity-desc');assert.equal(h.nodes.records.children.filter(b=>b.tag==='button').length,1);assert.equal(h.nodes.detail.textContent,api.translate('en','selectEvidence'));audit(h,'en');
assert.equal(h.memory.get('valyqon.preview.language'),'en');audit(harness('ru'),'ru');
const blocked=harness(null,true);assert.equal(blocked.document.documentElement.lang,'en');assert.equal(blocked.nodes['storage-note'].textContent,api.translate('en','storageDenied'));blocked.nodes['lang-ru'].fire();audit(blocked,'ru');assert.equal(blocked.nodes['storage-note'].textContent,api.translate('ru','storageDenied'));
for(const locale of ['en','ru'])for(const node of h.all.filter(e=>e.getAttribute('data-i18n'))){api.translate(locale,node.getAttribute('data-i18n'));}
assert.equal(JSON.stringify(data),snapshot,'Locale and filters must never mutate fixture data');assert.deepEqual(api.names.map(n=>data.cases.normal.kpis[n].value),[4,2,2,1,1,1]);
assert.doesNotMatch(source,/innerHTML|fetch\(|XMLHttpRequest/);
console.log('P39H I18N PASS: both locales × seven scenarios; static/dynamic/ARIA/titles, charts, inspector, reasons, search/filter/sort/drilldown, error/empty, persistence/denial/default, missing keys, immutable fixture');