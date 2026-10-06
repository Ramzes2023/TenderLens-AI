/* Pure rendering/filtering contracts are also exercised by Node regression tests. */
(function(root){
'use strict';
const escape=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const percent=v=>typeof v==='number'&&Number.isFinite(v)?`${v}%`:'Not enough data';
function safeUrl(value){try{const u=new URL(value);return ['https:','http:'].includes(u.protocol)&&!u.username&&!u.password?u.href:null;}catch{return null;}}
function matches(item,f){
 const score=item.preliminary_scoring||{}, text=[item.title,item.summary,item.metadata_analysis?.procurement_object].filter(Boolean).join(' ').toLowerCase();
 if(f.keyword&&!text.includes(f.keyword.toLowerCase()))return false;
 if(f.source&&item.source!==f.source)return false;
 if(f.buyer&&!String(item.customer||'').toLowerCase().includes(f.buyer.toLowerCase()))return false;
 if(f.currency&&item.currency!==f.currency)return false;
 if(f.value!==''&&f.currency&&(item.initial_price==null||item.initial_price<Number(f.value)))return false;
 if(f.fit!==''&&(score.fit_score==null||score.fit_score<Number(f.fit)))return false;
 if(f.deadline&&(!item.deadline||!Number.isFinite(Date.parse(item.deadline))||Date.parse(item.deadline)>Date.parse(f.deadline+'T23:59:59Z')))return false;
 if(f.published&&(!item.published_at||!Number.isFinite(Date.parse(item.published_at))||Date.parse(item.published_at)<Date.parse(f.published)))return false;
 return true;
}
function matchHtml(item){const s=item.preliminary_scoring||{};return `<div class="match-block"><strong>Preliminary Match: ${escape(percent(s.fit_score))}</strong><br>Data completeness ${escape(percent(s.completeness_percent))}<p class="fine">Company fit from available metadata. Review full documents before deciding.</p></div>`;}
function cardShortlistControl(index,savedRecord,enabled){if(!enabled)return '';return savedRecord?'<button type="button" disabled aria-disabled="true">Saved</button>':`<button type="button" data-save="${index}">Save opportunity</button>`;}
function detailShortlistControl(index,savedRecord,enabled){if(!enabled)return '';return savedRecord?`<button type="button" data-remove="${index}">Remove from saved</button>`:`<button type="button" data-save="${index}">Save opportunity</button>`;}
function card(item,index,savedRecord){const shortlist=cardShortlistControl(index,savedRecord,arguments.length>=3);return `<article class="tender-card"><span class="chip">${escape(item.source)}</span> <span class="chip">${item.full_ai_analyzed?'Document analysis available':'Metadata preview'}</span><h3>${escape(item.title||'Untitled notice')}</h3><div class="tender-meta"><span>Buyer: ${escape(item.customer||'Not provided')}</span><span>Number: ${escape(item.tender_number||'Not provided')}</span><span>Value: ${escape(item.initial_price??'Not provided')} ${escape(item.currency||'')}</span><span>Region: ${escape(item.region||'Not provided')}</span><span>Deadline: ${escape(item.deadline||'Not provided')}</span><span>Published: ${escape(item.published_at||'Not provided')}</span></div><p>${escape((item.summary||item.metadata_analysis?.procurement_object||'No summary supplied.').slice(0,500))}</p>${matchHtml(item)}<button data-detail="${index}">Open tender workspace</button>${shortlist}</article>`;}
const list=values=>values?.length?'<ul>'+values.map(v=>`<li>${escape(v)}</li>`).join('')+'</ul>':'<p>Not provided in metadata.</p>';
function detail(item,savedRecord,index){const score=item.preliminary_scoring||{},a=item.metadata_analysis||{},url=safeUrl(item.url),shortlist=detailShortlistControl(index,savedRecord,arguments.length>=3);return `<section><h3>Overview</h3><dl>${[['Source',item.source],['Buyer',item.customer],['Tender number',item.tender_number],['Region',item.region],['Deadline',item.deadline],['Published',item.published_at],['Value',item.initial_price==null?null:`${item.initial_price} ${item.currency||''}`]].map(([k,v])=>`<dt>${k}</dt><dd>${escape(v??'Not provided')}</dd>`).join('')}</dl><p>${escape(item.summary||a.procurement_object||'No summary supplied.')}</p></section><div class="detail-grid"><section><h3>Company Match</h3>${matchHtml(item)}${(score.criteria||[]).map(c=>`<div class="criterion"><strong>${escape(c.label||c.code)}</strong><p>Status: ${escape(c.status==='not_scored'?'Missing data \u2014 not scored':c.status)}</p><p>Points: ${escape(c.earned_points??'?')} / ${escape(c.weight??'?')}</p><p>${escape(c.explanation)}</p>${list(c.evidence)}</div>`).join('')}<h4>Missing information</h4>${list(score.missing_information)}</section><section><h3>Requirements</h3>${list(a.participant_requirements)}${list(a.technical_requirements)}<h3>Documents</h3><p>Documents not imported yet.</p><h4>Document requirements in metadata</h4>${list(a.required_documents)}<h3>Risks</h3>${list(score.document_risks)}${list(score.stop_factors)}<h3>AI Analysis</h3><p>${item.full_ai_analyzed?'Consult the stored document analysis through the supported document workflow.':'Full AI analysis has not been run for this tender yet.'}</p><button disabled>Analyze Tender \u2014 document import required</button><h3>Actions</h3>${url?`<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">Open official source</a>`:'<p>No safe source link available.</p>'}${shortlist}</section></div>`;}
function sourceMessage(report){if(report.total_failure)return 'Sources could not be reached. Please retry discovery.';if(report.partial_failure)return 'Results are available, but some procurement sources could not be reached.';return report.items?.length?'Discovery complete.':'No tenders found. Review company search keywords or try again later.';}
/* VALYQON DISCOVERY RANKING V1 */
function rankedItems(values){
 const rows=Array.isArray(values)?[...values]:[];
 return rows.sort((a,b)=>{
  const as=Number(a?.preliminary_scoring?.fit_score);
  const bs=Number(b?.preliminary_scoring?.fit_score);
  const ac=Number(a?.preliminary_scoring?.completeness_percent);
  const bc=Number(b?.preliminary_scoring?.completeness_percent);
  const aScore=Number.isFinite(as)?as:-1;
  const bScore=Number.isFinite(bs)?bs:-1;
  const aComplete=Number.isFinite(ac)?ac:-1;
  const bComplete=Number.isFinite(bc)?bc:-1;
  return (bScore-aScore)||(bComplete-aComplete);
 });
}
function sourceMix(values){
 const counts=new Map();
 for(const item of values||[]){
  const key=String(item?.source||'unknown');
  counts.set(key,(counts.get(key)||0)+1);
 }
 return [...counts.entries()]
  .map(([source,count])=>`${source}: ${count}`)
  .join(', ');
}

const publicApi={matches,card,detail,safeUrl,sourceMessage,percent};
if(typeof module!=='undefined'&&module.exports)module.exports=publicApi;
root.ValyqonDiscovery=publicApi;
if(typeof document==='undefined')return;
const $=id=>document.getElementById(id);let items=[],report=null,serial=0,controller=null,context='',detailIndex=null,shortlistSerial=0;const savedByKey=new Map();
const identity=()=>`${state.organizationId}:${state.activeCompanyId??''}:${state.uiEpoch||0}`;
function reset(){if(typeof CustomEvent!=='undefined')window.dispatchEvent(new CustomEvent('discovery-report',{detail:null}));serial++;shortlistSerial++;controller?.abort();controller=null;items=[];report=null;savedByKey.clear();detailIndex=null;if($('discoveredCount'))$('discoveredCount').textContent='Not run';if($('scoredCount'))$('scoredCount').textContent='Not run';$('discoveryResults').replaceChildren();$('sourceHealth').textContent='';$('discoveryMessage').textContent='Run discovery to find opportunities.';if($('tenderDetail').open)$('tenderDetail').close();$('detailBody').replaceChildren();update();}
function update(){const ready=usingSharedOrganization()&&Number.isInteger(state.activeCompanyId);$('discoverButton').disabled=!ready||Boolean(controller);$('discoverContext').textContent=!usingSharedOrganization()?'Select or create a shared organization in Team for global discovery.':ready?`Matching ${state.activeCompanyName}`:'Create and activate a company in Companies first.';}
function filters(){return Object.fromEntries(['keyword','source','buyer','currency','value','fit','deadline','published'].map(k=>[k,$('filter'+k[0].toUpperCase()+k.slice(1)).value.trim()]));}
function render(){const f=filters();$('filterValue').disabled=!f.currency;const visible=items.map((item,i)=>({item,i})).filter(({item})=>matches(item,f));$('discoveryResults').innerHTML=visible.map(({item,i})=>card(item,i,savedFor(item))).join('');if(report&&!report.total_failure){$('discoveryMessage').textContent=sourceMessage(report)+` Showing ${visible.length} of ${items.length} fetched results.`;if(items.length&&!visible.length)$('discoveryMessage').textContent+=' No results match these local filters.';}}
function options(id,values){const n=$(id),old=n.value;n.replaceChildren(new Option('All fetched values',''));[...new Set(values.filter(Boolean))].sort().forEach(v=>n.add(new Option(v,v)));n.value=[...n.options].some(o=>o.value===old)?old:'';}
function savedKey(item){return JSON.stringify([String(item?.source||''),String(item?.external_id||'')]);}
function savedFor(item){return savedByKey.get(savedKey(item))||null;}
function refreshDetail(){if(detailIndex===null||!$('tenderDetail').open)return;const item=items[detailIndex];if(!item)return;$('detailBody').innerHTML=detail(item,savedFor(item),detailIndex);}
function openDetail(index){const item=items[index];if(!item)return;detailIndex=index;$('detailTitle').textContent=item.title||'Tender workspace';$('detailBody').innerHTML=detail(item,savedFor(item),index);if(!$('tenderDetail').open)$('tenderDetail').showModal();}
async function loadShortlist(){const scope=identity(),ticket=++shortlistSerial,org=state.organizationId;if(!usingSharedOrganization()||!Number.isInteger(state.activeCompanyId))return;try{const r=await fetch(`/api/v1/organizations/${org}/shortlist`,{credentials:'same-origin',cache:'no-store'});if(ticket!==shortlistSerial||scope!==identity())return;if(r.status===401){location.replace('/login');return;}if(!r.ok)return;const records=await r.json();if(ticket!==shortlistSerial||scope!==identity())return;savedByKey.clear();for(const record of (Array.isArray(records)?records:[])){if(record?.opportunity)savedByKey.set(savedKey(record.opportunity),record);}render();refreshDetail();}catch(e){}}
async function saveItem(index,button){const item=items[index],scope=identity(),org=state.organizationId;if(!item||!usingSharedOrganization()||!Number.isInteger(state.activeCompanyId))return;if(button){button.disabled=true;button.textContent='Saving…';}try{const r=await fetch(`/api/v1/organizations/${org}/shortlist`,{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify(item)});if(scope!==identity())return;if(r.status===401){location.replace('/login');return;}if(!r.ok){if(button){button.disabled=false;button.textContent='Save opportunity';}return;}const record=await r.json();if(scope!==identity())return;savedByKey.set(savedKey(item),record);render();refreshDetail();}catch(e){if(button&&scope===identity()){button.disabled=false;button.textContent='Save opportunity';}}}
async function removeItem(index,button){const item=items[index],scope=identity(),org=state.organizationId;if(!item)return;const record=savedFor(item);if(!record||!Number.isInteger(Number(record.id)))return;if(button){button.disabled=true;button.textContent='Removing…';}try{const r=await fetch(`/api/v1/organizations/${org}/shortlist/${record.id}`,{method:'DELETE',credentials:'same-origin',cache:'no-store'});if(scope!==identity())return;if(r.status===401){location.replace('/login');return;}if(!r.ok&&r.status!==404){if(button){button.disabled=false;button.textContent='Remove from saved';}return;}savedByKey.delete(savedKey(item));render();refreshDetail();}catch(e){if(button&&scope===identity()){button.disabled=false;button.textContent='Remove from saved';}}}
async function discover(){if($('discoverButton').disabled)return;const ticket=++serial,scope=identity(),org=state.organizationId;controller=new AbortController();items=[];report=null;if($('discoveredCount'))$('discoveredCount').textContent='Not run';if($('scoredCount'))$('scoredCount').textContent='Not run';$('discoveryResults').replaceChildren();$('sourceHealth').textContent='';$('discoveryMessage').textContent='Searching configured sources…';update();
try{const r=await fetch(`/api/v1/organizations/${org}/discover/tenders`,{method:'POST',credentials:'same-origin',cache:'no-store',signal:controller.signal});if(ticket!==serial||scope!==identity())return;if(r.status===401){location.replace('/login');return;}if(!r.ok){$('discoveryMessage').textContent=r.status===403?'You do not have access to this organization.':r.status===409?'Create and activate an organization company first.':'Discovery is unavailable. Please retry.';return;}const data=await r.json();if(ticket!==serial||scope!==identity())return;report=data;if(typeof CustomEvent!=='undefined')window.dispatchEvent(new CustomEvent('discovery-report',{detail:data}));items=data.total_failure?[]:rankedItems(data.items||[]);if($('discoveredCount'))$('discoveredCount').textContent=data.total_failure?'Unavailable':String(items.length);if($('scoredCount'))$('scoredCount').textContent=data.total_failure?'Unavailable':String(items.filter(i=>i.preliminary_scoring?.fit_score!=null).length);options('filterSource',items.map(i=>i.source));options('filterCurrency',items.map(i=>i.currency));$('sourceHealth').textContent=`Attempted: ${(data.attempted_sources||[]).join(', ')||'none'} · Reached: ${(data.successful_sources||[]).join(', ')||'none'} · Unavailable: ${(data.failed_sources||[]).join(', ')||'none'}`;const mix=sourceMix(items);if(mix){$('sourceHealth').textContent+=` \u00b7 Results: ${mix}`;}$('discoveryMessage').textContent=sourceMessage(data);render();loadShortlist();}
catch(e){if(e.name!=='AbortError'&&ticket===serial)$('discoveryMessage').textContent='Network unavailable. Please retry discovery.';}
finally{if(ticket===serial){controller=null;update();}}}
$('discoverButton').onclick=discover;
$('discoveryWorkspace').querySelectorAll('input,select').forEach(n=>n.addEventListener('input',render));
$('resetFilters').onclick=()=>{$('discoveryWorkspace').querySelectorAll('input,select').forEach(n=>n.value='');render();};
$('discoveryResults').onclick=e=>{const save=e.target.closest('[data-save]');if(save){saveItem(Number(save.dataset.save),save);return;}const button=e.target.closest('[data-detail]');if(!button)return;openDetail(Number(button.dataset.detail));};
$('detailBody').onclick=e=>{const save=e.target.closest('[data-save]');if(save){saveItem(Number(save.dataset.save),save);return;}const remove=e.target.closest('[data-remove]');if(remove){removeItem(Number(remove.dataset.remove),remove);}};
$('closeDetail').onclick=()=>{detailIndex=null;$('tenderDetail').close();};
$('tenderDetail').addEventListener('close',()=>{detailIndex=null;});
window.addEventListener('workspace-context',()=>{if(context!==identity()){context=identity();reset();}else update();});update();
})(typeof globalThis!=='undefined'?globalThis:this);
