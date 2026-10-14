'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const read=p=>fs.readFileSync(require('node:path').join(__dirname,'../..',p),'utf8');
const source=read('app/api/dashboard.py');
const apply=source.split('async function applyCompanyPdfProfile()')[1].split('async function createCompany()')[0];
const preview=source.split('async function previewCompanyProfilePdf()')[1].split('async function applyCompanyPdfProfile()')[0];
assert.doesNotMatch(preview,/method:'PATCH'|applyCompanyPdfProfile\(\);/);
assert.match(apply,/profile:preview.suggested_profile/);
assert.match(apply,/JSON.stringify\(latest.profile\)/);
assert.ok(apply.indexOf('Review profile -> Find tenders')>apply.indexOf("method:'PATCH'"));
const fn='async function applyCompanyPdfProfile()'+apply.replaceAll('${{','${').replaceAll('{{','{').replaceAll('}}','}');
async function boot({port='',active=7,write=true,fail=false,preview=true}={}){
 const nodes=new Map(),calls=[],buttons=[];
 const node=id=>{if(!nodes.has(id))nodes.set(id,{innerHTML:'',value:'',appendChild:b=>buttons.push(b)});return nodes.get(id);};
 const profile={product_keywords:['industrial pumps']};
 const state={organizationId:4,activeCompanyId:active,editCompanyId:7,companyPdfPreview:preview?{current_profile:profile,suggested_profile:profile}:null};
 const c={state,location:{port,hash:'#companies'},document:{getElementById:node,createElement:()=>({})},usingSharedOrganization:()=>true,canWriteWorkspace:()=>write,
 organizationBase:()=>'/api/v1/organizations/4',esc:String,loadCompanies:async()=>calls.push('load'),api:async(p,o)=>{calls.push(o?.method||'GET');if(fail&&o)throw Error('denied');return {name:'Pumps',profile};}};
 vm.runInNewContext(fn,c);await c.applyCompanyPdfProfile();return {c,calls,buttons};
}
(async()=>{
 const x=await boot();assert.deepEqual(x.calls,['GET','PATCH','load']);assert.equal(x.buttons.length,1);assert.equal(x.c.location.hash,'#companies');
 const before=[...x.calls];x.buttons[0].onclick();assert.equal(x.c.location.hash,'discover');assert.deepEqual(x.calls,before);
 for(const key of ['organizationId','activeCompanyId']){x.c.location.hash='#companies';x.c.state[key]=99;x.buttons[0].onclick();assert.equal(x.c.location.hash,'#companies');x.c.state[key]=key==='organizationId'?4:7;}
 x.c.canWriteWorkspace=()=>false;x.c.location.hash='#companies';x.buttons[0].onclick();assert.equal(x.c.location.hash,'#companies');
 for(const opts of [{port:'8765'},{active:8},{fail:true},{write:false},{preview:false}]){const y=await boot(opts);assert.equal(y.buttons.length,0);if(opts.write===false||opts.preview===false)assert.deepEqual(y.calls,[]);}
 const css=read('app/api/static/premium.css');
 const rule=css.match(/body\.saas\.command-view \.overview-setup-steps article\s*\{([^}]+)\}/)[1];
 assert.match(rule,/background:#172640/);assert.match(rule,/color:#e9efff/);assert.match(rule,/opacity:1/);
 const lum=h=>{const rgb=h.match(/../g).map(v=>parseInt(v,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;};
 for(const text of ['e9efff','b8c6dd'])assert.ok((lum(text)+.05)/(lum('172640')+.05)>=4.5);
 assert.match(css,/:focus-visible/);assert.match(css,/repeat\(3,minmax\(0,1fr\)\)/);assert.match(css,/grid-template-columns:1fr/);
 console.log('PDF explicit apply, optional navigation, scope/role/preview guards and card contrast PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
