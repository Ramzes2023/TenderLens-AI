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
let pendingPlannerId=null;
let pendingPlannerScope=null;

const identity=()=>`${state.organizationId}:${state.activeCompanyId??''}:${state.uiEpoch||0}`;
const currentPage=()=>location.hash.slice(1)||'overview';

function ready(){
 return usingSharedOrganization()&&Number.isInteger(state.activeCompanyId);
}

function refreshExportLinks(){
 const canExport=usingSharedOrganization()&&Number.isInteger(state.activeCompanyId);
 for(const format of ['csv','xlsx']){
  const anchor=$('exportSaved'+(format==='csv'?'Csv':'Xlsx'));
  if(!anchor)continue;
  anchor.hidden=!canExport;
  if(canExport){
   anchor.href='/api/v1/organizations/'+encodeURIComponent(state.organizationId)+'/shortlist/export?format='+format;
  }else anchor.removeAttribute('href');
 }
}

let deadlinePreferenceTicket=0;
async function loadDeadlinePreferences(){
 const ticket=++deadlinePreferenceTicket;
 const org=state.organizationId,scope=identity();
 const save=$('saveDeadlinePreferences');
 if(!save)return;
 save.disabled=true;
 for(const id of ['deadlineEmailOptin','deadlineTelegramOptin'])$(id).checked=false;
 if(!usingSharedOrganization()||!Number.isInteger(state.activeCompanyId)){
  $('deadlinePreferencesStatus').textContent='Activate a shared company to set reminders.';
  return;
 }
 $('deadlinePreferencesStatus').textContent='Loading your reminder preferences...';
 try{
  const response=await fetch('/api/v1/organizations/'+encodeURIComponent(org)+'/deadline-alerts/preferences',
   {credentials:'same-origin',cache:'no-store'});
  if(ticket!==deadlinePreferenceTicket||scope!==identity())return;
  if(!response.ok)throw Error('unavailable');
  const data=await response.json();
  $('deadlineEmailOptin').checked=!!data.email_enabled;
  $('deadlineTelegramOptin').checked=!!data.telegram_enabled;
  save.disabled=false;
  $('deadlinePreferencesStatus').textContent='Reminders are optional and only sent for saved opportunities.';
 }catch(error){
  if(ticket===deadlinePreferenceTicket&&scope===identity())
   $('deadlinePreferencesStatus').textContent='Could not load preferences. No changes were made.';
 }
}
async function saveDeadlinePreferences(){
 if(!usingSharedOrganization()||!Number.isInteger(state.activeCompanyId))return;
 const scope=identity(),org=state.organizationId;
 const save=$('saveDeadlinePreferences');
 save.disabled=true;
 $('deadlinePreferencesStatus').textContent='Saving preferences...';
 try{
  const response=await fetch('/api/v1/organizations/'+encodeURIComponent(org)+'/deadline-alerts/preferences',{
   method:'PUT',credentials:'same-origin',cache:'no-store',
   headers:{'Content-Type':'application/json'},
   body:JSON.stringify({
    email_enabled:$('deadlineEmailOptin').checked,
    telegram_enabled:$('deadlineTelegramOptin').checked
   })
  });
  if(scope!==identity())return;
  if(!response.ok)throw Error('unavailable');
  $('deadlinePreferencesStatus').textContent='Deadline reminder preferences saved.';
 }catch(error){
  if(scope===identity())$('deadlinePreferencesStatus').textContent='Preferences were not saved. Please retry.';
 }finally{
  if(scope===identity())save.disabled=false;
 }
}
$('saveDeadlinePreferences').onclick=saveDeadlinePreferences;


