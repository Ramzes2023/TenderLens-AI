/* Active-company Saved Opportunities workspace. */
(function(){
'use strict';

const $=id=>document.getElementById(id);
const workspace=$('savedWorkspace');

if(!workspace)return;

const renderer=window.ValyqonDiscovery;

let records=[];
let serial=0;
let context='';

const identity=()=>`${state.organizationId}:${state.activeCompanyId??''}:${state.uiEpoch||0}`;
const currentPage=()=>location.hash.slice(1)||'overview';

function ready(){
 return usingSharedOrganization()&&Number.isInteger(state.activeCompanyId);
}

function updateContext(){
 if(!usingSharedOrganization()){
  $('savedContext').textContent='Select or create a shared organization in Team first.';
  return;
 }

 if(!Number.isInteger(state.activeCompanyId)){
  $('savedContext').textContent='Create and activate a company in Companies first.';
  return;
 }

 $('savedContext').textContent=`Saved for ${state.activeCompanyName}`;
}

function clearResults(message){
 records=[];
 $('savedCount').textContent='Not loaded';
 $('savedResults').replaceChildren();
 $('savedMessage').textContent=message;
}

function render(){
 if(!renderer){
  clearResults('Saved opportunity rendering is unavailable. Refresh the workspace.');
  return;
 }

 $('savedCount').textContent=String(records.length);

 $('savedResults').innerHTML=records
  .map((record,index)=>renderer.card(record.opportunity,index,record))
  .join('');

 $('savedMessage').textContent=records.length
  ? `Showing ${records.length} saved ${records.length===1?'opportunity':'opportunities'} for ${state.activeCompanyName}.`
  : 'No saved opportunities for this company yet. Use Discover to add opportunities to the shortlist.';
}

function renderSavedDetail(index){
 const record=records[index];

 if(
  !record?.opportunity
  ||!renderer
 )return;

 $('savedDetailBody').innerHTML=
  renderer.detail(
   record.opportunity,
   record,
   index,
   canWriteWorkspace()
  );
}

function openDetail(index){
 const record=records[index];

 if(!record?.opportunity||!renderer)return;

 $('savedDetailTitle').textContent=
  record.opportunity.title||'Saved opportunity';

 renderSavedDetail(index);

 if(!$('savedDetail').open){
  $('savedDetail').showModal();
 }
}

function opportunityKey(item){
 return JSON.stringify([
  String(item?.source||''),
  String(item?.external_id||'')
 ]);
}

function savedRequestStillCurrent(
 index,
 scope,
 ticket,
 savedId,
 expectedOpportunity
){
 const current=records[index];

 return (
  scope===identity()
  &&ticket===serial
  &&Number(current?.id)===savedId
  &&opportunityKey(
   current?.opportunity
  )===expectedOpportunity
 );
}

async function analyzeSavedTenderPdf(
 index,
 button
){
 const record=records[index];
 const savedId=Number(record?.id);

 if(
  !record?.opportunity
  ||!Number.isInteger(savedId)
  ||!ready()
  ||!canWriteWorkspace()
  ||!renderer
  ||typeof renderer.applyFullAiResult!=='function'
 ){
  return;
 }

 const input=$(
  `fullAiFile-${index}`
 );

 const statusNode=$(
  `fullAiStatus-${index}`
 );

 const file=input?.files?.[0];

 if(!file){
  if(statusNode){
   statusNode.textContent=
    'Choose a tender PDF first.';
  }

  return;
 }

 const lowerName=String(
  file.name||''
 ).toLowerCase();

 if(
  file.type!=='application/pdf'
  &&!lowerName.endsWith('.pdf')
 ){
  if(statusNode){
   statusNode.textContent=
    'Only PDF files are supported.';
  }

  return;
 }

 if(file.size>10*1024*1024){
  if(statusNode){
   statusNode.textContent=
    'PDF exceeds the 10 MiB limit.';
  }

  return;
 }

 const scope=identity();
 const ticket=serial;
 const org=state.organizationId;

 const expectedOpportunity=
  opportunityKey(
   record.opportunity
  );

 const form=new FormData();

 form.append(
  'file',
  file
 );

 if(button){
  button.disabled=true;
  button.textContent='Analyzing...';
 }

 if(statusNode){
  statusNode.textContent=
   'Extracting tender document and running Full AI analysis...';
 }

 try{
  const analysisResponse=
   await fetch(
    `/api/v1/organizations/${org}/analysis/pdf`,
    {
     method:'POST',
     credentials:'same-origin',
     cache:'no-store',
     body:form
    }
   );

  if(
   !savedRequestStillCurrent(
    index,
    scope,
    ticket,
    savedId,
    expectedOpportunity
   )
  ){
   return;
  }

  if(analysisResponse.status===401){
   location.replace('/login');
   return;
  }

  if(analysisResponse.status===403){
   if(statusNode){
    statusNode.textContent=
     'Your organization role cannot analyze tender documents.';
   }
   return;
  }

  if(analysisResponse.status===409){
   if(statusNode){
    statusNode.textContent=
     'The active company changed. Reopen Saved Opportunities and try again.';
   }
   return;
  }

  if(analysisResponse.status===413){
   if(statusNode){
    statusNode.textContent=
     'PDF exceeds the supported size or extraction limit.';
   }
   return;
  }

  if(analysisResponse.status===415){
   if(statusNode){
    statusNode.textContent=
     'Only PDF files are supported.';
   }
   return;
  }

  if(analysisResponse.status===422){
   if(statusNode){
    statusNode.textContent=
     'The PDF could not be analyzed. It may be scanned, encrypted, damaged, or contain no extractable text.';
   }
   return;
  }

  if(!analysisResponse.ok){
   if(statusNode){
    statusNode.textContent=
     'Full AI document analysis is unavailable. Please retry.';
   }
   return;
  }

  const result=
   await analysisResponse.json();

  if(
   !savedRequestStillCurrent(
    index,
    scope,
    ticket,
    savedId,
    expectedOpportunity
   )
  ){
   return;
  }

  const upgraded=
   renderer.applyFullAiResult(
    record.opportunity,
    result
   );

  const saveResponse=
   await fetch(
    `/api/v1/organizations/${org}/shortlist`,
    {
     method:'POST',
     credentials:'same-origin',
     cache:'no-store',
     headers:{
      'Content-Type':'application/json'
     },
     body:JSON.stringify(
      upgraded
     )
    }
   );

  if(
   !savedRequestStillCurrent(
    index,
    scope,
    ticket,
    savedId,
    expectedOpportunity
   )
  ){
   return;
  }

  if(saveResponse.status===401){
   location.replace('/login');
   return;
  }

  if(saveResponse.status===403){
   if(statusNode){
    statusNode.textContent=
     'The analysis was stored, but this Saved Opportunity can no longer be updated.';
   }
   return;
  }

  if(saveResponse.status===409){
   if(statusNode){
    statusNode.textContent=
     'The active company changed before the Saved Opportunity could be refreshed.';
   }
   return;
  }

  if(!saveResponse.ok){
   if(statusNode){
    statusNode.textContent=
     'The analysis was stored, but the Saved Opportunity snapshot could not be refreshed.';
   }
   return;
  }

  const updatedRecord=
   await saveResponse.json();

  if(
   !savedRequestStillCurrent(
    index,
    scope,
    ticket,
    savedId,
    expectedOpportunity
   )
  ){
   return;
  }

  if(
   Number(updatedRecord?.id)
   !==savedId
  ){
   if(statusNode){
    statusNode.textContent=
     'The Saved Opportunity changed while analysis was running. Refresh Saved Opportunities.';
   }
   return;
  }

  records[index]=updatedRecord;

  render();
  renderSavedDetail(index);

  const nextStatus=$(
   `fullAiStatus-${index}`
  );

  if(nextStatus){
   nextStatus.textContent=
    result.duplicate
     ?'Existing stored document analysis was reused. No additional AI call was required.'
     :'Full AI analysis completed and the Saved Opportunity was refreshed.';
  }

 }catch(error){
  if(
   !savedRequestStillCurrent(
    index,
    scope,
    ticket,
    savedId,
    expectedOpportunity
   )
  ){
   return;
  }

  const currentStatus=$(
   `fullAiStatus-${index}`
  );

  if(currentStatus){
   currentStatus.textContent=
    'Network unavailable. The Saved Opportunity was not changed.';
  }

 }finally{
  if(button){
   button.disabled=false;
   button.textContent='Analyze tender PDF';
  }
 }
}

async function loadSaved(){
 const scope=identity();
 const ticket=++serial;

 updateContext();

 if(!usingSharedOrganization()){
  clearResults('Select or create a shared organization in Team to use Saved Opportunities.');
  return;
 }

 if(!Number.isInteger(state.activeCompanyId)){
  clearResults('Create and activate a company before using Saved Opportunities.');
  return;
 }

 const org=state.organizationId;

 $('savedMessage').textContent='Loading saved opportunities...';
 $('savedCount').textContent='Not loaded';
 $('savedResults').replaceChildren();

 try{
  const response=await fetch(
   `/api/v1/organizations/${org}/shortlist`,
   {
    credentials:'same-origin',
    cache:'no-store'
   }
  );

  if(ticket!==serial||scope!==identity())return;

  if(response.status===401){
   location.replace('/login');
   return;
  }

  if(response.status===403){
   clearResults('You do not have access to this organization shortlist.');
   return;
  }

  if(response.status===409){
   clearResults('Create and activate a company before using Saved Opportunities.');
   return;
  }

  if(!response.ok){
   clearResults('Saved opportunities are unavailable. Please retry.');
   return;
  }

  const payload=await response.json();

  if(ticket!==serial||scope!==identity())return;

  records=(Array.isArray(payload)?payload:[])
   .filter(
    record=>
     record?.opportunity&&
     Number.isInteger(Number(record.id))
   );

  render();
 }
 catch(error){
  if(ticket!==serial||scope!==identity())return;

  clearResults(
   'Network unavailable. Saved opportunities could not be loaded.'
  );
 }
}

function removalMessage(message){
 $('savedMessage').textContent=message;
 const status=$('savedDetailBody').querySelector('[data-shortlist-status]');
 if(status)status.textContent=message;
}

async function removeSaved(index,button){
 const record=records[index];
 const savedId=Number(record?.id);

 if(
  !record||
  !Number.isInteger(savedId)||
  !ready()
 ){
  return;
 }

 const scope=identity();
 const org=state.organizationId;

 if(button){
  button.disabled=true;
  button.textContent='Removing...';
 }

 try{
  const response=await fetch(
   `/api/v1/organizations/${org}/shortlist/${savedId}`,
   {
    method:'DELETE',
    credentials:'same-origin',
    cache:'no-store'
   }
  );

  if(scope!==identity())return;

  if(response.status===401){
   location.replace('/login');
   return;
  }

  if(!response.ok&&response.status!==404){
   if(button){
    button.disabled=false;
    button.textContent='Remove from saved';
   }

   removalMessage('This opportunity could not be removed. Please retry.');

   return;
  }

  records.splice(index,1);

  if($('savedDetail').open){
   $('savedDetail').close();
  }

  render();
 }
 catch(error){
  if(button&&scope===identity()){
   button.disabled=false;
   button.textContent='Remove from saved';
  }

  if(scope===identity()){
   removalMessage('Network unavailable. The saved opportunity was not changed.');
  }
 }
}

$('refreshSaved').onclick=loadSaved;

$('savedResults').onclick=event=>{
 const button=event.target.closest('[data-detail]');

 if(!button)return;

 openDetail(
  Number(button.dataset.detail)
 );
};

$('savedDetailBody').onclick=event=>{
 const analyze=event.target.closest(
  '[data-full-ai]'
 );

 if(analyze){
  analyzeSavedTenderPdf(
   Number(analyze.dataset.fullAi),
   analyze
  );
  return;
 }

 const remove=event.target.closest(
  '[data-remove]'
 );

 if(!remove)return;

 removeSaved(
  Number(remove.dataset.remove),
  remove
 );
};

$('closeSavedDetail').onclick=()=>{
 $('savedDetail').close();
};

window.addEventListener(
 'workspace-context',
 ()=>{
  const next=identity();

  if(context!==next){
   context=next;
   serial++;
   clearResults('Open Saved to load the active company shortlist.');

   if($('savedDetail').open){
    $('savedDetail').close();
   }
  }

  updateContext();

  if(currentPage()==='saved'){
   loadSaved();
  }
 }
);

updateContext();

if(currentPage()==='saved'){
 loadSaved();
}
})();
