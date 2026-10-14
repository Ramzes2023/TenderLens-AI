'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const source = read('app/api/static/locale.js');
const shell = read('app/api/saas_shell.py');
const premium = read('app/api/static/premium.js');
class Node {
  constructor(text = '') { this.textContent = text; this.attributes = {}; this.dataset = {}; this.lang = ''; this.listeners = {}; }
  setAttribute(key,value) { this.attributes[key] = value; }
  getAttribute(key) { return this.attributes[key]; }
  addEventListener(key,fn) { this.listeners[key] = fn; }
  querySelector() { return this.span; }
  querySelectorAll() { return this.children || []; }
  set innerHTML(_) { throw Error('HTML injection'); }
}
function boot(saved, blocked = false, missingTranslation = false, noStorage = false) {
  const ids = Object.fromEntries(['shellLocale','shellLocaleLabel','shellLocaleScope','pageHeading','sideCompany','activeCompanyLabel','email','openCommands'].map(id => [id,new Node()]));
  ids.email.textContent = 'Loading account...';
  ids.activeCompanyLabel.textContent = 'No active company';
  ids.openCommands.firstChild = { nodeType:3, nodeValue:'Go to workspace... ' };
  const nav = new Node(); nav.dataset.nav = 'monitoring'; nav.span = new Node('Monitoring');
  const page = new Node('Scan for new matches');
  const label = new Node();
  const mapping = {'[data-nav]':[nav],'.nav-group-label':[], '[data-page],#orgControl,#futurePage,#appNotice,#globalSupportPanel,#globalSupportLauncher':[page], '#shellLocaleLabel':[ids.shellLocaleLabel], '#shellLocaleScope':[ids.shellLocaleScope], '#shellLocale':[ids.shellLocale], '#navToggle':[label]};
  const bindingSource = source.match(/const bindings = \[([\s\S]*?)\n  \];/)[1];
  const bound = [...bindingSource.matchAll(/\['([^']+)','([^']+)'(?:,'([^']+)')?\]/g)].map(([,selector,key,attribute])=>{
    const node = mapping[selector]?.[0] || new Node();
    mapping[selector] = [node];
    return {node,key,attribute};
  });
  mapping['.nav-group-label'] = Array.from({length:4},()=>new Node());
  const listeners = {}, events = [], writes = [];
  let observer;
  const state = {activeCompanyId:null, activeCompanyName:'No active company', uiEpoch:12, orgId:27};
  const context = {state, document:{documentElement:{lang:'en'},body:{},getElementById:id=>ids[id],querySelectorAll:selector=>mapping[selector]||[],querySelector:()=>nav},
    localStorage:{getItem(){if(blocked)throw Error('disabled');return saved;},setItem(...args){if(blocked)throw Error('disabled');writes.push(args);}},
    Event:class {constructor(type){this.type=type;}}, MutationObserver:class {constructor(fn){observer=fn;} observe(){}},
    fetch(){throw Error('Unexpected network request');}, window:{addEventListener:(key,fn)=>listeners[key]=fn,dispatchEvent:event=>events.push(event.type)}};
  if (noStorage) delete context.localStorage;
  vm.runInNewContext(missingTranslation ? source.replace('ru: pair[1]', 'ru: undefined') : source,context);
  return {api:context.window.MainLocale,context,ids,nav,page,label,state,events,writes,listeners,bound,mapping,mutate:()=>observer()};
}
function assertBindings(instance, language) {
  for (const {node,key,attribute} of instance.bound) {
    assert.equal(attribute ? node.getAttribute(attribute) : node.textContent,instance.api.dictionary[key][language],key);
  }
  for (const [index,key] of ['Workspace','Intelligence','Organization','System'].entries()) {
    assert.equal(instance.mapping['.nav-group-label'][index].textContent,instance.api.dictionary[key][language]);
  }
}
const x = boot();
assertBindings(x,'en');
for (const [key, value] of Object.entries(x.api.dictionary)) {
  assert.equal(typeof value.en,'string',key); assert.ok(value.en.length,key);
  assert.equal(typeof value.ru,'string',key); assert.ok(value.ru.length,key);
}
const navKeys = [...shell.matchAll(/"(Overview|Discover|Search History|Recommended|Saved|Monitoring|Source Health|AI Analysis|Documents|Companies|Notifications|Team|Billing|Support|Settings)"/g)].map(m=>m[1].toLowerCase().replaceAll(' ','-'));
for (const key of navKeys) assert.ok(x.api.dictionary[key],key);
// ['en','ru'] is a locale allowlist, not a DOM translation binding.
const bindings = source.match(/const bindings = \[([\s\S]*?)\n  \];/);
assert.ok(bindings, 'DOM translation bindings must exist');
const bindingKeys = [...bindings[1].matchAll(/\['[^']+','([^']+)'(?:,'[^']+')?\]/g)].map(match=>match[1]);
assert.ok(bindingKeys.length >= 20, 'Check the complete shell binding list');
for (const key of bindingKeys) assert.ok(x.api.dictionary[key],key);
assert.equal(x.context.document.documentElement.lang,'en');
assert.equal(x.api.setLocale('ru'),true);
assertBindings(x,'ru');
assert.equal(x.nav.span.textContent,'Мониторинг');
assert.equal(x.ids.pageHeading.textContent,'Мониторинг');
assert.equal(x.context.document.documentElement.lang,'ru');
assert.equal(x.ids.shellLocale.getAttribute('aria-label'),'Язык');
assert.equal(x.ids.sideCompany.textContent,'Нет активной компании');
assert.equal(x.ids.email.textContent,'Загрузка аккаунта…');
assert.equal(x.page.lang,'ru'); assert.equal(x.page.textContent,'Scan for new matches');
assert.equal(x.ids.activeCompanyLabel.textContent,'Нет активной компании');
assert.deepEqual(x.state,{activeCompanyId:null,activeCompanyName:'No active company',uiEpoch:12,orgId:27});
assert.deepEqual(x.events,['shell-locale-change']);
assert.equal(x.writes[0][0],'valyqon.shell.locale');
assert.equal(x.writes[0][1],'ru');
assert.equal(x.ids.shellLocale.value,'ru');
assert.match(x.ids.shellLocaleScope.textContent,/Названия официальных источников/);
assert.equal(x.api.setLocale('xx'),false); assert.equal(x.api.locale,'ru');
assert.equal(x.api.t('missing','English fallback'),'English fallback');
for (const [name,expected] of [['Loading workspace...','Загрузка рабочей области…'],['','Выберите компанию']]) {
  x.state.activeCompanyName=name; x.listeners['workspace-context'](); assert.equal(x.ids.sideCompany.textContent,expected);
}
const fallback = boot('ru',false,true); assert.equal(fallback.api.t('monitoring'),'Monitoring');
x.state.activeCompanyName = '<img src=x onerror=alert(1)>'; x.state.activeCompanyId = 4;
x.listeners['workspace-context'](); assert.equal(x.ids.sideCompany.textContent,x.state.activeCompanyName);
x.nav.span.textContent = 'Monitoring'; x.mutate(); assert.equal(x.nav.span.textContent,'Мониторинг');
x.nav.dataset.nav = 'source-health'; x.listeners.hashchange();
assert.equal(x.nav.span.textContent,'Состояние источников');
assert.equal(x.ids.pageHeading.textContent,'Состояние источников');
assert.equal(x.state.uiEpoch,12); assert.equal(x.state.orgId,27); assert.equal(x.state.activeCompanyId,4);
assert.deepEqual(x.events,['shell-locale-change']);
x.nav.dataset.nav = 'monitoring';
x.ids.shellLocale.listeners.change({target:{value:'en'}});
assertBindings(x,'en');
assert.equal(x.nav.span.textContent,'Monitoring'); assert.equal(x.ids.pageHeading.textContent,'Monitoring');
const reloaded = boot('ru'); assert.equal(reloaded.api.locale,'ru'); assertBindings(reloaded,'ru');
assert.equal(reloaded.context.document.documentElement.lang,'ru'); assert.equal(reloaded.nav.span.textContent,'Мониторинг');
assert.deepEqual(reloaded.events,[]); assert.deepEqual(reloaded.writes,[]);
assert.equal(boot('invalid').api.locale,'en');
const disabled = boot('ru',true); assert.equal(disabled.api.locale,'en'); assert.doesNotThrow(()=>disabled.api.setLocale('ru'));
assertBindings(disabled,'ru');
const absent = boot(undefined,false,false,true); assert.equal(absent.api.locale,'en');
assert.equal(absent.api.setLocale('ru'),true); assertBindings(absent,'ru');
assert.match(shell,/<select id="shellLocale" aria-describedby="shellLocaleScope">/);
assert.match(shell,/<option value="en">English<\/option>/);
assert.match(shell,/<option value="ru">Русский<\/option>/);
assert.ok(shell.indexOf('/assets/locale.js') > shell.indexOf('/assets/source_health.js'));
assert.match(premium,/MainLocale\?\.t\('go'\)/); assert.match(premium,/MainLocale\?\.t\('noPages'\)/);
assert.match(premium,/shell-locale-change/);
assert.match(premium,/e\.ctrlKey\|\|e\.metaKey/); assert.match(premium,/e\.preventDefault\(\)/);
// Execute the real command menu, including its keyboard entry and locale rerender.
const menuNodes = Object.fromEntries(['commandPalette','commandQuery','commandResults','openCommands','closeCommands'].map(id=>[id,new Node()]));
menuNodes.commandQuery.value = '';
menuNodes.commandQuery.focus = () => { menuNodes.commandQuery.focused = true; };
menuNodes.commandPalette.showModal = () => { menuNodes.commandPalette.open = true; };
menuNodes.commandPalette.close = () => { menuNodes.commandPalette.open = false; };
menuNodes.commandResults.replaceChildren = () => { menuNodes.commandResults.children = []; menuNodes.commandResults.textContent = ''; };
menuNodes.commandResults.append = node => menuNodes.commandResults.children.push(node);
const menuEvents = {};
const menuLink = {textContent:'Мониторинг',dataset:{nav:'monitoring'}};
const secondMenuLink = {textContent:'Состояние источников',dataset:{nav:'source-health'}};
const menuLocation = {hash:''};
const menuContext = {state:{},location:menuLocation,document:{getElementById:id=>menuNodes[id],querySelectorAll:()=>[menuLink,secondMenuLink],createElement:()=>new Node()},window:{MainLocale:x.api,addEventListener:(key,fn)=>menuEvents[key]=fn}};
for (const node of Object.values(menuNodes)) node.focus = () => { node.focused = true; menuContext.document.activeElement = node; };
menuContext.document.createElement = () => { const node=new Node(); node.focus=()=>{menuContext.document.activeElement=node;}; return node; };
vm.runInNewContext(premium.split('/* VALYQON OVERVIEW V2 */')[0],menuContext);
x.api.setLocale('ru');
let prevented = false;
menuEvents.keydown({ctrlKey:true,key:'k',preventDefault(){prevented=true;}});
assert.equal(prevented,true); assert.equal(menuNodes.commandPalette.open,true); assert.equal(menuNodes.commandQuery.focused,true);
assert.equal(menuNodes.commandResults.children[0].textContent,'Перейти: Мониторинг');
menuNodes.commandPalette.listeners.keydown({key:'ArrowDown',preventDefault(){}});
assert.equal(menuContext.document.activeElement,menuNodes.commandResults.children[0]);
menuNodes.commandPalette.listeners.keydown({key:'ArrowUp',preventDefault(){}});
assert.equal(menuContext.document.activeElement,menuNodes.commandResults.children[1]);
menuNodes.commandQuery.focus(); menuNodes.commandPalette.listeners.keydown({key:'ArrowUp',preventDefault(){}});
assert.equal(menuContext.document.activeElement,menuNodes.commandResults.children[1]);
menuNodes.commandResults.children[0].onclick();
assert.equal(menuLocation.hash,'monitoring'); assert.equal(menuNodes.commandPalette.open,false);
menuEvents.keydown({metaKey:true,key:'K',preventDefault(){}});
assert.equal(menuNodes.commandPalette.open,true);
menuNodes.commandPalette.listeners.keydown({key:'Escape',preventDefault(){}});
assert.equal(menuNodes.commandPalette.open,false); assert.equal(menuContext.document.activeElement,menuNodes.openCommands);
menuNodes.openCommands.onclick();
menuNodes.commandQuery.value = 'does not exist'; menuNodes.commandQuery.listeners.input();
assert.equal(menuNodes.commandResults.textContent,'Подходящие разделы не найдены.');
x.api.setLocale('en'); menuEvents['shell-locale-change']();
assert.equal(menuNodes.commandResults.textContent,'No matching pages.');
menuLink.textContent='Monitoring'; menuNodes.commandQuery.value='mon'; menuNodes.commandQuery.listeners.input();
assert.equal(menuNodes.commandResults.children[0].textContent,'Go to Monitoring');
menuNodes.closeCommands.onclick(); assert.equal(menuNodes.commandPalette.open,false);
assert.match(read('app/api/static/shell.js'),/e\.key==='Escape'/);
// Execute the existing sidebar navigation, rather than only inspecting its source.
function classList() {
  const values = new Set();
  return {add:value=>values.add(value),remove:value=>values.delete(value),contains:value=>values.has(value),
    toggle(value,force){const enabled=force===undefined?!values.has(value):force;if(enabled)values.add(value);else values.delete(value);return enabled;}};
}
const sidebarIds = Object.fromEntries(['companies','companyCreator','tenders','monitoringCenter','organizationCard','telegramCard','organizationSelect','orgControl','pageHeading','futurePage','futureTitle','futureText','futureNext','appNav','navToggle'].map(id=>[id,new Node()]));
const sidebarLinks = ['overview','monitoring','source-health'].map(key=>{const node=new Node(x.api.dictionary[key].ru);node.dataset.nav=key;return node;});
const sidebarPages = sidebarLinks.map(link=>{const node=new Node();node.dataset.page=link.dataset.nav;return node;});
let focused;
for (const node of [...Object.values(sidebarIds),...sidebarLinks]) {
  node.classList=classList(); node.closest=()=>node; node.focus=()=>{focused=node;}; node.removeAttribute=key=>delete node.attributes[key];
}
sidebarIds.organizationSelect.parentElement=new Node();
sidebarIds.orgControl.append=node=>{sidebarIds.orgControl.child=node;};
sidebarIds.appNav.querySelector=()=>sidebarLinks.find(node=>node.getAttribute('aria-current')==='page');
const sidebarEvents={}, sidebarPublished=[];
const sidebarLocation={hash:'#monitoring'};
const workspaceContext=new Node();
const sidebarDocument={body:{classList:classList()},getElementById:id=>sidebarIds[id],
  querySelector(selector){if(selector==='.workspace-context')return workspaceContext;return sidebarLinks.find(node=>selector===`[data-nav="${node.dataset.nav}"]`);},
  querySelectorAll:selector=>selector==='[data-nav]'?sidebarLinks:selector==='[data-page]'?sidebarPages:[]};
vm.runInNewContext(read('app/api/static/shell.js').split('/* Workspace lifecycle:')[0],{
  document:sidebarDocument,location:sidebarLocation,CSS:{escape:value=>value},Event:class{constructor(type){this.type=type;}},
  fetch(){throw Error('Navigation must not request data');},
  window:{addEventListener:(key,fn)=>sidebarEvents[key]=fn,dispatchEvent:event=>sidebarPublished.push(event.type),matchMedia:()=>({addEventListener(){}})}
});
assert.equal(sidebarIds.pageHeading.textContent,'Мониторинг');
assert.equal(sidebarLinks[1].getAttribute('aria-current'),'page');
assert.equal(sidebarPages[1].hidden,false); assert.equal(sidebarPages[0].hidden,true);
sidebarIds.navToggle.onclick(); assert.equal(sidebarIds.navToggle.getAttribute('aria-expanded'),'true'); assert.equal(focused,sidebarLinks[1]);
sidebarEvents.keydown({key:'Escape'}); assert.equal(sidebarIds.navToggle.getAttribute('aria-expanded'),'false'); assert.equal(focused,sidebarIds.navToggle);
sidebarLocation.hash='#source-health'; sidebarEvents.hashchange();
assert.equal(sidebarIds.pageHeading.textContent,'Состояние источников'); assert.equal(focused,sidebarIds.pageHeading);
assert.equal(sidebarPages[2].hidden,false); assert.equal(sidebarPages[1].hidden,true);
assert.deepEqual(sidebarPublished,['workspace-context']);
sidebarLocation.hash='#invalid'; sidebarEvents.hashchange(); assert.equal(sidebarLinks[0].getAttribute('aria-current'),'page');
assert.doesNotMatch(source,/innerHTML|insertAdjacentHTML|fetch\(|workspace-context'\)\)/);
for (const file of ['discovery','history','source_health','saved','support']) assert.doesNotMatch(read(`app/api/static/${file}.js`),/MainLocale|shell-locale-change/);
console.log('main_i18n: shell coverage, switching, persistence, context, text safety, keyboard and locale-neutral services passed');