let activitySerial=0;
const activityLabels={
 tender_saved:'Saved tender',
 tender_refreshed:'Updated saved tender',
 tender_removed:'Removed saved tender',
 export_csv_generated:'Generated CSV export',
 export_xlsx_generated:'Generated Excel export'
};
async function loadSavedActivity(){
 const scope=identity(),ticket=++activitySerial;
 const root=$('savedActivityEvents');
 root.replaceChildren();
 if(!ready()){
  $('savedActivityStatus').textContent='Activate a shared company to view activity.';
  return;
 }
 $('savedActivityStatus').textContent='Loading team activity…';
 try{
  const response=await fetch(
   '/api/v1/organizations/'+encodeURIComponent(state.organizationId)+'/activity',
   {credentials:'same-origin',cache:'no-store'}
  );
  if(ticket!==activitySerial||scope!==identity())return;
  if(response.status===401){location.replace('/login');return;}
  if(response.status===403){
   $('savedActivityStatus').textContent='Only organization owners and admins can view this history.';
   return;
  }
  if(!response.ok){
   $('savedActivityStatus').textContent='Company activity unavailable. Retry.';
   return;
  }
  const data=await response.json();
  if(ticket!==activitySerial||scope!==identity())return;
  const events=Array.isArray(data.events)?data.events:[];
  for(const event of events){
   if(!Object.hasOwn(activityLabels,event.action))continue;
   const line=document.createElement('li');
   line.textContent=activityLabels[event.action]+
    ' · Account #'+Number(event.actor_account_id)+
    (Number.isInteger(event.saved_opportunity_id)
      ?' · saved #'+event.saved_opportunity_id:'')+
    (Number.isInteger(event.item_count)?' · '+event.item_count+' rows':'')+
    ' · '+String(event.created_at||'');
   root.append(line);
  }
  $('savedActivityStatus').textContent=events.length?
   'Last '+events.length+' recorded company actions.':'No recorded activity for this company yet.';
 }catch(error){
  if(ticket===activitySerial&&scope===identity())
   $('savedActivityStatus').textContent='Network unavailable. Retry.';
 }
}
$('refreshSavedActivity').onclick=loadSavedActivity;

