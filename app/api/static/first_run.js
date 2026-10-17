/* Genuine first-run opportunities. No invented demo records or background polling. */
(function(root){
'use strict';
function scoredTop(records,limit=4){
 if(!Array.isArray(records))return [];
 const score=x=>Number.isFinite(x?.preliminary_scoring?.fit_score)?x.preliminary_scoring.fit_score:-1;
 return records.filter(x=>x&&x.source&&x.external_id&&x.title)
  .slice(0,200).sort((a,b)=>score(b)-score(a)).slice(0,limit);
}
if(typeof module!=='undefined'&&module.exports)module.exports={scoredTop};
if(typeof document==='undefined')return;
const panel=document.getElementById('firstRunPreview');
const status=document.getElementById('firstRunStatus');
const result=document.getElementById('firstRunResults');
if(!panel||!status||!result)return;
let serial=0,scope='',controller=null;
const attempted=new Set();
const context=()=>String(state.organizationId)+':'+String(state.activeCompanyId)+':'+String(state.uiEpoch||0);
const eligible=()=>typeof usingSharedOrganization==='function'&&usingSharedOrganization()
 &&Number.isInteger(state.activeCompanyId)&&location.port!=='8765';
function render(data,cached){
 result.replaceChildren();
 if(data?.total_failure||!data?.successful_sources?.length){
  status.textContent='Real procurement sources are unavailable. Check source status in Discover.';
  return;
 }
 const rows=scoredTop(data?.items);
 if(!rows.length){
  status.textContent='No matching active tenders found in available sources. Refine the company profile and retry in Discover.';
  return;
 }
 status.textContent=(cached?'Previously discovered':'Just discovered')+
  ' opportunities for '+state.activeCompanyName+
  '. Verify deadlines on original procurement sites before applying.';
 for(const item of rows){
  const card=document.createElement('article');card.className='tender-card';
  const heading=document.createElement('h3');heading.textContent=item.title;card.append(heading);
  const line=document.createElement('p');
  const score=item.preliminary_scoring?.fit_score;
  line.textContent='Source: '+item.source+' · Preliminary match: '+
   (Number.isFinite(score)?score+'%':'not enough data')+
   ' · Deadline: '+(item.deadline||'not provided');
  card.append(line);
  const link=root.ValyqonDiscovery?.officialUrl?.(item);
  if(link){
   const a=document.createElement('a');a.href=link;a.target='_blank';
   a.rel='noopener noreferrer';a.textContent='View original tender';card.append(a);
  }else{
   const note=document.createElement('p');
   note.textContent='Review original source link in Discover.';card.append(note);
  }
  result.append(card);
 }
}
async function json(url,options){
 const r=await fetch(url,{credentials:'same-origin',cache:'no-store',...options});
 if(!r.ok)throw new Error('Search unavailable');
 return r.json();
}
async function refresh(){
 if(!eligible()){
  panel.hidden=true;scope='';controller?.abort();result.replaceChildren();return;
 }
 panel.hidden=false;
 const current=context(),companyKey=String(state.organizationId)+':'+String(state.activeCompanyId);
 if(current===scope)return;
 scope=current;
 const ticket=++serial;
 controller?.abort();controller=new AbortController();
 result.replaceChildren();
 const signal=controller.signal;
 status.textContent='Preparing real company-matched tender recommendations...';
 const base='/api/v1/organizations/'+encodeURIComponent(state.organizationId);
 try{
  const history=await json(base+'/discovery/history?limit=1',{signal});
  if(ticket!==serial||scope!==current)return;
  const latest=Array.isArray(history)?history[0]:null;
  const age=latest?Date.now()-Date.parse(latest.created_at):Infinity;
  if(latest&&latest.result_count>0&&Number.isFinite(age)&&age>=0&&age<24*3600*1000){
   const detail=await json(base+'/discovery/history/'+encodeURIComponent(latest.id),{signal});
   if(ticket!==serial||scope!==current)return;
   render(detail.discovery,true);
   return;
  }
  if(attempted.has(companyKey)){
   status.textContent='Open Discover for a fresh company-matched search.';
   return;
  }
  attempted.add(companyKey);
  status.textContent='Checking live tender feeds against your company profile...';
  const live=await json(base+'/discover/tenders',{method:'POST',signal});
  if(ticket!==serial||scope!==current)return;
  render(live,false);
 }catch(error){
  if(ticket===serial&&scope===current)
   status.textContent='Live matching is currently unavailable. Your profile is saved. Open Discover to retry.';
 }
}
root.addEventListener('workspace-context',refresh);
root.addEventListener('hashchange',refresh);
refresh();
})(typeof window!=='undefined'?window:globalThis);
