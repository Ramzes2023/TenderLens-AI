'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const read=p=>fs.readFileSync(path.join(__dirname,'../..',p),'utf8');
const css=read('app/api/static/premium.css'),html=read('app/api/saas_shell.py');
const shell=read('app/api/static/shell.js'),locale=read('app/api/static/locale.js');
// Evaluate declarations of the actual scoped rules, including last-rule wins.
const rules=[...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)];
function declarations(selector){
 const result={};
 for(const [,selectors,body] of rules){
  if(selectors.split(',').some(s=>s.trim()===selector)){
   for(const declaration of body.split(';')){
    const i=declaration.indexOf(':');if(i>0)result[declaration.slice(0,i).trim()]=declaration.slice(i+1).trim();
   }
  }
 }
 return result;
}
const scope='body.saas.command-view .document-intelligence';
const vars=declarations(scope);
function color(selector){const value=declarations(selector).color;return value?.startsWith('var(')?vars[value.slice(4,-1)]:value;}
function luminance(hex){if(hex.length===4)hex='#'+[...hex.slice(1)].map(c=>c+c).join('');const values=hex.slice(1).match(/../g).map(v=>parseInt(v,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return values.reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);}
function contrast(fg,bg){const a=luminance(fg),b=luminance(bg);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);}
const background=declarations('.document-workflows article').background;
assert.equal(background,'#0b162b');
for(const tag of ['h2','h3','p','.fine','.help','.eyebrow','a']){
 const fg=color(scope+' '+tag);assert.match(fg,/^#[a-f0-9]{6}$/i,tag+' has explicit resolved color');
 assert.ok(contrast(fg,background)>=4.5,tag+' contrast');
 // These selectors outrank the generic light shell rules, regardless of order.
 assert.ok((scope+' '+tag).includes('body.saas.command-view .document-intelligence'));
}
for(const suffix of ['.neutral-pill','a.cta','a.secondary','button:disabled']){
 const rule=declarations(scope+' '+suffix);assert.ok(contrast(color(scope+' '+suffix),rule.background)>=4.5,suffix+' contrast');
}
assert.equal(declarations(scope+' button:disabled').opacity,'1');
assert.match(declarations(scope+' :focus-visible').outline,/3px solid/);
const hub=html.split('<section id="documentIntelligence"')[1].split('</section>')[0];
assert.equal((hub.match(/<article>/g)||[]).length,3);
assert.equal((html.match(/data-page="ai-analysis"/g)||[]).length,1);
assert.doesNotMatch(hub,/Planned workspace/);
assert.match(shell,/hidden=page==='ai-analysis'\|\|!future\[page\]/);
assert.match(hub,/<button id="ragUpload" type="button" disabled/);
assert.match(hub,/<button id="ragAsk" type="button" disabled/);
assert.match(hub,/Processing requires configured services and a running worker/);
assert.match(locale,/language: \['Language', '\u042f\u0437\u044b\u043a'\]/);
assert.match(html,/id="shellLocaleScope"[^>]* hidden/);
assert.match(html,/premium.css\?v=phase24-visual-20261012/);
assert.match(html,/shell.js\?v=ui-fix-20261013/);
assert.match(html,/id="geographyWorkspace" class="geo-workspace" data-page="geography" hidden/);
assert.doesNotMatch(css.slice(css.indexOf('/* Visual review:')),/geo-workspace|geo-map|svg|path\s*\{/);
// Execute permission, preview/approval and locale behavior regressions too.
require('./main_pdf_ai_ux.test.cjs');
require('./main_ui_consistency.test.cjs');
console.log('PDF hub scoped colors/contrast, routing, disabled RAG and locale regressions passed');
