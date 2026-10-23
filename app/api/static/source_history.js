/* Version history from actual persisted EIS worker evidence, not PDF guesses. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id),root=$('savedSourceHistoryPanel');
  if(!root)return;
  let selection=null,serial=0;
  const ru=()=>window.MainLocale?.locale==='ru'||document.documentElement.lang==='ru';
  const t=(a,b)=>ru()?b:a;
  const status=(en,russian)=>{$('savedSourceHistoryStatus').textContent=t(en,russian);};
  const valid=()=>selection&&typeof state!=='undefined'&&
    state.organizationId===selection.organizationId&&
    state.activeCompanyId===selection.companyId&&$('savedDetail').open;
  const clear=()=>{
    serial++;selection=null;root.hidden=true;
    $('savedSourceHistoryEvents').replaceChildren();
    $('refreshSavedSourceHistory').disabled=true;
  };
  const fields={
    title:['Title','Название'],buyer:['Buyer','Заказчик'],
    price:['Price','Цена'],currency:['Currency','Валюта'],deadline:['Deadline','Срок']
  };
  async function refresh(){
    if(!valid())return;
    const sc={...selection},ticket=++serial;
    $('refreshSavedSourceHistory').disabled=true;
    const list=$('savedSourceHistoryEvents');list.replaceChildren();
    status('Reading stored source observations…','Читаем сохранённые версии источника…');
    try{
      const url='/api/v1/organizations/'+encodeURIComponent(sc.organizationId)+
        '/shortlist/'+encodeURIComponent(sc.id)+'/source-history';
      const response=await fetch(url,{credentials:'same-origin',cache:'no-store'});
      if(response.status===401){location.replace('/login');return;}
      if(!response.ok)throw Error('history unavailable');
      const payload=await response.json();
      if(ticket!==serial||!valid()||selection.id!==sc.id)return;
      if(!payload.supported){
        status('This source has no supported persisted version history yet.',
          'Для этого источника ещё нет поддерживаемой истории версий.');
        return;
      }
      if(!Array.isArray(payload.revisions)||payload.revisions.length===0){
        status('No stored revisions for this tender. It may still have changed upstream.',
          'Для этой закупки нет сохранённых версий. На исходной площадке изменения всё равно могли произойти.');
        return;
      }
      status(t('Stored EIS observations: ','Сохранено наблюдений ЕИС: ')+payload.revisions.length,
             'Сохранено наблюдений ЕИС: '+payload.revisions.length);
      for(const record of payload.revisions.slice(0,25)){
        const li=document.createElement('li'),head=document.createElement('strong');
        const raw=String(record.observed_at||'');
        const when=new Date(raw);
        head.textContent=Number.isNaN(when.getTime())?raw.slice(0,28):
          new Intl.DateTimeFormat(ru()?'ru-RU':'en-GB',{
            year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'
          }).format(when);
        li.append(head);
        const statusNode=document.createElement('span');
        const names=(Array.isArray(record.changed_fields)?record.changed_fields:[])
          .map(v=>fields[v.field]?t(...fields[v.field]):null).filter(Boolean);
        statusNode.textContent=record.status==='first_observation'
          ?t('First recorded observation','Первая сохранённая версия')
          :record.status==='changed'&&names.length
            ?t('Changed fields: ','Изменены поля: ')+names.join(', ')
            :record.status==='changed'
              ?t('Other metadata change (documents not verified)','Другие изменения метаданных (PDF не проверены)')
              :t('No confirmed comparable changes','Подтверждённых сравнимых изменений нет');
        li.append(statusNode);list.append(li);
      }
    }catch(_){
      if(ticket===serial&&valid())status(
        'Stored source history unavailable. This is not proof that there were no changes.',
        'История источника недоступна. Это не доказательство отсутствия изменений.');
    }finally{
      if(ticket===serial&&valid())$('refreshSavedSourceHistory').disabled=false;
    }
  }
  window.addEventListener('valyqon-saved-detail-open',event=>{
    clear();
    const value=event.detail;
    if(!value||!Number.isInteger(value.id)||value.id<=0||typeof state==='undefined')return;
    if(value.organizationId!==state.organizationId||value.companyId!==state.activeCompanyId)return;
    selection={...value};root.hidden=false;
    refresh();
  });
  $('refreshSavedSourceHistory').addEventListener('click',refresh);
  $('savedDetail').addEventListener('close',clear);
  window.addEventListener('workspace-context',()=>{if(selection&&!valid())clear();});
})();