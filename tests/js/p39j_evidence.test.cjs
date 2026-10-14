'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
assert.ok(process.argv[2],'Generated HTML path required');
const html=fs.readFileSync(process.argv[2],'utf8');
const js=html.match(/<script>([\s\S]*?)<\/script>/)[1];
assert.equal(js,fs.readFileSync('scripts/p39e_preview/view.js','utf8').replace(/\r\n/g,'\n'),'Real builder must rebundle current assets');
const context={module:{exports:{}}};vm.runInNewContext(js,context);const api=context.module.exports;
const data=JSON.parse(html.match(/<script id="fixture" type="application\/json">([\s\S]*?)<\/script>/)[1]);
const plain=x=>JSON.parse(JSON.stringify(x)),clone=plain;
assert.deepEqual(Object.keys(data.cases).sort(),['normal','empty','unknown','legacy','foreign','future','filtered'].sort());
assert.deepEqual(plain(api.names.map(n=>data.cases.normal.kpis[n].value)),[4,2,2,1,1,1]);
assert.deepEqual(data.cases.normal.U,[['ted','calendar'],['ted','high'],['ted','unknown'],['ted','zero']]);
for(const [scenario,r] of Object.entries(data.cases)){
 const before=JSON.stringify(r),p=plain(api.analyticsEvidence(r)),n=r.U.length;
 assert.equal(JSON.stringify(r),before);assert.deepEqual(p.population.identities,r.U);assert.equal(p.population.denominator,n);
 assert.deepEqual(p.provenance,{population_id:r.population_id,scope:r.scope,as_of:r.context.as_of,timezone:r.context.timezone,coverage:r.coverage,sample_window:r.sample_window});
 const sourceNames=[...new Set(r.U.map(i=>i[0]))].sort();assert.deepEqual(p.sources.groups.map(g=>g.label),sourceNames);
 for(const g of p.sources.groups){assert.deepEqual(g.identities,r.U.filter(i=>i[0]===g.label));assert.equal(g.denominator,n);}
 for(const k of ['countries','categories']){assert.equal(p[k].status,'unavailable');assert.equal(p[k].groups,null);assert.equal(p[k].numerator,null);}
 const eventDays=[...new Set(r.selected_events.map(e=>new Date(e[1]).toISOString().slice(0,10)))].sort();
 assert.deepEqual(p.activity.groups.map(g=>g.label),eventDays);
 for(const g of p.activity.groups){assert.deepEqual(g.identities,r.selected_events.filter(e=>new Date(e[1]).toISOString().slice(0,10)===g.label).map(e=>e[0]));assert.equal(g.denominator,r.selected_events.length);assert.equal(g.unit,'selected_history_event');}
 assert.deepEqual(p.deadlines.groups.map(g=>[g.type,g.day,g.identities]),r.deadline_grouping.buckets);
 assert.deepEqual(p.deadlineStates.groups.map(g=>[g.type,g.label,g.identities]),r.deadline_grouping.states);
 for(const g of p.fit.groups.slice(0,3)){assert.deepEqual(g.identities,r.fit_bands[g.label].identities);assert.equal(g.denominator,r.fit_bands[g.label].denominator);}
 assert.deepEqual(p.fit.groups[3].identities,Object.values(r.unknown_fit).flat());assert.equal(p.fit.groups[3].denominator,n);
 assert.equal(p.coverage.groups.reduce((sum,g)=>sum+g.numerator,0),n);
 for(const panel of Object.values(p))if(panel&&Array.isArray(panel.groups))for(const g of panel.groups){assert.ok(Number.isSafeInteger(g.numerator)&&Number.isSafeInteger(g.denominator));assert.equal(g.numerator,g.identities.length);assert.ok(g.numerator<=g.denominator);}
 for(const bad of [NaN,Infinity,-1,Number.MAX_SAFE_INTEGER+1]){const x=clone(r);x.kpis.Discovered.denominator=bad;assert.throws(()=>api.analyticsEvidence(x));}
 const x=clone(r);x.U.push(['hostile','identity']);assert.throws(()=>api.analyticsEvidence(x));
 assert.ok(!JSON.stringify(p).includes('supplier_wins'));assert.equal(p.trend,undefined);
 console.log('P4A evidence scenario:',scenario);
}
const mutate=f=>{const r=clone(data.cases.normal);f(r);assert.throws(()=>api.analyticsEvidence(r));};
mutate(r=>r.deadline_grouping.buckets.push(clone(r.deadline_grouping.buckets[0])));
mutate(r=>r.deadline_grouping.buckets[0][1]='2026-02-30');
mutate(r=>r.selected_events.push(clone(r.selected_events[0])));
mutate(r=>r.selected_events[0][1]='2026-03-26');
mutate(r=>r.observed_events=Infinity);
mutate(r=>r.deadline_grouping.states[0][2].push(['untrusted','id']));
const hostile=clone(data.cases.normal),payload='<img src=x onerror=alert(1)>';
// Allowlisted strings remain inert data; no HTML/JS execution path is introduced.
hostile.scope=[7,33];hostile.context.timezone=payload;
assert.equal(api.analyticsEvidence(hostile).provenance.timezone,payload);
const detached=api.analyticsEvidence(data.cases.normal);detached.population.identities[0][0]='changed';
assert.equal(data.cases.normal.U[0][0],'ted');
assert.ok(html.includes("connect-src 'none'"));
assert.doesNotMatch(js,/innerHTML|outerHTML|insertAdjacentHTML|document\.write|fetch\(|XMLHttpRequest/);
assert.ok(html.includes("'sha256-"+crypto.createHash('sha256').update(js).digest('base64')+"'"));
// Existing generated-DOM suite checks safe textContent rendering, EN/RU and every scenario.
require('./p39h_i18n.test.cjs');
console.log('P4A EVIDENCE PASS: frozen allowlist, exact groups, missing semantics, immutable data');
