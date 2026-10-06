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
 $('savedCount').textContent='0';
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

function openDetail(index){
 const record=records[index];

 if(!record?.opportunity||!renderer)return;

 $('savedDetailTitle').textContent=
  record.opportunity.title||'Saved opportunity';

 $('savedDetailBody').innerHTML=
  renderer.detail(
   record.opportunity,
   record,
   index
  );

 if(!$('savedDetail').open){
  $('savedDetail').showModal();
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

 $('savedMessage').textContent='Loading saved opportunities?';
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
  button.textContent='Removing?';
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

   $('savedMessage').textContent=
    'This opportunity could not be removed. Please retry.';

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
   $('savedMessage').textContent=
    'Network unavailable. The saved opportunity was not changed.';
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
 const remove=event.target.closest('[data-remove]');

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
   records=[];

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
