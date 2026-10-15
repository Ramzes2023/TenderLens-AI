'use strict';
// LOCAL SYNTHETIC TEST. Run shipped handlers against the existing minimal DOM harness.
// This is browser-script behavior evidence, not an authenticated real-browser session.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const file = path.join(__dirname, '../../app/api/static/discovery.js');
const ui = require(file);
const item = {source:'ted',external_id:'100001-2026',title:'SYNTHETIC cables <script>alert(1)</script>',
 url:'https://ted.europa.eu/en/notice/100001-2026/html',full_ai_analyzed:false,
 metadata_analysis:{required_documents:[]},
 preliminary_scoring:{fit_score:80,completeness_percent:30,criteria:[],
 missing_information:['Price missing','Deadline missing'],stop_factors:['Currency needs review']}};
assert.match(ui.card(item,0), /Preliminary Match/);
assert.doesNotMatch(ui.card(item,0), /<script>/);
assert.match(ui.detail(item), /Price missing/);
assert.match(ui.detail(item), /Deadline missing/);
assert.match(ui.detail(item), /Currency needs review/);
for (const url of ['javascript:alert(1)','http://ted.europa.eu/x',
 'https://ted.europa.eu.evil.example/x','https://user@ted.europa.eu/x']) {
 assert.equal(ui.officialUrl({...item,url}), null);
}
assert.match(ui.sourceMessage({items:[]}), /No tenders found/);
assert.match(ui.sourceMessage({total_failure:true}), /could not be reached/);
// Existing full-document contract requires full analysis and full scoring, not just a flag.
const document = {...item,full_ai_analyzed:true,full_analysis:{title:'SYNTHETIC document facts',required_documents:[]},
 full_scoring:{fit_score:65,completeness_percent:70,criteria:[],missing_information:[],stop_factors:[]}};
assert.doesNotMatch(ui.card(document,0), /Preliminary Match: 80/);
require('./main_customer_discovery_flow.test.cjs')(fs.readFileSync(file,'utf8'),assert)
 .catch(error=>{console.error(error);process.exitCode=1;});
