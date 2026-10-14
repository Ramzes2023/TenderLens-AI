'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const nodes=['Command Center','Find opportunities','Search history','Saved opportunities','Monitoring center','Source Health','AI Analysis','Documents','Team','Companies','Billing','Settings','Refresh status','No active company','No analyzed PDF tenders stored for this account yet.','Showing 1 previous search for Synthetic company.','Showing 2 previous searches for Synthetic company.','Source key: sam_gov'].map(nodeValue=>({nodeValue,parentElement:{closest:()=>false}}));
const customer={nodeValue:'Command Center',parentElement:{closest:()=>true}};nodes.push(customer);
const input={value:'My original profile',attributes:{placeholder:'Company name'},getAttribute(k){return this.attributes[k];},setAttribute(k,v){this.attributes[k]=v;}};
let locale='ru',observer;
const events={},state={organizationId:7,activeCompanyId:11},original=JSON.stringify(state);
const context={state,NodeFilter:{SHOW_TEXT:4},MutationObserver:class{constructor(fn){observer=fn;}observe(){}},document:{body:{},createTreeWalker(){let i=-1;return {nextNode(){return ++i<nodes.length;},get currentNode(){return nodes[i];}};},querySelectorAll:()=>[input]},window:{MainLocale:{get locale(){return locale;}},addEventListener:(name,fn)=>events[name]=fn},fetch(){throw Error('Locale must never fetch');}};
vm.runInNewContext(fs.readFileSync('app/api/static/workspace_locale.js','utf8'),context);
assert.ok(Object.keys(context.window.WorkspaceLocale.copy).length>200);
for(const [en,ru] of Object.entries(context.window.WorkspaceLocale.copy)){assert.ok(en.trim());assert.match(ru,/[А-Яа-яЁё]/,en);}
for(const node of nodes.slice(0,-1)) assert.match(node.nodeValue,/[А-Яа-яЁё]/);
assert.equal(customer.nodeValue,'Command Center');assert.equal(input.value,'My original profile');assert.equal(input.attributes.placeholder,'Название компании');
locale='en';events['shell-locale-change']();assert.equal(nodes[0].nodeValue,'Command Center');assert.equal(input.attributes.placeholder,'Company name');
locale='ru';events['shell-locale-change']();nodes[0].nodeValue='Find opportunities';observer();assert.equal(nodes[0].nodeValue,'Найти закупки');
observer();assert.equal(nodes[0].nodeValue,'Найти закупки');assert.equal(JSON.stringify(state),original);
console.log('UI locale: route catalogue, reversible copy, dynamic updates, customer exclusions, attributes and unchanged tenant state passed');
