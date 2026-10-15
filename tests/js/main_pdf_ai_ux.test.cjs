'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const read=p=>fs.readFileSync(path.join(__dirname,'../..',p),'utf8');
const shell=read('app/api/static/shell.js'),html=read('app/api/saas_shell.py'),dashboard=read('app/api/dashboard.py');
const hub=shell.split('/* Document hub only')[1].split('/* Workspace lifecycle:')[0];
function boot(port=''){
 const nodes=Object.fromEntries(['openCompanyPdf','companyPdfHubGate','pdfPreviewNotice','companyPdfFile'].map(id=>[id,{dataset:{},addEventListener(k,f){this[k]=f;},focus(){this.focused=true;}}]));
 const events={},calls=[],state={activeCompanyId:7,companies:[{id:7}],organizationId:4,uiEpoch:3};
 const c={state,location:{port,hash:'#ai-analysis'},document:{getElementById:id=>nodes[id]},usingSharedOrganization:()=>true,canWriteWorkspace:()=>true,editCompany:id=>calls.push(id),window:{MainLocale:{locale:'en'},addEventListener:(k,f)=>events[k]=f}};
 vm.runInNewContext('/* Document hub only'+hub,c);return {c,nodes,events,calls,state};
}
const x=boot();assert.equal(x.nodes.openCompanyPdf.disabled,false);
x.nodes.openCompanyPdf.click();assert.equal(x.c.location.hash,'companies');assert.deepEqual(x.calls,[7]);assert.equal(x.nodes.companyPdfFile.focused,true);assert.equal(x.state.activeCompanyId,7);
for(const change of [()=>x.c.canWriteWorkspace=()=>false,()=>x.c.usingSharedOrganization=()=>false,()=>x.state.companies=[],()=>x.state.activeCompanyId=null]){
 change();x.events['workspace-context']();assert.equal(x.nodes.openCompanyPdf.disabled,true);x.nodes.openCompanyPdf.click();assert.deepEqual(x.calls,[7]);
}
x.c.window.MainLocale.locale='ru';x.events['shell-locale-change']();assert.match(x.nodes.companyPdfHubGate.textContent,/Выберите/);
const preview=boot('8765');assert.equal(preview.nodes.pdfPreviewNotice.hidden,false);assert.equal(preview.nodes.openCompanyPdf.disabled,true);preview.nodes.openCompanyPdf.click();assert.deepEqual(preview.calls,[]);
assert.match(html,/id="documentIntelligence"[^>]*data-page="ai-analysis" hidden/);
for(const destination of ['discover','saved','documents'])assert.match(html,new RegExp('href="#'+destination+'" data-ui-en='));
assert.match(html,/<button id="ragUpload" type="button" disabled/);
assert.match(html,/<button id="ragAsk" type="button" disabled/);
assert.match(html,/\/assets\/rag.js/);
assert.doesNotMatch(shell.match(/const future=([^\n]+)/)[1],/'ai-analysis'/);
// Execute the actual page router: the hub is visible and the placeholder is hidden.
const router=shell.slice(shell.indexOf(' function navigate()'),shell.indexOf(' function closeNavigation'));
const nav=['ai-analysis','companies','discover','saved','documents'].map(page=>({dataset:{nav:page},textContent:page,setAttribute(){}}));
const pages=nav.map(n=>({dataset:{page:n.dataset.nav},hidden:true}));
const routerNodes=Object.fromEntries(['pageHeading','futurePage','futureTitle','futureText','futureNext','appNav','navToggle'].map(id=>[id,{classList:{remove(){}},setAttribute(){},removeAttribute(){}}]));
const r={location:{hash:'#ai-analysis'},CSS:{escape:v=>v},future:{},$:id=>routerNodes[id],document:{body:{classList:{toggle(){}}},querySelector:s=>nav.find(n=>s===`[data-nav="${n.dataset.nav}"]`),querySelectorAll:s=>s==='[data-nav]'?nav:pages}};
vm.runInNewContext(router+'navigate();',r);assert.equal(pages[0].hidden,false);assert.equal(routerNodes.futurePage.hidden,true);
r.location.hash='#documents';vm.runInNewContext('navigate();',r);assert.equal(pages[0].hidden,true);assert.equal(pages[4].hidden,false);
assert.doesNotMatch(hub,/fetch\(|api\(|applyCompanyPdfProfile\(|scanMonitoring\(/);
const previewFn=dashboard.split('async function previewCompanyProfilePdf()')[1].split('async function applyCompanyPdfProfile()')[0];
assert.match(previewFn,/\/companies\/\$\{\{companyId\}\}\/profile-from-pdf\/preview/);
assert.match(previewFn,/form\.append\(\s*'file'/);assert.match(previewFn,/method:'POST'/);assert.doesNotMatch(previewFn,/method:'PATCH'|applyCompanyPdfProfile\(\);/);
const apply=dashboard.split('async function applyCompanyPdfProfile()')[1].split('async function createCompany()')[0];
assert.match(apply,/\|\|!preview/);assert.match(apply,/JSON\.stringify\(latest.profile\)/);assert.match(apply,/preview.current_profile/);assert.match(apply,/method:'PATCH'/);assert.match(apply,/profile:preview.suggested_profile/);
for(const p of ['discovery.js','saved.js']){const s=read('app/api/static/'+p);assert.match(s,/`\/api\/v1\/organizations\/\$\{org\}\/analysis\/pdf`/);assert.match(s,/method:'POST'/);assert.match(s,/body:form/);assert.match(s,/credentials:'same-origin'/);}
console.log('Document hub navigation, permissions, preview isolation and existing PDF contracts passed');
