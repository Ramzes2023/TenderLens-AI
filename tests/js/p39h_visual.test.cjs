'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),crypto=require('node:crypto');
const api=require('../../scripts/p39e_preview/view.js');
const html=fs.readFileSync(process.argv[2],'utf8');
const css=html.match(/<style>([\s\S]*?)<\/style>/)[1],js=html.match(/<script>([\s\S]*?)<\/script>/)[1];
for(const asset of [css,js])assert.ok(html.includes("'sha256-"+crypto.createHash('sha256').update(asset).digest('base64')+"'"));
assert.equal(css,fs.readFileSync('scripts/p39e_preview/style.css','utf8').replace(/\r\n/g,'\n'));
assert.equal(js,fs.readFileSync('scripts/p39e_preview/view.js','utf8').replace(/\r\n/g,'\n'));
for(const marker of ['color-scheme:dark','background:#07101f','radial-gradient','data-metric','investigation','deadline-glyph','@media(max-width:1200px)','@media(max-width:850px)','@media(max-width:480px)','prefers-reduced-motion','transition:none!important',':focus-visible','overflow-x:auto'])assert.ok(html.includes(marker),marker);
assert.doesNotMatch(html,/color-scheme:light|background:\s*(?:white|#fff(?:fff)?[;}])|innerHTML|fetch\(|XMLHttpRequest|<script src=|<link /);
assert.ok(html.includes("connect-src 'none'"));
for(const key of ['coverageGraphic','keyboardEvidence','bucketGraphic',...api.names.map(n=>'context.'+n)])for(const locale of ['en','ru'])assert.ok(api.translate(locale,key));
const data=JSON.parse(html.match(/<script id="fixture" type="application\/json">([\s\S]*?)<\/script>/)[1]);
assert.deepEqual([...new Set(data.cases.normal.deadline_grouping.buckets.map(b=>b[0]))].sort(),['date_only','instant'],'Normal fixture must exercise both typed tracks; missing timezone support is not acceptance');
for(const r of Object.values(data.cases)){
 const ms=api.model(r),known=ms.find(m=>m.name==='Fit high').d,unknown=ms.find(m=>m.name==='Fit unknown');
 assert.equal(known+unknown.n,r.U.length);assert.equal(unknown.d,r.U.length);
 assert.ok(Number.isFinite(api.width(known,r.U.length)));
 for(const a of api.arcs(ms)){assert.ok(Number.isFinite(a.length)&&Number.isFinite(a.offset));assert.ok(a.length>=0&&a.offset>=0&&a.length+a.offset<=100+1e-10);}
 for(const [type,day,ids]of r.deadline_grouping.buckets){
  const m=ms.find(m=>m.kind==='deadline'&&m.type===type&&m.day===day);
  assert.deepEqual(m.ids,ids);assert.equal(m.n,ids.length);
 }
}
assert.deepEqual(api.names.map(n=>data.cases.normal.kpis[n].value),[4,2,2,1,1,1]);
// Executes generated DOM in both directions, all scenarios, titles and keyboard-native buttons.
require('./p39h_i18n.test.cjs');
console.log('P39H VISUAL PASS: dark instruments, responsive contracts, CSP bytes, bilingual graphics, exact denominators and typed identities');
