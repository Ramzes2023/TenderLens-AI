/* Pure rendering/filtering contracts are also exercised by Node regression tests. */
(function(root){
'use strict';
const escape=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const percent=v=>typeof v==='number'&&Number.isFinite(v)?`${v}%`:'Not enough data';
function safeUrl(value){try{const u=new URL(value);const secret=[...u.searchParams.keys()].some(k=>['api_key','apikey','token','access_token','password','secret'].includes(k.toLowerCase()));return u.protocol==='https:'&&!u.username&&!u.password&&!secret&&(!u.port||u.port==='443')?u.href:null;}catch{return null;}}
// Exact official hosts from the existing source catalog; unknown hosts fail closed.
const officialHosts={world_bank:['projects.worldbank.org'],ted:['ted.europa.eu'],uk_fts:['www.find-tender.service.gov.uk'],sam_gov:['sam.gov'],eis:['zakupki.gov.ru'],canada_buys:['canadabuys.canada.ca'],austender:['www.tenders.gov.au'],nz_gets:['www.gets.govt.nz'],za_etenders:['www.etenders.gov.za'],india_cppp:['eprocure.gov.in'],kz_goszakup:['goszakup.gov.kz']};
function officialUrl(item){const url=safeUrl(item?.url);return url&&officialHosts[item.source]?.includes(new URL(url).hostname)?url:null;}
const bilingual=(en,ru)=>`data-ui-en="${escape(en)}" data-ui-ru="${escape(ru)}"`;
const internationalNamesRu={ted:'Европейский союз — TED',uk_fts:'Великобритания — Find a Tender',world_bank:'Группа Всемирного банка — Finances One'};
const internationalStates={healthy:['Healthy','Работает'],failed:['Failed','Ошибка'],disabled:['Disabled','Отключён'],not_checked:['Not checked','Не проверен']};
function internationalState(s){const labels=internationalStates[s.state];return internationalNamesRu[s.source]&&labels?`<span ${bilingual(...labels)}>${escape(labels[0])}</span>`:escape(s.state||'not_checked');}
function decisionHtml(item){
 const s=item.full_ai_analyzed&&item.full_scoring?item.full_scoring:(item.preliminary_scoring||{});
 const criteria=Array.isArray(s.criteria)?s.criteria:[];
 const reasons=criteria.filter(c=>c?.explanation).map(c=>`${c.label||c.code||'Criterion'}: ${c.explanation}`);
 const evidence=[...new Set(criteria.flatMap(c=>Array.isArray(c?.evidence)?c.evidence:[]))];
 const risks=Array.isArray(s.document_risks)?s.document_risks:[];
 const currency=item.full_ai_analyzed&&item.full_analysis?item.full_analysis.currency:item.currency;
 const unknowns=[...new Set([
  ...(Array.isArray(s.missing_information)?s.missing_information:[]),
  ...criteria.filter(c=>c?.status==='not_scored'&&c?.explanation)
   .map(c=>`${c.label||c.code||'Criterion'}: ${c.explanation}`)
 ])];
 return `<section class="discovery-decision"><h4 ${bilingual('Score reasons','Причины оценки')}>Score reasons</h4>${list(reasons)}<h4 ${bilingual('Score evidence','Основания оценки')}>Score evidence</h4>${list(evidence)}<h4 ${bilingual('Document risks','Риски документа')}>Document risks</h4>${list(risks)}<p class="fine" ${bilingual('Currency and budget: amounts are not converted. Confirm the notice currency against your company budget before deciding.','Валюта и бюджет: суммы не конвертируются. Проверьте валюту закупки и бюджет компании перед решением.')}>Currency and budget: amounts are not converted. Confirm the notice currency against your company budget before deciding.</p><p>${escape(currency||'Currency not provided; budget compatibility is unknown.')}</p><h4 ${bilingual('Stop factors','Стоп-факторы')}>Stop factors</h4>${Array.isArray(s.stop_factors)&&s.stop_factors.length?list(s.stop_factors):`<p ${bilingual("No stop factors reported in available data; eligibility is not confirmed.","В доступных данных стоп-факторы не указаны; допуск к участию не подтверждён.")}>No stop factors reported in available data; eligibility is not confirmed.</p>`}<h4 ${bilingual('Unknowns to verify','Что нужно уточнить')}>Unknowns to verify</h4>${unknowns.length?list(unknowns):`<p ${bilingual("No missing-information list supplied. Verify the official documents.","Список неизвестных данных не предоставлен. Проверьте официальные документы.")}>No missing-information list supplied. Verify the official documents.</p>`}</section>`;
}
function sourceOutcomes(report){return (Array.isArray(report?.source_statuses)?report.source_statuses:[]).map(s=>`<article class="discovery-source"><strong ${internationalNamesRu[s.source]?bilingual(s.display_name||s.source,internationalNamesRu[s.source]):''}>${escape(s.display_name||s.source)}</strong><p>${internationalState(s)} · ${s.notice_count==null?'Count unavailable':escape(s.notice_count)+' notices'}${s.authentication_required?' · Authentication required':''}</p><p>${escape(s.diagnostic||s.message||s.error_type||'No additional source information supplied.')}</p>${s.coverage?`<p>${escape(s.coverage)}</p>`:''}${s.last_successful_sync?`<p>Last successful sync: ${escape(s.last_successful_sync)}</p>`:''}</article>`).join('');}
function matches(item,f){
 const score=item.full_ai_analyzed&&item.full_scoring?item.full_scoring:(item.preliminary_scoring||{}), text=[item.title,item.summary,item.metadata_analysis?.procurement_object].filter(Boolean).join(' ').toLowerCase();
 if(f.keyword&&!text.includes(f.keyword.toLowerCase()))return false;
 if(f.source&&item.source!==f.source)return false;
 if(f.buyer&&!String(item.customer||'').toLowerCase().includes(f.buyer.toLowerCase()))return false;
 if(f.currency&&item.currency!==f.currency)return false;
 if(f.value!==''&&f.currency&&(!Number.isFinite(Number(f.value))||typeof item.initial_price!=='number'||!Number.isFinite(item.initial_price)||item.initial_price<Number(f.value)))return false;
 if(f.fit!==''&&(!Number.isFinite(Number(f.fit))||typeof score.fit_score!=='number'||!Number.isFinite(score.fit_score)||score.fit_score<Number(f.fit)))return false;
 if(f.deadline&&(!item.deadline||!Number.isFinite(Date.parse(item.deadline))||Date.parse(item.deadline)>Date.parse(f.deadline+'T23:59:59Z')))return false;
 if(f.published&&(!item.published_at||!Number.isFinite(Date.parse(item.published_at))||Date.parse(item.published_at)<Date.parse(f.published)))return false;
 return true;
}
function matchHtml(item){
 const full=Boolean(item?.full_ai_analyzed&&item?.full_scoring);
 const s=full?item.full_scoring:(item.preliminary_scoring||{});
 const label=full?'Full Document Match':'Preliminary Match';
 const note=full
  ?'Company fit recalculated from the uploaded tender document. Fit is not a probability of winning.'
  :'Company fit from available metadata. Review full documents before deciding. Fit is not a probability of winning.';
 return `<div class="match-block"><strong>${escape(label)}: ${escape(percent(s.fit_score))}</strong><br>Data completeness ${escape(percent(s.completeness_percent))}<p class="fine">${escape(note)}</p></div>`;
}
function cardShortlistControl(index,savedRecord,enabled){if(!enabled)return '';return savedRecord?'<button type="button" disabled aria-disabled="true">Saved</button>':`<button type="button" data-save="${index}">Save opportunity</button>`;}
function detailShortlistControl(index,savedRecord,enabled){if(!enabled)return '';return savedRecord?`<button type="button" data-remove="${index}">Remove from saved</button>`:`<button type="button" data-save="${index}">Save opportunity</button>`;}
function card(item,index,savedRecord){const shortlist=cardShortlistControl(index,savedRecord,arguments.length>=3);return `<article class="tender-card"><span class="chip">${escape(item.source)}</span> <span class="chip">${item.full_ai_analyzed?'Document analysis available':'Metadata preview'}</span><h3>${escape(item.title||'Untitled notice')}</h3><div class="tender-meta"><span>Buyer: ${escape(item.customer||'Not provided')}</span><span>Number: ${escape(item.tender_number||item.external_id||'Not provided')}</span><span>Value: ${escape(item.initial_price??'Not provided')} ${escape(item.currency||'')}</span><span>Region: ${escape(item.region||'Not provided')}</span><span>Deadline: ${escape(item.deadline||'Not provided')}</span><span>Published: ${escape(item.published_at||'Not provided')}</span></div><p>${escape((item.summary||item.metadata_analysis?.procurement_object||'No summary supplied.').slice(0,500))}</p>${matchHtml(item)}${decisionHtml(item)}${officialUrl(item)?`<a href="${escape(officialUrl(item))}" target="_blank" rel="noopener noreferrer" ${bilingual("Open official source","Открыть официальный источник")}>Open official source</a>`:""}<button data-detail="${index}">Open tender workspace</button>${shortlist}</article>`;}
const list=values=>Array.isArray(values)&&values.length?'<ul>'+values.map(v=>`<li>${escape(v)}</li>`).join('')+'</ul>':'<p>Not provided.</p>';

function fullAiControl(item,index,enabled){
 if(!enabled)return '';

 const already=Boolean(item?.full_ai_analyzed);

 return `
  <section class="match-block">
   <h3>${already?'Re-analyze tender document':'Full AI document analysis'}</h3>

   <p class="fine">
    Upload the authoritative tender PDF. VALYQON will use the existing
    document analysis workflow and recalculate company fit.
    Uploading a PDF does not submit a bid or change the tender source.
   </p>

   <input
    id="fullAiFile-${index}"
    data-full-ai-file="${index}"
    type="file"
    aria-label="Tender PDF for full AI analysis"
    accept=".pdf,application/pdf">

   <button
    type="button"
    data-full-ai="${index}">
    ${already?'Analyze another PDF':'Analyze tender PDF'}
   </button>

   <p
    id="fullAiStatus-${index}"
    class="fine"
    role="status"
    aria-live="polite"></p>
  </section>
 `;
}

function fullAnalysisMeta(item){
 if(!item?.full_ai_analyzed)return '';

 const warning=(item.full_analysis_warnings||[])
  .map(value=>`<li>${escape(value)}</li>`)
  .join('');

 return `
  <section>
   <h3>Full document analysis</h3>

   <dl>
    <dt>Document</dt>
    <dd>${escape(item.full_analysis_source_filename||'Uploaded tender PDF')}</dd>

    <dt>Stored analysis</dt>
    <dd>${item.full_analysis_record_id?`#${escape(item.full_analysis_record_id)}`:'Available'}</dd>

    <dt>Extraction</dt>
    <dd>${item.full_analysis_truncated?'Bounded / truncated':'Complete within configured analysis limit'}</dd>
   </dl>

   ${warning?`<h4>Analysis warnings</h4><ul>${warning}</ul>`:''}
  </section>
 `;
}

function applyFullAiResult(item,result){
 if(
  !item
  ||!result
  ||!result.analysis
 ){
  return item;
 }

 return {
  ...item,
  analysis_stage:'full_ai_document',
  full_ai_analyzed:true,
  full_analysis:result.analysis,
  full_scoring:result.scoring||null,
  full_analysis_record_id:
   Number.isInteger(Number(result.record_id))
    ?Number(result.record_id)
    :null,
  full_analysis_pdf_sha256:
   result.pdf_sha256||null,
  full_analysis_source_filename:
   result.source_filename||null,
  full_analysis_truncated:
   Boolean(result.analysis_truncated),
  full_analysis_warnings:
   Array.isArray(result.warnings)
    ?result.warnings
    :[]
 };
}

function detail(item,savedRecord,index,fullAiEnabled){
 const score=(
  item.full_ai_analyzed&&item.full_scoring
 )
  ?item.full_scoring
  :(item.preliminary_scoring||{});

 const a=(
  item.full_ai_analyzed&&item.full_analysis
 )
  ?item.full_analysis
  :(item.metadata_analysis||{});

 const url=officialUrl(item);

 const shortlist=detailShortlistControl(
  index,
  savedRecord,
  arguments.length>=3&&fullAiEnabled!==false
 );

 const requirementsLabel=
  item.full_ai_analyzed
   ?'Requirements from analyzed document'
   :'Requirements available in metadata';

 const documentsLabel=
  item.full_ai_analyzed
   ?'Required documents'
   :'Document requirements in metadata';

 return `
  <section>
   <h3>Overview</h3>

   <dl>
    ${
     [
      ['Source',item.source],
      ['Buyer',item.customer],
      ['Tender number',item.tender_number],
      ['Region',item.region],
      ['Deadline',item.deadline],
      ['Published',item.published_at],
      [
       'Value',
       item.initial_price==null
        ?null
        :`${item.initial_price} ${item.currency||''}`
      ]
     ]
      .map(
       ([k,v])=>
        `<dt>${escape(k)}</dt><dd>${escape(v??'Not provided')}</dd>`
      )
      .join('')
    }
   </dl>

   <p>
    ${escape(
     item.summary
     ||a.procurement_object
     ||'No summary supplied.'
    )}
   </p>
  </section>

  ${fullAnalysisMeta(item)}
  ${decisionHtml(item)}

  <div class="detail-grid">
   <section>
    <h3>Company Match</h3>

    ${matchHtml(item)}

    ${
     (score.criteria||[])
      .map(
       c=>`
        <div class="criterion">
         <strong>${escape(c.label||c.code)}</strong>
         <p>
          Status:
          ${escape(
           c.status==='not_scored'
            ?'Missing data — not scored'
            :c.status
          )}
         </p>
         <p>
          Points:
          ${escape(c.earned_points??'?')}
          /
          ${escape(c.weight??'?')}
         </p>
         <p>${escape(c.explanation)}</p>
         ${list(c.evidence)}
        </div>`
      )
      .join('')
    }

    <h4>Missing information</h4>
    ${list(score.missing_information)}
   </section>

   <section>
    <h3>${escape(requirementsLabel)}</h3>

    <h4>Participant requirements</h4>
    ${list(a.participant_requirements)}

    <h4>Technical requirements</h4>
    ${list(a.technical_requirements)}

    <h3>${escape(documentsLabel)}</h3>
    ${list(a.required_documents)}

    <h3>Risks</h3>
    ${list(score.document_risks)}
    ${list(score.stop_factors)}

    <h3>AI Analysis</h3>

    <p>
     ${
      item.full_ai_analyzed
       ?'Full AI analysis has been completed from an uploaded tender PDF.'
       :'Full AI analysis has not been run for this tender yet.'
     }
    </p>

    ${fullAiControl(
      item,
      index,
      Boolean(fullAiEnabled)
    )}

    <h3>Actions</h3>

    ${
     url
      ?`<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">Open official source</a>`
      :'<p>No safe source link available.</p>'
    }

    ${shortlist}
    <p data-shortlist-status role="status" aria-live="polite"></p>
   </section>
  </div>
 `;
}

function sourceMessage(report){if(Array.isArray(report.attempted_sources)&&!report.attempted_sources.length)return 'No enabled source was checked. Review source configuration before interpreting an empty result.';if(report.total_failure)return 'Sources could not be reached. Please retry discovery.';if(report.partial_failure)return 'Results are available, but some procurement sources could not be reached.';return report.items?.length?'Discovery complete.':'No tenders found in bounded source coverage. Review company search keywords and country/region preferences or try again later.';}
/* VALYQON DISCOVERY RANKING V1 */
function rankedItems(values){
 const rows=Array.isArray(values)?[...values]:[];
 return rows.sort((a,b)=>{
  const as=a?.preliminary_scoring?.fit_score;
  const bs=b?.preliminary_scoring?.fit_score;
  const ac=a?.preliminary_scoring?.completeness_percent;
  const bc=b?.preliminary_scoring?.completeness_percent;
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

const publicApi={
 officialUrl, sourceOutcomes, matches,
 card,
 detail,
 safeUrl,
 sourceMessage,
 percent,
 applyFullAiResult
};
if(typeof module!=='undefined'&&module.exports)module.exports=publicApi;
root.ValyqonDiscovery=publicApi;
if(typeof document==='undefined')return;
const $=id=>document.getElementById(id);let items=[],report=null,serial=0,controller=null,context='',detailIndex=null,shortlistSerial=0;const savedByKey=new Map();
const identity=()=>`${state.organizationId}:${state.activeCompanyId??''}:${state.uiEpoch||0}`;
function updateGuide(){
 const node=$('discoveryGuide');if(!node?.dataset)return;
 const company=(state.companies||[]).find(c=>c.id===state.activeCompanyId);
 const keywords=company?.profile?.search_keywords;
 const en=location.port==='8765'?'API unavailable in local preview. Use the authenticated application for discovery.':!usingSharedOrganization()?'Choose a shared organization in Team.':!Number.isInteger(state.activeCompanyId)?'Activate a company in Companies, then review its PDF-derived profile.':controller?'Searching for the active company. Previous results have been cleared.':report?.total_failure?'No usable source response. Review source outcomes and retry explicitly.':items.length?`Review ${items.length} fetched opportunities for ${state.activeCompanyName}. Check reasons and unknowns, open official documents, then save your candidates.`:report?'No opportunities returned. Review search keywords in the company profile before retrying.':`Ready for ${state.activeCompanyName} in organization #${state.organizationId}. Review your company profile, then select Find opportunities.`;
 const ru=location.port==='8765'?'API недоступен в локальном превью. Используйте приложение с авторизацией.':!usingSharedOrganization()?'Выберите общую организацию в разделе Команда.':!Number.isInteger(state.activeCompanyId)?'Активируйте компанию и проверьте профиль из PDF.':controller?'Идёт поиск для активной компании. Предыдущие результаты очищены.':report?.total_failure?'Источники не ответили. Проверьте их состояние и повторите поиск.':items.length?`Проверьте закупки (${items.length}) для ${state.activeCompanyName}: причины, неизвестные данные и официальные документы. Сохраните кандидатов.`:report?'Закупки не найдены. Проверьте поисковые слова профиля.':`Компания ${state.activeCompanyName}, организация #${state.organizationId}. Проверьте профиль и нажмите «Найти закупки».`;
 const suffix=Array.isArray(keywords)&&keywords.length?` Search keywords: ${keywords.join(', ')}`:'';
 node.dataset.uiEn=en+suffix;node.dataset.uiRu=ru+(suffix?` Поисковые слова: ${keywords.join(', ')}`:'');node.textContent=node.dataset.uiEn;
 $('discoverButton').dataset.uiEn='Find opportunities';$('discoverButton').dataset.uiRu='Найти закупки';
}
function reset(){if(typeof CustomEvent!=='undefined')window.dispatchEvent(new CustomEvent('discovery-report',{detail:null}));serial++;shortlistSerial++;controller?.abort();controller=null;items=[];report=null;clearOptions();if($('discoverySourceOutcomes'))$('discoverySourceOutcomes').replaceChildren();savedByKey.clear();detailIndex=null;if($('discoveredCount'))$('discoveredCount').textContent='Not run';if($('scoredCount'))$('scoredCount').textContent='Not run';$('discoveryResults').replaceChildren();$('sourceHealth').textContent='';$('discoveryMessage').textContent='Run discovery to find opportunities.';if($('tenderDetail').open)$('tenderDetail').close();$('detailBody').replaceChildren();update();}
function update(){const ready=usingSharedOrganization()&&Number.isInteger(state.activeCompanyId)&&location.port!=='8765';updateGuide();$('discoverButton').disabled=!ready||Boolean(controller);$('filterSource').disabled=Boolean(controller);$('filterCurrency').disabled=Boolean(controller);$('discoverContext').textContent=!usingSharedOrganization()?'Select or create a shared organization in Team for global discovery.':ready?`Matching ${state.activeCompanyName}`:'Create and activate a company in Companies first.';}
function filters(){return Object.fromEntries(['keyword','source','buyer','currency','value','fit','deadline','published'].map(k=>[k,['source','currency'].includes(k)?$('filter'+k[0].toUpperCase()+k.slice(1)).value:$('filter'+k[0].toUpperCase()+k.slice(1)).value.trim()]));}
function render(){updateGuide();const f=filters();$('filterValue').disabled=!f.currency;const visible=items.map((item,i)=>({item,i})).filter(({item})=>matches(item,f));$('discoveryResults').innerHTML=visible.map(({item,i})=>canWriteWorkspace()?card(item,i,savedFor(item)):card(item,i)).join('');if(report&&!report.total_failure){$('discoveryMessage').textContent=sourceMessage(report)+` Showing ${visible.length} of ${items.length} fetched results.`;if(items.length&&!visible.length)$('discoveryMessage').textContent+=' No results match these local filters.';}}
// Labels describe fetched identifiers; they never add catalog entries or change API values.
const sourceLabels={world_bank:'World Bank - Finances One',eis:'Russia - EIS',ted:'European Union - TED',sam_gov:'United States - SAM.gov',uk_fts:'United Kingdom - Find a Tender',canada_buys:'Canada - CanadaBuys',austender:'Australia - AusTender',nz_gets:'New Zealand - GETS',za_etenders:'South Africa - eTenders',india_cppp:'India - CPPP',kz_goszakup:'Kazakhstan - Goszakup'};
function options(id,values){
 const n=$(id),old=n.value,source=id==='filterSource';
 n.replaceChildren(new Option(source?'All fetched sources':'All currencies',''));
 [...new Set(values.filter(v=>typeof v==='string'&&v.trim()))].sort().forEach(v=>n.add(new Option(source?(Object.hasOwn(sourceLabels,v)?sourceLabels[v]:v):v,v)));
 n.value=[...n.options].some(o=>o.value===old)?old:'';
}
function clearOptions(){options('filterSource',[]);options('filterCurrency',[]);$('filterValue').disabled=true;}
function savedKey(item){return JSON.stringify([String(item?.source||''),String(item?.external_id||'')]);}
function savedFor(item){return savedByKey.get(savedKey(item))||null;}
function refreshDetail(){
 if(
  detailIndex===null
  ||!$('tenderDetail').open
 )return;

 const item=items[detailIndex];

 if(!item)return;

 $('detailBody').innerHTML=detail(
  item,
  savedFor(item),
  detailIndex,
  canWriteWorkspace()
 );
}

function openDetail(index){
 const item=items[index];

 if(!item)return;

 detailIndex=index;

 $('detailTitle').textContent=
  item.title||'Tender workspace';

 $('detailBody').innerHTML=detail(
  item,
  savedFor(item),
  index,
  canWriteWorkspace()
 );

 if(!$('tenderDetail').open){
  $('tenderDetail').showModal();
 }
}
async function loadShortlist(){const scope=identity(),ticket=++shortlistSerial,org=state.organizationId;if(!usingSharedOrganization()||!Number.isInteger(state.activeCompanyId))return;try{const r=await fetch(`/api/v1/organizations/${org}/shortlist`,{credentials:'same-origin',cache:'no-store'});if(ticket!==shortlistSerial||scope!==identity())return;if(r.status===401){location.replace('/login');return;}if(!r.ok){shortlistMessage('Saved status unavailable. Open Saved to retry; existing records have not been confirmed.');return;}const records=await r.json();if(ticket!==shortlistSerial||scope!==identity())return;savedByKey.clear();for(const record of (Array.isArray(records)?records:[])){if(record?.opportunity)savedByKey.set(savedKey(record.opportunity),record);}render();refreshDetail();}catch(e){}}
function shortlistMessage(message){
 $('discoveryMessage').textContent=message;
 const status=$('detailBody').querySelector('[data-shortlist-status]');
 if(status)status.textContent=message;
}
async function saveItem(index,button){const item=items[index],scope=identity(),org=state.organizationId,runSerial=serial;if(!item||!usingSharedOrganization()||!Number.isInteger(state.activeCompanyId)||!canWriteWorkspace()||controller||location.port==='8765')return;if(button){button.disabled=true;button.textContent='Saving…';}try{const r=await fetch(`/api/v1/organizations/${org}/shortlist`,{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify(item)});if(scope!==identity()||runSerial!==serial)return;if(r.status===401){location.replace('/login');return;}if(!r.ok){if(button){button.disabled=false;button.textContent='Save opportunity';}shortlistMessage(r.status===403?'Your workspace role cannot save opportunities.':'The opportunity could not be saved. Please retry.');return;}const record=await r.json();if(scope!==identity()||runSerial!==serial)return;savedByKey.set(savedKey(item),record);render();refreshDetail();}catch(e){if(button&&scope===identity()&&runSerial===serial){button.disabled=false;button.textContent='Save opportunity';shortlistMessage('Network unavailable. The opportunity could not be saved. Please retry.');}}}
async function syncFullAiSavedSnapshot(
 item,
 scope,
 org,
 runSerial
){
 const existing=savedFor(item);

 if(!existing){
  return true;
 }

 try{
  const response=await fetch(
   `/api/v1/organizations/${org}/shortlist`,
   {
    method:'POST',
    credentials:'same-origin',
    cache:'no-store',
    headers:{
     'Content-Type':'application/json'
    },
    body:JSON.stringify(item)
   }
  );

  if(
   scope!==identity()||runSerial!==serial
  ){
   return false;
  }

  if(response.status===401){
   location.replace('/login');
   return false;
  }

  if(!response.ok){
   return false;
  }

  const record=await response.json();

  if(
   scope!==identity()||runSerial!==serial
  ){
   return false;
  }

  savedByKey.set(
   savedKey(item),
   record
  );

  return true;

 }catch(error){
  return false;
 }
}

async function analyzeTenderPdf(
 index,
 button
){
 const item=items[index];

 if(
  !item
  ||!usingSharedOrganization()
  ||!Number.isInteger(
    state.activeCompanyId
  )
  ||!canWriteWorkspace()
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
 const runSerial=serial;
 const org=state.organizationId;
 const expectedKey=savedKey(item);

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
   'Extracting tender document and running Full AI analysis?';
 }

 try{
  const response=await fetch(
   `/api/v1/organizations/${org}/analysis/pdf`,
   {
    method:'POST',
    credentials:'same-origin',
    cache:'no-store',
    body:form
   }
  );

  if(
   scope!==identity()
   ||runSerial!==serial
   ||savedKey(items[index])!==expectedKey
  ){
   return;
  }

  if(response.status===401){
   location.replace('/login');
   return;
  }

  if(response.status===403){
   if(statusNode){
    statusNode.textContent=
     'Your organization role cannot analyze tender documents.';
   }

   return;
  }

  if(response.status===409){
   if(statusNode){
    statusNode.textContent=
     'The active company changed. Reopen the tender and try again.';
   }

   return;
  }

  if(response.status===413){
   if(statusNode){
    statusNode.textContent=
     'PDF exceeds the supported size or extraction limit.';
   }

   return;
  }

  if(response.status===415){
   if(statusNode){
    statusNode.textContent=
     'Only PDF files are supported.';
   }

   return;
  }

  if(response.status===422){
   if(statusNode){
    statusNode.textContent=
     'The PDF could not be analyzed. It may be scanned, encrypted, damaged, or contain no extractable text.';
   }

   return;
  }

  if(!response.ok){
   if(statusNode){
    statusNode.textContent=
     'Full AI document analysis is unavailable. Please retry.';
   }

   return;
  }

  const result=await response.json();

  if(
   scope!==identity()
   ||runSerial!==serial
   ||savedKey(items[index])!==expectedKey
  ){
   return;
  }

  items[index]=applyFullAiResult(
   item,
   result
  );

  const shortlistUpdated=
   await syncFullAiSavedSnapshot(
    items[index],
    scope,
    org,
    runSerial
   );

  if(
   scope!==identity()
   ||runSerial!==serial
  ){
   return;
  }

  render();
  refreshDetail();

  const nextStatus=$(
   `fullAiStatus-${index}`
  );

  if(nextStatus){
   nextStatus.textContent=
    shortlistUpdated
     ?(
       result.duplicate
        ?'Existing stored document analysis was reused. No additional AI call was required.'
        :'Full AI analysis completed and stored.'
      )
     :'Full AI analysis completed and stored, but the Saved Opportunity snapshot could not be refreshed.';
  }

 }catch(error){
  if(
   scope!==identity()
   ||runSerial!==serial
  ){
   return;
  }

  const currentStatus=$(
   `fullAiStatus-${index}`
  );

  if(currentStatus){
   currentStatus.textContent=
    'Network unavailable. The tender document was not changed in this view.';
  }

 }finally{
  if(button){
   button.disabled=false;
   button.textContent=
    item.full_ai_analyzed
     ?'Analyze another PDF'
     :'Analyze tender PDF';
  }
 }
}

async function removeItem(index,button){const item=items[index],scope=identity(),org=state.organizationId,runSerial=serial;if(!item||!usingSharedOrganization()||!Number.isInteger(state.activeCompanyId)||!canWriteWorkspace()||controller||location.port==='8765')return;const record=savedFor(item);if(!record||!Number.isInteger(Number(record.id)))return;if(button){button.disabled=true;button.textContent='Removing…';}try{const r=await fetch(`/api/v1/organizations/${org}/shortlist/${record.id}`,{method:'DELETE',credentials:'same-origin',cache:'no-store'});if(scope!==identity()||runSerial!==serial)return;if(r.status===401){location.replace('/login');return;}if(!r.ok&&r.status!==404){if(button){button.disabled=false;button.textContent='Remove from saved';}shortlistMessage(r.status===403?'Your workspace role cannot remove saved opportunities.':'The opportunity could not be removed. Please retry.');return;}savedByKey.delete(savedKey(item));render();refreshDetail();}catch(e){if(button&&scope===identity()&&runSerial===serial){button.disabled=false;button.textContent='Remove from saved';shortlistMessage('Network unavailable. The opportunity could not be removed. Please retry.');}}}
async function discover(){if($('discoverButton').disabled||!usingSharedOrganization()||!Number.isInteger(state.activeCompanyId)||location.port==='8765')return;const ticket=++serial,scope=identity(),org=state.organizationId;controller=new AbortController();shortlistSerial++;savedByKey.clear();detailIndex=null;if($('tenderDetail').open)$('tenderDetail').close();$('detailBody').replaceChildren();if($('discoverySourceOutcomes'))$('discoverySourceOutcomes').replaceChildren();items=[];report=null;if($('discoveredCount'))$('discoveredCount').textContent='Not run';if($('scoredCount'))$('scoredCount').textContent='Not run';$('discoveryResults').replaceChildren();$('sourceHealth').textContent='';$('discoveryMessage').textContent='Searching configured sources…';update();
try{const r=await fetch(`/api/v1/organizations/${org}/discover/tenders`,{method:'POST',credentials:'same-origin',cache:'no-store',signal:controller.signal});if(ticket!==serial||scope!==identity())return;if(r.status===401){location.replace('/login');return;}if(!r.ok){clearOptions();$('discoveryMessage').textContent=r.status===403?'You do not have access to this organization.':r.status===409?'Create and activate an organization company first.':'Discovery is unavailable. Please retry.';return;}const data=await r.json();if(ticket!==serial||scope!==identity())return;report=data;if($('discoverySourceOutcomes'))$('discoverySourceOutcomes').innerHTML=sourceOutcomes(data);if(typeof CustomEvent!=='undefined')window.dispatchEvent(new CustomEvent('discovery-report',{detail:data}));items=data.total_failure?[]:rankedItems(data.items||[]);if($('discoveredCount'))$('discoveredCount').textContent=data.total_failure?'Unavailable':String(items.length);if($('scoredCount'))$('scoredCount').textContent=data.total_failure?'Unavailable':String(items.filter(i=>i.preliminary_scoring?.fit_score!=null).length);options('filterSource',items.map(i=>i.source));options('filterCurrency',items.map(i=>i.currency));$('sourceHealth').textContent=`Attempted: ${(data.attempted_sources||[]).join(', ')||'none'} · Reached: ${(data.successful_sources||[]).join(', ')||'none'} · Unavailable: ${(data.failed_sources||[]).join(', ')||'none'}`;const skipped=(data.source_statuses||[]).filter(s=>!(data.attempted_sources||[]).includes(s.source)).length;$('sourceHealth').textContent+=` ? Counts: checked ${(data.attempted_sources||[]).length}, reached ${(data.successful_sources||[]).length}, failed ${(data.failed_sources||[]).length}, skipped ${skipped}`;const mix=sourceMix(items);if(mix){$('sourceHealth').textContent+=` \u00b7 Results: ${mix}`;}$('discoveryMessage').textContent=sourceMessage(data);render();loadShortlist();}
catch(e){if(e.name!=='AbortError'&&ticket===serial&&scope===identity()){clearOptions();$('discoveryMessage').textContent='Network unavailable. Please retry discovery.';}}
finally{if(ticket===serial){controller=null;update();}}}
$('discoverButton').onclick=discover;
$('discoveryWorkspace').querySelectorAll('input,select').forEach(n=>n.addEventListener('input',render));
$('resetFilters').onclick=()=>{$('discoveryWorkspace').querySelectorAll('input,select').forEach(n=>n.value='');render();};
$('discoveryResults').onclick=e=>{const save=e.target.closest('[data-save]');if(save){saveItem(Number(save.dataset.save),save);return;}const button=e.target.closest('[data-detail]');if(!button)return;openDetail(Number(button.dataset.detail));};
$('detailBody').onclick=e=>{
 const analyze=e.target.closest(
  '[data-full-ai]'
 );

 if(analyze){
  analyzeTenderPdf(
   Number(analyze.dataset.fullAi),
   analyze
  );

  return;
 }

 const save=e.target.closest(
  '[data-save]'
 );

 if(save){
  saveItem(
   Number(save.dataset.save),
   save
  );

  return;
 }

 const remove=e.target.closest(
  '[data-remove]'
 );

 if(remove){
  removeItem(
   Number(remove.dataset.remove),
   remove
  );
 }
};
$('closeDetail').onclick=()=>{detailIndex=null;$('tenderDetail').close();};
$('tenderDetail').addEventListener('close',()=>{detailIndex=null;});
window.addEventListener('workspace-context',()=>{if(context!==identity()){context=identity();reset();}else update();if((location.hash.slice(1)||'overview')==='discover')loadShortlist();});context=identity();clearOptions();update();
})(typeof globalThis!=='undefined'?globalThis:this);
