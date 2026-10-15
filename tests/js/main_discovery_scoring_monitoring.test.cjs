'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const file = path.join(__dirname, '../../app/api/static/discovery.js');
const source = fs.readFileSync(file, 'utf8');
const discovery = require(file);
const item = {source:'ted', external_id:'synthetic', title:'Industrial pumps',
 full_ai_analyzed:false, metadata_analysis:{required_documents:[]},
 preliminary_scoring:{fit_score:null, criteria:[{code:'documents', status:'not_scored',
 explanation:'Document inventory unknown', evidence:[]}], missing_information:['Delivery unknown']}};
const card = discovery.card(item, 0);
assert.match(card, /Preliminary Match/);
assert.match(card, /available metadata/);
assert.match(card, /Review full documents/);
assert.match(card, /Not enough data/);
const detail = discovery.detail(item);
assert.match(detail, /Missing data.*not scored/);
assert.match(detail, /Document inventory unknown/);
assert.match(detail, /Delivery unknown/);
assert.match(detail, /Full AI analysis has not been run/);
assert.match(detail, /Document requirements in metadata/);
assert.match(discovery.sourceMessage({partial_failure:true}), /some procurement sources could not be reached/);
assert.match(discovery.sourceMessage({total_failure:true}), /Sources could not be reached/);
// Monitoring is a separate user action, never an automatic Discovery side effect.
assert.doesNotMatch(source, /\/monitoring\/scan/);
const nodes = {}, events = {};
function node(id) { return nodes[id] ||= {value:'', textContent:'', innerHTML:'', disabled:false,
 options:[], open:false, replaceChildren(...rows){this.innerHTML='';this.options=rows;},
 add(row){this.options.push(row);}, addEventListener(){}, querySelectorAll(){return [];},
 querySelector(){return null;}, close(){this.open=false;}}; }
let resolve;
const calls = [];
const context = {document:{getElementById:node}, window:{addEventListener:(key, fn)=>{events[key]=fn;}},
 state:{organizationId:11, activeCompanyId:21, activeCompanyName:'Synthetic A', uiEpoch:0},
 usingSharedOrganization:()=>true, canWriteWorkspace:()=>false, AbortController, URL,
 Option:function(text,value){this.text=text;this.value=value;}, location:{hash:'',replace(){}},
 fetch:(url,options)=>{calls.push({url,options});return new Promise(r=>{resolve=r;});}};
vm.runInNewContext(source, context);
(async()=>{
 const pending = node('discoverButton').onclick();
 assert.equal(calls[0].url, '/api/v1/organizations/11/discover/tenders');
 assert.equal(calls[0].options.method, 'POST');
 assert.equal(calls[0].options.credentials, 'same-origin');
 context.state.activeCompanyId=22; // Same organization, different active company.
 events['workspace-context']();
 assert.equal(calls[0].options.signal.aborted, true);
 resolve({ok:true,status:200,json:async()=>({items:[item]})});
 await pending;
 assert.equal(node('discoveryResults').innerHTML, '');
 assert.equal(calls.length, 1);
 assert.equal(node('sourceHealth').textContent, '');
 context.state.organizationId=12;
 context.state.uiEpoch++;
 events['workspace-context']();
 assert.equal(node('discoveredCount').textContent, 'Not run');
 assert.equal(node('scoredCount').textContent, 'Not run');
 console.log('PASS: honest Discovery labels and cross-company stale response isolation');
})().catch(error=>{console.error(error);process.exitCode=1;});
