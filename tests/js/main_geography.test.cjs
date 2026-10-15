'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {spawnSync} = require('node:child_process');
const base = path.resolve(__dirname,'../..');
const read = file => fs.readFileSync(path.join(base,file),'utf8').replace(/^\uFEFF/,'');
const shell = read('app/api/saas_shell.py');
const script = read('app/api/static/geography.js');
const locale = read('app/api/static/locale.js');
const geo = JSON.parse(read('app/api/static/geography_world.geojson'));
assert.equal(geo.type,'FeatureCollection'); assert.equal(geo.features.length,176);
const franceIndex = geo.features.findIndex(f=>f.properties.name==='France');
const italyIndex = geo.features.findIndex(f=>f.properties.iso_a2==='IT');
assert.ok(franceIndex>=0 && italyIndex>=0);
assert.equal(geo.features[franceIndex].properties.iso_a2,'FR');
assert.equal(geo.features[franceIndex].properties.iso_a3,'FRA');
const names = new Set(); let points = 0;
for (const f of geo.features) {
  assert.equal(f.type,'Feature'); assert.ok(f.properties.name); assert.ok(!names.has(f.properties.name)); names.add(f.properties.name);
  for (const [key,length] of [['iso_a2',2],['iso_a3',3]]) assert.ok(f.properties[key] === null || new RegExp(`^[A-Z]{${length}}$`).test(f.properties[key]));
  assert.ok(['Polygon','MultiPolygon'].includes(f.geometry.type));
  const polygons = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates;
  assert.ok(polygons.length);
  for (const polygon of polygons) { assert.ok(polygon.length); for (const ring of polygon) {
    assert.ok(ring.length>=4); assert.deepEqual(ring[0],ring.at(-1));
    for (const [lon,lat] of ring) { assert.ok(Number.isFinite(lon)&&Number.isFinite(lat)); assert.ok(Math.abs(lon)<=180.000001&&Math.abs(lat)<=90); points++; }
  } }
}
assert.ok(points>5000);
assert.match(shell,/"Intelligence": \[\s*"Geography"/);
assert.match(shell,/id="geographyWorkspace"[^>]*data-page="geography"[^>]*hidden/);
assert.ok(shell.indexOf('/assets/geography.js') > shell.indexOf('/assets/locale.js'));
assert.match(shell,/\/assets\/geography.css/);
assert.match(read('app/api/main.py'),/app.mount\("\/assets", StaticFiles/);
assert.match(read('app/api/static/shell.js'),/document.querySelectorAll\('\[data-page\]'\).*n.hidden=n.dataset.page!==page/);
assert.doesNotMatch(script,/innerHTML|insertAdjacentHTML|localStorage|\/api\/|Math.random|tender_count|heatmap/);
assert.equal((script.match(/fetch\(/g)||[]).length,1);
class El {
  constructor(tag='div') { this.tag=tag; this.children=[]; this.dataset={}; this.attrs={}; this.listeners={}; this.value=''; this.textContent=''; }
  append(el) { this.children.push(el); el.parent=this; }
  replaceChildren(){this.children=[];}
  // Native selects cannot retain a value absent from their option list.
  set value(v){this._value=this.tag==='select' && !this.children.some(el=>el.value===String(v))?'':String(v);}
  get value(){return this._value;}
  setAttribute(k,v){this.attrs[k]=String(v);}
  getAttribute(k){return this.attrs[k];}
  addEventListener(k,fn){this.listeners[k]=fn;}
  focus(){this.focused=true;}
  querySelectorAll(selector){const all=this.children.flatMap(el=>[el,...el.querySelectorAll(selector)]);return all.filter(el=>selector==='[data-geo-text]' ? !!el.dataset.geoText : false);}
  querySelector(selector){return this.querySelectorAll('[data-geo-text]').find(el=>selector===`[data-geo-text="${el.dataset.geoText}"]`);}
  getBBox(){return {x:400,y:200,width:50,height:30};}
  getBoundingClientRect(){return {width:1000,height:500};}
  setPointerCapture(){}
  set innerHTML(_){throw Error('unsafe HTML');}
}
const all = root => [root,...root.children.flatMap(all)];
async function boot(fail=false) {
  const root=new El(), events={}, requests=[];
  const document={documentElement:{},body:{},getElementById:id=>id==='geographyWorkspace'?root:null,querySelectorAll:()=>[],querySelector:()=>null,createElement:tag=>new El(tag),createElementNS:(_,tag)=>new El(tag)};
  let release;
  const response = new Promise(resolve=>{release=resolve;});
  const context={document,Intl,Event:class{constructor(type){this.type=type;}},MutationObserver:class{observe(){}},window:{addEventListener:(key,fn)=>{(events[key] ||= []).push(fn);},dispatchEvent:event=>{for(const fn of events[event.type]||[])fn();}},fetch:(url,opts)=>{requests.push({url,opts});return response;}};
  vm.runInNewContext(locale,context); vm.runInNewContext(script,context);
  assert.match(all(root).find(el=>el.attrs.class==='geo-status').textContent,/Loading bundled geography/);
  assert.equal(all(root).find(el=>el.id==='geoSearch').disabled,true);
  assert.equal(all(root).find(el=>el.id==='geoCountry').disabled,true);
  release({ok:!fail,json:async()=>geo});
  await new Promise(resolve=>setImmediate(resolve));
  return {root,context,events,requests};
}
// Exercise MAIN navigation with geography and monitoring panels using the real shell code.
{
  const ids=Object.fromEntries(['companies','companyCreator','tenders','monitoringCenter','organizationCard','telegramCard','organizationSelect','orgControl','pageHeading','futurePage','futureTitle','futureText','futureNext','appNav','navToggle'].map(id=>[id,new El()]));
  const links=['overview','geography','monitoring'].map(key=>{const el=new El();el.dataset.nav=key;el.textContent=key;return el;});
  const panels=links.map(link=>{const el=new El();el.dataset.page=link.dataset.nav;return el;});
  const events={},location={hash:'#geography'};
  function classes(){const values=new Set();return {remove:v=>values.delete(v),contains:v=>values.has(v),toggle(v,force){const on=force===undefined?!values.has(v):force;if(on)values.add(v);else values.delete(v);return on;}};}
  for(const el of [...Object.values(ids),...links]){el.classList=classes();el.closest=()=>el;el.removeAttribute=k=>delete el.attrs[k];}
  ids.organizationSelect.parentElement=new El();ids.appNav.querySelector=()=>links.find(el=>el.attrs['aria-current']==='page');
  vm.runInNewContext(read('app/api/static/shell.js').split('/* Workspace lifecycle:')[0],{location,CSS:{escape:v=>v},Event:class{constructor(type){this.type=type;}},document:{body:{classList:classes()},getElementById:id=>ids[id],querySelector:selector=>links.find(el=>selector===`[data-nav="${el.dataset.nav}"]`),querySelectorAll:selector=>selector==='[data-nav]'?links:selector==='[data-page]'?panels:[]},window:{addEventListener:(k,fn)=>events[k]=fn,dispatchEvent(){},matchMedia:()=>({addEventListener(){}})},fetch(){throw Error('MAIN navigation must not fetch');}});
  assert.equal(panels[1].hidden,false);assert.equal(panels[2].hidden,true);assert.equal(ids.futurePage.hidden,true);assert.equal(links[1].attrs['aria-current'],'page');
  location.hash='#monitoring';events.hashchange();assert.equal(panels[1].hidden,true);assert.equal(panels[2].hidden,false);assert.equal(ids.pageHeading.textContent,'monitoring');
  location.hash='#geography';events.hashchange();assert.equal(panels[1].hidden,false);assert.equal(ids.pageHeading.textContent,'geography');
}
(async()=>{
  const x=await boot(); assert.equal(x.requests.length,1); assert.equal(x.requests[0].url,'/assets/geography_world.geojson');
  const elements=all(x.root), shapes=elements.filter(el=>el.attrs.class==='geo-country');
  assert.equal(shapes.length,176); for(const el of shapes){assert.equal(el.attrs.role,'button');assert.ok(el.attrs['aria-label']);assert.match(el.attrs.d,/^M/);assert.doesNotMatch(el.attrs.d,/NaN|Infinity/);}
  const status=elements.find(el=>el.attrs.class==='geo-status'); assert.match(status.textContent,/Tender metrics unavailable/);
  const detail=elements.find(el=>el.attrs.class==='geo-details'), title=detail.children.find(el=>el.tag==='h3');
  shapes[1].listeners.click(); assert.equal(shapes[1].attrs['aria-pressed'],'true'); assert.ok(title.textContent);
  let prevented=false; shapes[2].listeners.keydown({key:'Enter',preventDefault(){prevented=true;}});assert.ok(prevented);assert.equal(shapes[2].attrs['aria-pressed'],'true');assert.equal(shapes[1].attrs['aria-pressed'],'false');
  shapes[2].listeners.keydown({key:'ArrowRight',preventDefault(){}});assert.ok(shapes[3].focused);
  shapes[3].listeners.keydown({key:' ',preventDefault(){}}); assert.equal(shapes[3].attrs['aria-pressed'],'true');
  x.context.window.MainLocale.setLocale('ru');assert.equal(x.root.lang,'ru');assert.match(status.textContent,/Тендерные метрики недоступны/);
  for(const el of elements.filter(el=>el.dataset.geoText))assert.equal(el.textContent,x.context.window.MainLocale.t(el.dataset.geoText));
  assert.ok(elements.some(el=>el.textContent.includes('Отсутствие данных не означает')));
  const search=elements.find(el=>el.id==='geoSearch'), select=elements.find(el=>el.id==='geoCountry');
  search.value='zzzz-not-country';search.listeners.input();assert.equal(select.disabled,true);assert.match(status.textContent,/Страны не найдены/);
  assert.equal(select.value,'');
  search.value=' FR ';search.listeners.input();
  const franceOption=select.children.find(el=>el.value===String(franceIndex));
  assert.ok(franceOption);assert.equal(franceOption.textContent,'Франция');assert.equal(select.disabled,false);
  select.value=franceOption.value;select.listeners.change();assert.equal(title.textContent,'Франция');
  assert.equal(select.value,String(franceIndex));assert.equal(shapes[franceIndex].attrs['aria-pressed'],'true');
  assert.equal(shapes[franceIndex].attrs['aria-label'],'Франция');assert.equal(shapes[franceIndex].attrs.tabindex,'0');
  assert.match(detail.children.find(el=>el.attrs.class==='geo-codes').textContent,/FR \/ FRA/);
  assert.equal(title.attrs['aria-live'],'polite');assert.equal(detail.attrs['aria-labelledby'],title.id);
  x.context.window.MainLocale.setLocale('en');assert.equal(title.textContent,'France');assert.equal(x.requests.length,1);
  assert.equal(select.value,String(franceIndex));assert.equal(shapes[franceIndex].attrs['aria-label'],'France');
  assert.equal(select.children.find(el=>el.value===String(franceIndex)).textContent,'France');
  search.value='France';search.listeners.input();assert.ok(select.children.some(el=>el.value===String(franceIndex)));
  search.value='ITA';search.listeners.input();assert.equal(select.value,'');assert.equal(title.textContent,'France');
  select.value=String(italyIndex);select.listeners.change();assert.equal(title.textContent,'Italy');
  assert.equal(shapes[italyIndex].attrs['aria-pressed'],'true');assert.equal(shapes[franceIndex].attrs['aria-pressed'],'false');
  shapes[franceIndex].listeners.click();assert.equal(search.value,'');assert.equal(select.value,String(franceIndex));assert.equal(title.textContent,'France');
  shapes[italyIndex].listeners.keydown({key:'Enter',preventDefault(){}});assert.equal(title.textContent,'Italy');assert.equal(select.value,String(italyIndex));
  x.context.window.MainLocale.setLocale('ru');assert.equal(title.textContent,'Италия');assert.equal(shapes[italyIndex].attrs['aria-label'],'Италия');
  search.value='Франция';search.listeners.input();assert.ok(select.children.some(el=>el.value===String(franceIndex)));
  select.value=String(franceIndex);select.listeners.change();assert.equal(title.textContent,'Франция');
  shapes[franceIndex].listeners.keydown({key:' ',preventDefault(){}});assert.equal(shapes[franceIndex].attrs['aria-pressed'],'true');
  x.context.window.MainLocale.setLocale('en');
  assert.equal(title.textContent,'France');assert.equal(select.value,''); // Russian query still filters the English list.
  search.value='';search.listeners.input();assert.equal(select.value,String(franceIndex));
  select.value='';select.listeners.change();assert.equal(title.textContent,x.context.window.MainLocale.t('geoNoSelection'));
  assert.ok(shapes.every(el=>el.attrs['aria-pressed']==='false'));
  assert.equal(shapes[0].attrs.tabindex,'0');
  assert.equal(elements.find(el=>el.dataset.geoText==='geoFit').disabled,true);
  assert.equal(detail.children.find(el=>el.dataset.geoText==='geoUnavailable').textContent,x.context.window.MainLocale.t('geoUnavailable'));
  assert.match(detail.children.find(el=>el.dataset.geoText==='geoUnavailable').textContent,/Missing data does not mean zero tenders/);
  assert.match(elements.find(el=>el.dataset.geoText==='geoIntro').textContent,/outlines do not indicate tender coverage/);
  assert.match(elements.find(el=>el.dataset.geoText==='geoRankingCopy').textContent,/counts and rankings are unavailable/);
  assert.equal(x.requests.length,1);
  const map=elements.find(el=>el.tag==='svg');for(let i=0;i<50;i++)map.listeners.keydown({target:map,key:'+',preventDefault(){}});assert.equal(map.attrs.viewBox.split(' ')[2],'125');
  for(let i=0;i<50;i++)map.listeners.keydown({target:map,key:'-',preventDefault(){}});assert.equal(map.attrs.viewBox,'0 0 1000 500');
  const y=await boot(true);assert.match(all(y.root).find(el=>el.attrs.class==='geo-status').textContent,/could not be loaded/);y.context.window.MainLocale.setLocale('ru');assert.match(all(y.root).find(el=>el.attrs.class==='geo-status').textContent,/Не удалось/);
  const prior=spawnSync(process.execPath,[path.join(base,'tests/js/main_i18n.test.cjs')],{encoding:'utf8',timeout:15000}); assert.equal(prior.status,0,prior.stdout+prior.stderr);
  console.log('main_geography: MAIN wiring, full real outlines, pointer/keyboard selection, EN/RU, search, zoom bounds, error/no-data and existing shell regression passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
