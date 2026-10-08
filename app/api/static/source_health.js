/* Read-only procurement Source Health workspace. */
(function(){
'use strict';

const $=id=>document.getElementById(id);
const workspace=$('sourceHealthWorkspace');

if(!workspace)return;

let serial=0;
let context='';

const identity=()=>`${state.organizationId}:${state.activeCompanyId??''}:${state.uiEpoch||0}`;
const currentPage=()=>location.hash.slice(1)||'overview';

const escape=value=>String(value??'')
 .replaceAll('&','&amp;')
 .replaceAll('<','&lt;')
 .replaceAll('>','&gt;')
 .replaceAll('"','&quot;');

function safeUrl(value){
 try{
  const parsed=new URL(String(value||''));

  if(parsed.protocol!=='https:'){
   return null;
  }

  return parsed.href;
 }
 catch(error){
  return null;
 }
}

function ready(){
 return usingSharedOrganization()&&
  Number.isInteger(state.activeCompanyId);
}

function dateLabel(value){
 if(!value)return 'Not checked yet';

 const parsed=new Date(value);

 if(Number.isNaN(parsed.getTime())){
  return String(value);
 }

 return parsed.toLocaleString();
}

function stateLabel(value){
 const labels={
  healthy:'Healthy',
  failed:'Failed',
  disabled:'Disabled',
  not_checked:'Not checked'
 };

 return labels[value]||'Unknown';
}

function stateRank(value){
 const ranks={
  failed:0,
  healthy:1,
  disabled:2,
  not_checked:3
 };

 return ranks[value]??4;
}

function updateContext(){
 if(!usingSharedOrganization()){
  $('sourceHealthContext').textContent=
   'Select or create a shared organization in Team first.';
  return;
 }

 if(!Number.isInteger(state.activeCompanyId)){
  $('sourceHealthContext').textContent=
   'Create and activate a company in Companies first.';
  return;
 }

 $('sourceHealthContext').textContent=
  `Source status for ${state.activeCompanyName}`;
}

function zeroMetrics(){
 $('sourceHealthyCount').textContent='Not loaded';
 $('sourceFailedCount').textContent='Not loaded';
 $('sourceDisabledCount').textContent='Not loaded';
 $('sourceUncheckedCount').textContent='Not loaded';
}

function clear(message){
 serial++;
 zeroMetrics();
 $('sourceHealthResults').replaceChildren();
 $('sourceHealthLastChecked').textContent=
  'Source status has not been loaded for this workspace.';
 $('sourceHealthMessage').textContent=message;
}

function render(payload){
 const sources=Array.isArray(payload?.sources)
  ? [...payload.sources]
  : [];

 const counts={
  healthy:0,
  failed:0,
  disabled:0,
  not_checked:0
 };

 for(const source of sources){
  if(Object.hasOwn(counts,source?.state)){
   counts[source.state]++;
  }
 }

 $('sourceHealthyCount').textContent=
  String(counts.healthy);

 $('sourceFailedCount').textContent=
  String(counts.failed);

 $('sourceDisabledCount').textContent=
  String(counts.disabled);

 $('sourceUncheckedCount').textContent=
  String(counts.not_checked);

 $('sourceHealthLastChecked').textContent=
  payload?.last_checked
   ? `Last recorded Discovery check: ${dateLabel(payload.last_checked)}${payload.history_id?` | Discovery #${payload.history_id}`:''}`
   : 'No recorded Discovery check exists for this company yet.';

 sources.sort((a,b)=>{
  const stateDifference=
   stateRank(a?.state)-stateRank(b?.state);

  if(stateDifference)return stateDifference;

  return String(a?.display_name||a?.source||'')
   .localeCompare(
    String(b?.display_name||b?.source||'')
   );
 });

 $('sourceHealthResults').innerHTML=
  sources.map(source=>{
   const url=safeUrl(source.homepage_url);

   const notices=
    source.notice_count==null
     ? 'Not recorded'
     : String(source.notice_count);

   const latency=
    source.duration_ms==null
     ? 'Not recorded'
     : `${source.duration_ms} ms`;

   const jurisdictions=
    Array.isArray(source.jurisdictions)&&
    source.jurisdictions.length
     ? source.jurisdictions.join(', ')
     : 'Not specified';

   const languages=
    Array.isArray(source.languages)&&
    source.languages.length
     ? source.languages.join(', ')
     : 'Not specified';

   const configuration=
    source.enabled
     ? 'Enabled'
     : source.authentication_required
       ? 'Configuration required'
       : 'Disabled';

   const note=
    source.state==='failed'
     ? `
       <p class="fine">
         <strong>Latest check:</strong>
         Source could not be reached during the latest Discovery.
       </p>
      `
     : source.state==='disabled'
       ? `
         <p class="fine">
           ${
            source.authentication_required
             ? 'Source requires configuration before it can be checked.'
             : 'Source is disabled in configuration.'
           }
         </p>
        `
       : '';

   return `
    <article class="tender-card">
      <span class="chip">
        ${escape(stateLabel(source.state))}
      </span>

      <span class="chip">
        ${escape(String(source.transport||'unknown').toUpperCase())}
      </span>

      <h3>
        ${escape(source.display_name||source.source)}
      </h3>

      <p class="fine">
        Source key: ${escape(source.source)}
      </p>

      <div class="tender-meta">
        <span>
          Results returned: ${escape(notices)}
        </span>

        <span>
          Response time: ${escape(latency)}
        </span>

        <span>
          Jurisdiction: ${escape(jurisdictions)}
        </span>

        <span>
          Languages: ${escape(languages)}
        </span>

        <span>
          Configuration: ${escape(configuration)}
        </span>

        <span>
          ${source.official?'Official source':'Connector source'}
        </span>
      </div>

      ${note}

      ${
       url
        ? `<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">Open official source</a>`
        : ''
      }
    </article>
   `;
  }).join('');

 $('sourceHealthMessage').textContent=
  sources.length
   ? `Showing ${sources.length} configured procurement sources. Status comes from the latest recorded Discovery run and does not trigger a new source check.`
   : 'No procurement source metadata is available.';
}

async function loadSourceHealth(){
 const scope=identity();
 const ticket=++serial;

 updateContext();

 if(!usingSharedOrganization()){
  clear(
   'Select or create a shared organization in Team to use Source Health.'
  );
  return;
 }

 if(!Number.isInteger(state.activeCompanyId)){
  clear(
   'Create and activate a company before using Source Health.'
  );
  return;
 }

 const org=state.organizationId;

 $('sourceHealthMessage').textContent=
  'Loading the latest recorded source status...';
 zeroMetrics();

 try{
  const response=await fetch(
   `/api/v1/organizations/${org}/discovery/source-health`,
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
   clear(
    'You do not have access to Source Health for this organization.'
   );
   return;
  }

  if(response.status===409){
   clear(
    'Create and activate a company before using Source Health.'
   );
   return;
  }

  if(!response.ok){
   clear(
    'Source Health is unavailable. Please retry.'
   );
   return;
  }

  const payload=await response.json();

  if(ticket!==serial||scope!==identity())return;

  render(payload);
 }
 catch(error){
  if(ticket!==serial||scope!==identity())return;

  clear(
   'Network unavailable. Source Health could not be loaded.'
  );
 }
}

$('refreshSourceHealth').onclick=
 loadSourceHealth;

window.addEventListener(
 'workspace-context',
 ()=>{
  const next=identity();

  if(context!==next){
   context=next;
   serial++;
   zeroMetrics();
   $('sourceHealthResults').replaceChildren();
   $('sourceHealthLastChecked').textContent='Source status has not been loaded for this workspace.';
  }

  updateContext();

  if(currentPage()==='source-health'){
   loadSourceHealth();
  }
 }
);

updateContext();

if(currentPage()==='source-health'){
 loadSourceHealth();
}
})();
