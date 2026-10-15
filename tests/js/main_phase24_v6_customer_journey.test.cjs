'use strict';
// OFFLINE_FIXTURE: shipped functions and handlers on a minimal DOM, NOT Chromium/auth.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const script = path.join(__dirname, '../../app/api/static/discovery.js');
const ui = require(script);
const item = {source:'ted', external_id:'240003-2099', title:'OFFLINE_FIXTURE cables',
 url:'https://ted.europa.eu/en/notice/240003-2099/html', currency:null, initial_price:null,
 deadline:null, full_ai_analyzed:false, metadata_analysis:{required_documents:[]},
 preliminary_scoring:{fit_score:null, completeness_percent:null,
  criteria:[{code:'category',label:'Category',status:'matched',explanation:'Cable keyword evidence'},
   {code:'budget',label:'Budget',status:'not_scored',explanation:'Amount unavailable'}],
  missing_information:['Deadline unavailable','Documents unverified'], stop_factors:['Currency restriction requires review']}};
const filters = {keyword:'',source:'',buyer:'',currency:'',value:'',fit:'',deadline:'',published:''};
assert.equal(ui.matches(item, filters),true);
for (const filter of [{currency:'EUR'}, {fit:'1'}, {deadline:'2099-01-01'}, {source:'uk_fts'}, {keyword:'accounting'}]) {
 assert.equal(ui.matches(item,{...filters,...filter}),false);
}
assert.equal(ui.matches(item,{...filters,keyword:'cables'}),true);
const html = ui.card(item,0,null);
for (const text of ['Metadata preview','Not enough data','Amount unavailable','Documents unverified','Currency restriction']) {
 assert.ok(html.includes(text),text);
}
assert.match(ui.detail(item), /Deadline unavailable/);
for (const url of ['javascript:alert(1)', 'http://ted.europa.eu/x', 'https://ted.europa.eu.evil.test/x',
 'https://user:pass@ted.europa.eu/x', 'https://ted.europa.eu:8443/x', 'https://sam.gov/x']) {
 assert.equal(ui.officialUrl({...item,url}),null);
}
assert.match(html,/rel="noopener noreferrer"/);
assert.doesNotMatch(ui.card({...item,title:'<script>OFFLINE_FIXTURE</script>'},0),/<script>/);
assert.match(ui.sourceMessage({items:[],total_failure:true}),/could not be reached/);
assert.match(ui.sourceMessage({items:[],total_failure:false}),/No tenders found/);
// Executes actual explicit Find, detail, Save, filters, late JSON/Save and role-switch handlers.
require('./main_customer_discovery_flow.test.cjs')(fs.readFileSync(script,'utf8'),assert)
 .then(()=>console.log('V6_DOM_SCRIPT=PASS; EVIDENCE=OFFLINE_FIXTURE; BROWSER_AUTHENTICATED=NOT_VERIFIED'))
 .catch(error=>{console.error(error);process.exitCode=1;});
