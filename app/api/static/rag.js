/* Company-scoped document Q&A. No fixtures, automatic uploads or background polling. */
(function(root){
'use strict';
function validPdf(file,limit){return Boolean(file&&file.size>0&&file.size<=limit&&/\.pdf$/i.test(file.name));}
function readyJob(job){return Boolean(job&&job.state==='succeeded'&&job.ready===true);}
const errors={401:['Sign in again.','Войдите снова.'],403:['Access denied for this company.','Нет доступа к этой компании.'],404:['Document job not found in this workspace.','Задание не найдено в этом пространстве.'],409:['Document is not ready or needs ingestion with the current pipeline.','Документ ещё не готов или требует повторной обработки.'],413:['PDF exceeds the 10 MiB limit.','PDF превышает 10 МиБ.'],422:['Check the PDF or enter a question of 1–2000 characters.','Проверьте PDF или введите вопрос длиной 1–2000 символов.'],429:['Document or AI quota reached. Retry after the quota window resets.','Лимит документов или ИИ исчерпан. Повторите после обновления лимита.'],502:['AI provider unavailable. Retry later.','ИИ-провайдер недоступен. Повторите позже.'],503:['Document services unavailable. Contact the workspace administrator.','Сервисы документов недоступны. Обратитесь к администратору.']};
const contracts={validPdf,readyJob};
if(typeof module!=='undefined'&&module.exports)module.exports=contracts;
root.ValyqonRag=contracts;
if(typeof document==='undefined')return;
const $=id=>document.getElementById(id);
if(!$('ragWorkspace'))return;
let context='',generation=0,capabilities=null,job=null,busy=false,abort=null;
const identity=()=>`${state.accountId}:${state.organizationId}:${state.activeCompanyId}:${state.uiEpoch||0}`;
const selected=()=>usingSharedOrganization()&&Number.isInteger(state.activeCompanyId)&&state.companies.some(c=>c.id===state.activeCompanyId)&&location.port!=='8765';
const base=()=>`/api/v1/organizations/${state.organizationId}/companies/${state.activeCompanyId}/rag`;
const ru=()=>window.MainLocale?.locale==='ru';
let status=['Select a shared company to check document Q&A availability.','Выберите общую компанию для проверки доступности вопросов по документам.'];
function say(en,translation){status=[en,translation||en];$('ragStatus').textContent=status[ru()?1:0];}
function controls(){
 $('ragServices').disabled=!selected()||busy;
 const upload=selected()&&capabilities?.can_upload&&canWriteWorkspace()&&!busy;
 $('ragFile').disabled=!upload;$('ragUpload').disabled=!upload;
 $('ragCheck').disabled=!job||busy||!selected();
 const ready=selected()&&capabilities?.configured&&readyJob(job)&&!busy;
 $('ragQuestion').disabled=!ready;$('ragAsk').disabled=!ready;
}
async function request(path,options={}){
 const response=await fetch(path,{...options,credentials:'same-origin',cache:'no-store',signal:abort.signal});
 if(!response.ok){const pair=errors[response.status]||['Request failed. Retry later.','Запрос не выполнен. Повторите позже.'];const error=new Error(pair[0]);error.translation=pair[1];throw error;}
 return response.json();
}
async function run(action){
 if(busy||!selected())return;
 const version=generation,endpoint=base();busy=true;abort=new AbortController();controls();
 try{await action(endpoint,()=>version===generation);}
 catch(error){if(version===generation&&error.name!=='AbortError')say(error.message||'Network unavailable.',error.translation||'Сеть недоступна. Повторите позже.');}
 finally{if(version===generation){busy=false;abort=null;controls();}}
}
function jobStatus(){
 if(readyJob(job))say('Document ready. Ask a question; verify the answer against its cited pages.','Документ готов. Задайте вопрос и проверьте ответ по указанным страницам.');
 else if(['failed','cancelled'].includes(job?.state))say('Processing failed or was cancelled. Ask the administrator to inspect the worker, then upload again.','Обработка завершилась ошибкой или отменена. Администратор должен проверить обработчик.');
 else say('Document queued or processing. Use Check processing status. If it remains queued, a running ingestion worker is required.','Документ в очереди или обрабатывается. Нажмите «Проверить обработку». Для очереди нужен работающий обработчик.');
}
$('ragUpload').onclick=()=>run(async(endpoint,current)=>{
 if(!capabilities?.can_upload||!canWriteWorkspace())return;
 const file=$('ragFile').files?.[0];
 if(!validPdf(file,capabilities.max_pdf_bytes)){say('Choose a non-empty PDF up to 10 MiB.','Выберите непустой PDF до 10 МиБ.');return;}
 const form=new FormData();form.append('file',file);say('Uploading document…','Загрузка документа…');
 const result=await request(endpoint+'/documents',{method:'POST',body:form});
 if(!current())return;job=result;$('ragAnswer').replaceChildren();$('ragQuestion').value='';$('ragFile').value='';jobStatus();
});
$('ragCheck').onclick=()=>run(async(endpoint,current)=>{
 if(!job)return;const result=await request(endpoint+'/jobs/'+encodeURIComponent(job.job_id));
 if(current()){job=result;jobStatus();}
});
$('ragAsk').onclick=()=>run(async(endpoint,current)=>{
 if(!readyJob(job)||!capabilities?.configured)return;
 const question=$('ragQuestion').value.trim();if(!question){say('Enter a question about the document.','Введите вопрос по документу.');return;}
 $('ragAnswer').replaceChildren();say('Asking document…','Поиск ответа…');
 const answer=await request(endpoint+'/jobs/'+encodeURIComponent(job.job_id)+'/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question})});
 if(!current())return;
 const text=document.createElement('p');text.style.whiteSpace='pre-wrap';text.textContent=answer.answer;$('ragAnswer').append(text);
 const sources=document.createElement('ul');
 for(const source of answer.sources||[]){const node=document.createElement('li');node.textContent=`${ru()?'Страница':'Page'} ${source.page_number??'?'} · ${ru()?'Фрагмент':'Chunk'} ${source.chunk_index??'?'}`;sources.append(node);}
 $('ragAnswer').append(sources);say('Answer generated from retrieved document passages. Verify citations; omitted requirements may still apply.','Ответ по найденным фрагментам. Проверьте ссылки; пропущенные требования могут оставаться в силе.');
});
function refresh(){
 const next=identity();if(next!==context){context=next;generation++;abort?.abort();abort=null;busy=false;capabilities=null;job=null;$('ragFile').value='';$('ragQuestion').value='';$('ragAnswer').replaceChildren();say('Select a shared company to check document Q&A availability.','Выберите общую компанию для проверки доступности вопросов по документам.');}
 controls();
 if(location.hash!=='#ai-analysis'||!selected()||capabilities||busy)return;
 run(async(endpoint,current)=>{say('Checking document services…','Проверка сервисов документов…');const result=await request(endpoint+'/capabilities');if(!current())return;capabilities=result;
 if(!result.configured)say(result.message,'Вопросы по документам недоступны: нужны сервисы обработки, векторов и ИИ с общей конфигурацией.');
 else if(!result.can_upload)say('Your role can read documents but cannot upload. Select a company with a member, admin or owner role.','Ваша роль не разрешает загрузку. Нужна роль member, admin или owner.');
 else say(result.message,'Сервисы настроены. Обработка требует работающего обработчика; доступность проверяется при запросе.');});
}
window.addEventListener('workspace-context',refresh);window.addEventListener('hashchange',refresh);
$('ragServices').onclick=()=>{if(busy)return;capabilities=null;refresh();};
window.addEventListener('shell-locale-change',()=>{$('ragStatus').textContent=status[ru()?1:0];});refresh();
})(typeof globalThis!=='undefined'?globalThis:this);
