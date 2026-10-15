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
  else stack.at(-1).own+=token;
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
 assert.ok(h.nodes.cards.children.length===6);assert.equal(h.nodes['lang-'+locale].getAttribute('aria-pressed'),'true');
 assert.equal(h.nodes.ring.children[0].getAttribute('aria-label'),api.translate(locale,'ringAria'));
}
let activeDocument;
Element.prototype.focus=function(){this.focused=true;activeDocument.activeElement=this;};
Element.prototype.scrollIntoView=function(){this.scrolled=true;};
for(const locale of ['en','ru']){
 const h=harness(locale),n=h.nodes;activeDocument=h.document;
 for(const scenario of Object.keys(data.cases)){
  n.scenario.value=scenario;n.scenario.fire('change');audit(h,locale);
  const population=data.cases[scenario].U.length;
  const buttons=()=>n.records.children.filter(b=>b.tag==='button');
  assert.equal(buttons().length,population);
  for(const [control,event]of [['search','input'],['fit-filter','change'],['deadline-filter','change'],['sort','change']])assert.ok(n[control].listeners[event]);
  n.search.value='ted';n.search.fire('input');
  const before=buttons().map(b=>b.textContent);
  if(buttons().length){
   buttons()[0].focus();buttons()[0].fire();
   assert.equal(h.document.activeElement,buttons()[0],'Row replacement retains keyboard focus');
   assert.ok(!n.detail.textContent.includes(api.translate(locale,'sourceDrill')),'Record is not a source/country group');
   assert.equal(n.search.value,'ted','Row inspection preserves search');
   assert.deepEqual(buttons().map(b=>b.textContent),before,'Row inspection preserves visible population');
   assert.equal(buttons()[0].getAttribute('aria-pressed'),'true');
   n['back-records'].fire();assert.ok(buttons()[0].focused);assert.ok(n.explorer.scrolled);
  }
  n.reset.fire();
  for(const b of [...n.cards.children,...n.fit.children,...n['deadline-states'].children,...n.deadline.children.flatMap(x=>x.children.filter(b=>b.tag==='button'))]){
   b.fire();const ms=api.model(data.cases[scenario]);const m=ms.find(m=>b.getAttribute('aria-label')=== (m.kind==='kpi'?api.translate(locale,'kpi.'+m.name):m.kind==='fit'?api.translate(locale,'fit.'+m.name.split(' ')[1]):m.kind==='state'?m.name.split(' / ').map(x=>api.translate(locale,x)).join(' / '):m.kind==='deadline'?api.translate(locale,m.type)+' · '+new Intl.DateTimeFormat(locale,{timeZone:'UTC',year:'numeric',month:'short',day:'numeric'}).format(new Date(m.day+'T00:00:00Z')):'')+' · '+(m.n+' / '+m.d)+' · '+api.translate(locale,m.kind==='fit'?(m.name==='Fit unknown'?'whole':'known'):m.kind==='kpi'?({'unique_tender_identity':'tenders','distinct_successfully_reached_source':'sources','distinct_supported_country':'countries'}[m.unit]||'units'):'whole'));assert.ok(m,'Every evidence button resolves to an exact model group');if(m){const ids=m.ids.map(i=>Array.isArray(i)?i.join(' / '):i).join(', ')||'—';assert.ok(n.detail.textContent.includes(ids),'Inspector shows exact identities');if(m.kind!=='kpi'||m.unit==='unique_tender_identity')assert.equal(buttons().length,m.ids.length);}assert.equal(b.getAttribute('aria-pressed'),'true');assert.equal(b.getAttribute('aria-controls'),'records detail');assert.equal(n['clear-group'].disabled,false);
   assert.match(n.subset.textContent,new RegExp(api.translate(locale,'frozenPopulation')));
   n['clear-group'].fire();assert.equal(buttons().length,population);assert.equal(b.getAttribute('aria-pressed'),'false');
  }
  n.search.value='absent';n.search.fire('input');assert.equal(buttons().length,0);
  n['lang-'+(locale==='en'?'ru':'en')].fire();assert.equal(buttons().length,0);assert.equal(n.search.value,'absent');n['lang-'+locale].fire();
  n.scenario.value=scenario;n.scenario.fire('change');
  assert.equal(n.search.value,'');assert.equal(n['fit-filter'].value,'');assert.equal(n['deadline-filter'].value,'');assert.equal(n.sort.value,'identity');
  assert.equal(buttons().length,population);assert.equal(n.detail.textContent,api.translate(locale,'selectEvidence'));assert.equal(n['clear-group'].disabled,true);
  assert.equal(JSON.parse(n.provenance.textContent).case,scenario);
 }
 for(const a of h.all.filter(e=>e.tag==='a')){assert.ok(h.nodes[a.getAttribute('href').slice(1)]);a.fire();assert.equal(a.getAttribute('aria-current'),'location');}
 n.scenario.value='invalid';n.scenario.fire('change');assert.equal(n.records.children.length,0);assert.equal(n.context.textContent,'');assert.equal(n.provenance.textContent,'');
 n.scenario.value='normal';n.retry.fire();assert.equal(buttonCount(n.records),data.cases.normal.U.length);
 // Failure after buttons were built must clear controls and disable stale actions.
 const badSource=source.replace("'context.High Fit':", "'context.broken':");
 const badDocument=h.document;
 vm.runInNewContext(badSource,{document:badDocument,localStorage:{getItem:()=>locale,setItem(){}},Intl});
 assert.equal(n['clear-group'].disabled,true);assert.equal(n.cards.children.length,0);assert.equal(n.status.textContent,api.translate(locale,'error'));

}
function buttonCount(node){return node.children.filter(b=>b.tag==='button').length;}
assert.equal(JSON.stringify(data),snapshot);
assert.ok(html.includes('aria-live="polite"'));
console.log('P39H INTERACTIONS PASS: both locales, seven scenarios, row/search preservation, native buttons, synchronized groups, return focus, anchors, errors, restoration, immutable data');