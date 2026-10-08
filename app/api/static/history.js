/* Active-company Discovery Search History workspace. */
(function(){
'use strict';

const $=id=>document.getElementById(id);
const workspace=$('historyWorkspace');

if(!workspace)return;

const renderer=window.ValyqonDiscovery;

let records=[];
let snapshotItems=[];
let serial=0;
let detailSerial=0;
let context='';

const identity=()=>`${state.organizationId}:${state.activeCompanyId??''}:${state.uiEpoch||0}`;
const currentPage=()=>location.hash.slice(1)||'overview';

const escape=value=>String(value??'')
 .replaceAll('&','&amp;')
 .replaceAll('<','&lt;')
 .replaceAll('>','&gt;')
 .replaceAll('"','&quot;');

function ready(){
 return usingSharedOrganization()&&
  Number.isInteger(state.activeCompanyId);
}

function dateLabel(value){
 const parsed=new Date(value);

 if(Number.isNaN(parsed.getTime())){
  return String(value||'Unknown time');
 }

 return parsed.toLocaleString();
}

function sourceText(values){
 return Array.isArray(values)&&values.length
  ? values.join(', ')
  : 'none';
}

function updateContext(){
 if(!usingSharedOrganization()){
  $('historyContext').textContent=
   'Select or create a shared organization in Team first.';
  return;
 }

 if(!Number.isInteger(state.activeCompanyId)){
  $('historyContext').textContent=
   'Create and activate a company in Companies first.';
  return;
 }

 $('historyContext').textContent=
  `Search history for ${state.activeCompanyName}`;
}

function closeTender(){
 if($('historyTenderDetail').open){
  $('historyTenderDetail').close();
 }
}

function closeSnapshot(){
 detailSerial++;
 snapshotItems=[];
 $('historySnapshot').hidden=true;
 $('historySnapshotResults').replaceChildren();
 $('historySnapshotMeta').textContent='';
 closeTender();
}

function clearHistory(message){
 records=[];
 $('historyCount').textContent='Not loaded';
 $('historyRuns').replaceChildren();
 $('historyMessage').textContent=message;
 closeSnapshot();
}

function renderHistory(){
 $('historyCount').textContent=
  String(records.length);

 $('historyRuns').innerHTML=
  records.map(record=>{
   const status=record.total_failure
    ? 'Source failure'
    : record.partial_failure
      ? 'Partial source coverage'
      : 'Completed';

   return `
    <article class="tender-card">
      <span class="chip">
        ${escape(status)}
      </span>

      <h3>
        Discovery #${escape(record.id)}
      </h3>

      <div class="tender-meta">
        <span>
          Run: ${escape(dateLabel(record.created_at))}
        </span>

        <span>
          Opportunities: ${escape(record.result_count)}
        </span>

        <span>
          Metadata scored: ${escape(record.scored_count)}
        </span>
      </div>

      <p>
        Attempted: ${escape(sourceText(record.attempted_sources))}
      </p>

      <p class="fine">
        Reached: ${escape(sourceText(record.successful_sources))}
        | Unavailable: ${escape(sourceText(record.failed_sources))}
      </p>

      <button
        type="button"
        data-history-open="${escape(record.id)}"
      >
        Open results
      </button>
    </article>
   `;
  }).join('');

 $('historyMessage').textContent=
  records.length
   ? `Showing ${records.length} previous ${records.length===1?'search':'searches'} for ${state.activeCompanyName}.`
   : 'No Discovery history exists for this company yet.';
}

async function loadHistory(){
 const scope=identity();
 const ticket=++serial;

 updateContext();
 closeSnapshot();

 if(!usingSharedOrganization()){
  clearHistory(
   'Select or create a shared organization in Team to use Search History.'
  );
  return;
 }

 if(!Number.isInteger(state.activeCompanyId)){
  clearHistory(
   'Create and activate a company before using Search History.'
  );
  return;
 }

 const org=state.organizationId;

 $('historyMessage').textContent=
  'Loading previous Discovery runs...';
 $('historyCount').textContent='Not loaded';

 $('historyRuns').replaceChildren();

 try{
  const response=await fetch(
   `/api/v1/organizations/${org}/discovery/history?limit=50`,
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
   clearHistory(
    'You do not have access to this organization Search History.'
   );
   return;
  }

  if(response.status===409){
   clearHistory(
    'Create and activate a company before using Search History.'
   );
   return;
  }

  if(!response.ok){
   clearHistory(
    'Search History is unavailable. Please retry.'
   );
   return;
  }

  const payload=await response.json();

  if(ticket!==serial||scope!==identity())return;

  records=(Array.isArray(payload)?payload:[])
   .filter(
    record=>
     Number.isInteger(Number(record?.id))
   );

  renderHistory();
 }
 catch(error){
  if(ticket!==serial||scope!==identity())return;

  clearHistory(
   'Network unavailable. Search History could not be loaded.'
  );
 }
}

async function openHistory(historyId){
 if(!ready())return;

 const id=Number(historyId);

 if(!Number.isInteger(id)||id<=0)return;

 const scope=identity();
 const ticket=++detailSerial;
 const org=state.organizationId;

 $('historyMessage').textContent=
  `Opening Discovery #${id} from saved history...`;

 try{
  const response=await fetch(
   `/api/v1/organizations/${org}/discovery/history/${id}`,
   {
    credentials:'same-origin',
    cache:'no-store'
   }
  );

  if(
   ticket!==detailSerial||
   scope!==identity()
  )return;

  if(response.status===401){
   location.replace('/login');
   return;
  }

  if(response.status===403){
   $('historyMessage').textContent=
    'You do not have access to this historical search.';
   return;
  }

  if(response.status===404){
   $('historyMessage').textContent=
    'This historical search is not available for the active company.';
   return;
  }

  if(!response.ok){
   $('historyMessage').textContent=
    'Historical results are unavailable. Please retry.';
   return;
  }

  const payload=await response.json();

  if(
   ticket!==detailSerial||
   scope!==identity()
  )return;

  const discovery=payload?.discovery||{};

  snapshotItems=
   discovery.total_failure
    ? []
    : Array.isArray(discovery.items)
      ? discovery.items
      : [];

  $('historySnapshotTitle').textContent=
   `Discovery #${id} - ${dateLabel(payload.created_at)}`;

  $('historySnapshotMeta').textContent=
   `Opportunities: ${payload.result_count} | Metadata scored: ${payload.scored_count} | Attempted: ${sourceText(payload.attempted_sources)} | Reached: ${sourceText(payload.successful_sources)} | Unavailable: ${sourceText(payload.failed_sources)}`;

  $('historySnapshotResults').innerHTML=
   renderer
    ? snapshotItems
       .map(
        (item,index)=>
         renderer.card(
          item,
          index
         )
       )
       .join('')
    : '';

  $('historySnapshot').hidden=false;

  $('historyMessage').textContent=
   snapshotItems.length
    ? `Loaded ${snapshotItems.length} results from saved Discovery history. No procurement sources were queried.`
    : 'This historical Discovery run contains no available results.';

  $('historySnapshot').scrollIntoView({
   block:'start'
  });
 }
 catch(error){
  if(
   ticket!==detailSerial||
   scope!==identity()
  )return;

  $('historyMessage').textContent=
   'Network unavailable. Historical results could not be loaded.';
 }
}

function openTender(index){
 const item=snapshotItems[index];

 if(!item||!renderer)return;

 $('historyTenderDetailTitle').textContent=
  item.title||'Historical opportunity';

 $('historyTenderDetailBody').innerHTML=
  renderer.detail(item);

 if(!$('historyTenderDetail').open){
  $('historyTenderDetail').showModal();
 }
}

$('refreshHistory').onclick=loadHistory;

$('historyRuns').onclick=event=>{
 const button=event.target.closest(
  '[data-history-open]'
 );

 if(!button)return;

 openHistory(
  button.dataset.historyOpen
 );
};

$('historySnapshotResults').onclick=event=>{
 const button=event.target.closest(
  '[data-detail]'
 );

 if(!button)return;

 openTender(
  Number(button.dataset.detail)
 );
};

$('closeHistorySnapshot').onclick=
 closeSnapshot;

$('closeHistoryTenderDetail').onclick=
 closeTender;

window.addEventListener(
 'workspace-context',
 ()=>{
  const next=identity();

  if(context!==next){
   context=next;
   serial++;
   detailSerial++;
   clearHistory('Open Search History to load previous Discovery runs.');
  }

  updateContext();

  if(currentPage()==='search-history'){
   loadHistory();
  }
 }
);

updateContext();

if(currentPage()==='search-history'){
 loadHistory();
}
})();