function updateContext(){
 refreshExportLinks();
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


let workflowSerial=0;
let workflowRevision=0;
let workflowRecord=null;
const workflowStages=['new','reviewing','preparing','submitted','won','lost','archived'];
const workflowUrl=id=>'/api/v1/organizations/'+encodeURIComponent(state.organizationId)+
 '/shortlist/'+encodeURIComponent(id)+'/workflow';
function workflowValid(ticket,scope,id){
 return ticket===workflowSerial&&scope===identity()&&
        Number(workflowRecord?.id)===id&&$('savedDetail').open;
}
async function loadWorkflowEvents(ticket,scope,id){
 try{
  const res=await fetch(workflowUrl(id)+'/events',{credentials:'same-origin',cache:'no-store'});
  if(!res.ok||!workflowValid(ticket,scope,id))return;
  const events=await res.json();
  if(!workflowValid(ticket,scope,id))return;
  const root=$('savedWorkflowEvents');root.replaceChildren();
  for(const item of Array.isArray(events)?events.slice(0,20):[]){
   const li=document.createElement('li');
   li.textContent='Account #'+Number(item.actor_account_id)+': '+
    String(item.previous_stage||'new')+' → '+String(item.next_stage||'new')+
    (item.note_changed?' · note edited':'')+' · '+String(item.changed_at||'');
   root.appendChild(li);
  }
  if(!root.childElementCount){
   const empty=document.createElement('li');
   empty.textContent='No changes yet.';
   root.appendChild(empty);
  }
 }catch(error){/* The saved workflow remains available even if audit read fails. */}
}
async function loadWorkflow(index){
 const node=$('savedWorkflowPanel');
 if(!node)return;
 const record=records[index],id=Number(record?.id),scope=identity();
 const ticket=++workflowSerial;
 workflowRecord=record;
 workflowRevision=0;
 node.hidden=false;
 $('savedWorkflowStatus').textContent='Loading team workflow…';
 $('saveSavedWorkflow').disabled=true;
 $('savedWorkflowNote').value='';
 $('savedWorkflowStage').value='new';
 $('savedWorkflowEvents').replaceChildren();
 if(!ready()||!Number.isInteger(id))return;
 try{
  const res=await fetch(workflowUrl(id),{credentials:'same-origin',cache:'no-store'});
  if(!workflowValid(ticket,scope,id))return;
  if(res.status===401){location.replace('/login');return;}
  if(!res.ok){
   $('savedWorkflowStatus').textContent='Workflow unavailable; please retry.';
   return;
  }
  const data=await res.json();
  if(!workflowValid(ticket,scope,id))return;
  workflowRevision=Number(data.revision);
  $('savedWorkflowStage').value=workflowStages.includes(data.stage)?data.stage:'new';
  $('savedWorkflowNote').value=String(data.note||'').slice(0,2000);
  const writable=canWriteWorkspace();
  $('savedWorkflowStage').disabled=!writable;
  $('savedWorkflowNote').disabled=!writable;
  $('saveSavedWorkflow').disabled=!writable;
  $('savedWorkflowStatus').textContent=writable?
   'Team-only details. Conflicting edits are rejected.':'Read-only access.';
  await loadWorkflowEvents(ticket,scope,id);
 }catch(error){
  if(workflowValid(ticket,scope,id))
   $('savedWorkflowStatus').textContent='Network unavailable; please retry.';
 }
}
$('saveSavedWorkflow').onclick=async()=>{
 const record=workflowRecord,id=Number(record?.id),scope=identity(),ticket=workflowSerial;
 if(!ready()||!canWriteWorkspace()||!Number.isInteger(id)||!workflowValid(ticket,scope,id))return;
 const stage=$('savedWorkflowStage').value,note=$('savedWorkflowNote').value;
 if(!workflowStages.includes(stage)||note.length>2000)return;
 const button=$('saveSavedWorkflow');button.disabled=true;
 $('savedWorkflowStatus').textContent='Saving…';
 try{
  const res=await fetch(workflowUrl(id),{
   method:'PATCH',credentials:'same-origin',cache:'no-store',
   headers:{'Content-Type':'application/json'},
   body:JSON.stringify({stage,note,expected_revision:workflowRevision})
  });
  if(!workflowValid(ticket,scope,id))return;
  if(res.status===409){
   $('savedWorkflowStatus').textContent='Another team member updated this tender. Close and reopen to reload.';
   return;
  }
  if(!res.ok){
   $('savedWorkflowStatus').textContent='Not saved. Check access and retry.';
   return;
  }
  const data=await res.json();
  if(!workflowValid(ticket,scope,id))return;
  workflowRevision=Number(data.revision);
  $('savedWorkflowStatus').textContent='Status and note saved.';
  await loadWorkflowEvents(ticket,scope,id);
 }catch(error){
  if(workflowValid(ticket,scope,id))
   $('savedWorkflowStatus').textContent='Network unavailable. Not saved.';
 }finally{
  if(workflowValid(ticket,scope,id)&&
     !$('savedWorkflowStatus').textContent.startsWith('Another team member'))
   button.disabled=false;
 }
};

function openDetail(index){
 const record=records[index];

 if(!record?.opportunity||!renderer)return;

 $('savedDetailTitle').textContent=
  record.opportunity.title||'Saved opportunity';

 renderSavedDetail(index);

 if(!$('savedDetail').open){
  $('savedDetail').showModal();
 }
 loadWorkflow(index);
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
  if(pendingPlannerId!==null&&currentPage()==='saved'){
   const index=records.findIndex(record=>Number(record.id)===pendingPlannerId);
   pendingPlannerId=null;
   pendingPlannerScope=null;
   if(index>=0)openDetail(index);
   else $('savedMessage').textContent='That tender is not in the active company shortlist.';
  }
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
  workflowSerial++;

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
 workflowSerial++;
 $('savedDetail').close();
};
$('savedDetail').addEventListener('close',()=>{workflowSerial++;});

window.addEventListener('valyqon-open-saved',event=>{
 const item=event.detail;
 if(!item||!Number.isInteger(item.id)||item.id<=0||
    item.organizationId!==state.organizationId||
    item.companyId!==state.activeCompanyId)return;
 pendingPlannerId=item.id;
 pendingPlannerScope=identity();
 if(currentPage()==='saved')loadSaved();
});
window.addEventListener(
 'workspace-context',
 ()=>{
  const next=identity();

  if(context!==next){
   context=next;
   if(pendingPlannerScope!==next){
    pendingPlannerId=null;
    pendingPlannerScope=null;
   }
   serial++;
   clearResults('Open Saved to load the active company shortlist.');
   workflowSerial++;

   if($('savedDetail').open){
    $('savedDetail').close();
   }
  }

  updateContext();
  loadDeadlinePreferences();
  loadSavedActivity();

  if(currentPage()==='saved'){
   loadSaved();
  }
 }
);

updateContext();
loadDeadlinePreferences();
loadSavedActivity();

if(currentPage()==='saved'){
 loadSaved();
}
})();
