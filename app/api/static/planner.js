/* Tender Planner: real saved shortlist + existing scoped workflow endpoints.
   Never fabricate notices, deadlines or stages, and never issue bid submissions. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const panel=$('plannerWorkspace');
  if(!panel)return;

  const stages=[
    ['new','New','Новые'],
    ['reviewing','Reviewing','Анализ'],
    ['preparing','Preparing','Подготовка'],
    ['submitted','Submitted (team)','Подано (внутр.)'],
    ['won','Won (team)','Победа (внутр.)'],
    ['lost','Lost (team)','Проигрыш (внутр.)'],
    ['archived','Archived','Архив']
  ];
  const PAGE_SIZE=30,MAX_ITEMS=300;
  let records=[], visibleLimit=PAGE_SIZE, epoch=0, activeScope='', view='board';
  let month=new Date(new Date().getFullYear(),new Date().getMonth(),1);
  let loaded=false, loadError=false, busy=false;
  const ru=()=>window.MainLocale?.locale==='ru'||document.documentElement.lang==='ru';
  const t=(en,russian)=>ru()?russian:en;
  const stageLabel=s=>{const entry=stages.find(x=>x[0]===s);return entry?t(entry[1],entry[2]):t('Unknown stage','Этап неизвестен');};
  const scope=()=>typeof state!=='undefined'?String(state.organizationId)+':'+String(state.activeCompanyId):'';
  const enabled=()=>typeof state!=='undefined'&&typeof usingSharedOrganization==='function'
    &&usingSharedOrganization()&&Number.isInteger(state.organizationId)
    &&Number.isInteger(state.activeCompanyId);
  const canEdit=()=>enabled()&&typeof canWriteWorkspace==='function'&&canWriteWorkspace();
  const status=(en,russian)=>{$('vqPlannerStatus').textContent=t(en,russian);};
  const safeDate=(raw)=>{
    if(typeof raw!=='string')return null;
    const value=raw.trim();
    if(/^\d{4}-\d{2}-\d{2}$/.test(value)){
      const day=new Date(value+'T12:00:00');
      return !Number.isNaN(day.getTime())&&day.getFullYear()===Number(value.slice(0,4))&&
        day.getMonth()+1===Number(value.slice(5,7))&&day.getDate()===Number(value.slice(8,10))&&
        day.getFullYear()>=2000&&day.getFullYear()<=2100
        ?{instant:null,day,kind:'date'}:null;
    }
    if(!/^\d{4}-\d{2}-\d{2}T\d\d:\d\d(?::\d\d(?:\.\d{1,3})?)?(?:Z|[+-]\d\d:\d\d)$/i.test(value))return null;
    // Reject impossible written civil dates before applying the supplied offset.
    const yy=Number(value.slice(0,4)),mm=Number(value.slice(5,7)),dd=Number(value.slice(8,10));
    const civil=new Date(Date.UTC(yy,mm-1,dd));
    if(civil.getUTCFullYear()!==yy||civil.getUTCMonth()+1!==mm||civil.getUTCDate()!==dd)return null;
    const when=new Date(value);
    return Number.isNaN(when.getTime())||when.getUTCFullYear()<2000||when.getUTCFullYear()>2100
      ?null:{instant:when,day:when,kind:'instant'};
  };
  const ymd=date=>String(date.getFullYear()).padStart(4,'0')+'-'+
    String(date.getMonth()+1).padStart(2,'0')+'-'+String(date.getDate()).padStart(2,'0');
  const now=()=>new Date();
  const deadlineInfo=date=>{
    if(!date)return t('Deadline unavailable','Срок не указан');
    const pretty=new Intl.DateTimeFormat(ru()?'ru-RU':'en-GB',
      date.kind==='date'?{day:'numeric',month:'short',year:'numeric'}:
        {day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(date.day);
    return date.kind==='date'
      ?pretty+' · '+t('time not provided','время неизвестно')
      :pretty+' · '+t('local time','местное время');
  };
  const title=record=>String(record.opportunity?.title||t('Untitled tender','Закупка без названия')).slice(0,240);
  const make=(tag,className,content)=>{
    const el=document.createElement(tag);
    if(className)el.className=className;
    if(content!==undefined)el.textContent=String(content);
    return el;
  };
  const current=()=>records.slice(0,Math.min(visibleLimit,MAX_ITEMS))
    .filter(x=>(title(x)+' '+String(x.opportunity?.tender_number||x.opportunity?.external_id||''))
      .toLocaleLowerCase().includes($('vqPlannerQuery').value.trim().toLocaleLowerCase()));
  const keyFor=record=>String(record.id);
  const workflowURL=id=>'/api/v1/organizations/'+encodeURIComponent(state.organizationId)+
    '/shortlist/'+encodeURIComponent(id)+'/workflow';
  function reset(message){
    epoch++;records=[];visibleLimit=PAGE_SIZE;loaded=false;loadError=false;busy=false;
    $('vqPlannerBoard').replaceChildren();
    $('vqMonthGrid').replaceChildren();
    for(const id of ['vqPlannerTotal','vqPlannerSoon','vqPlannerLate','vqPlannerDateOnly'])
      $(id).textContent='—';
    $('vqPlannerCalendarExport').disabled=true;
    $('vqPlannerMore').hidden=true;
    $('vqPlannerShown').textContent='';
    if(message)status(message,message);
  }
  async function apiJSON(url,options={}){
    const response=await fetch(url,{credentials:'same-origin',cache:'no-store',...options});
    if(response.status===401){window.location.replace('/login');throw Error('login required');}
    if(!response.ok)throw Error('HTTP '+response.status);
    return await response.json();
  }
  function prepPayload(value){
    return Array.isArray(value)?value.filter(x=>x&&Number.isInteger(Number(x.id))&&
      x.opportunity&&typeof x.opportunity==='object'):null;
  }
  async function fetchWorkflow(record,scopeId,ticket){
    try{
      const value=await apiJSON(workflowURL(record.id));
      if(scopeId!==scope()||ticket!==epoch)return;
      if(!stages.some(s=>s[0]===value.stage)||!Number.isInteger(value.revision))
        throw Error('invalid workflow');
      record.workflow={stage:value.stage,note:typeof value.note==='string'?value.note:'',
        revision:value.revision};
      record.workflowError=false;
    }catch(_){
      if(scopeId!==scope()||ticket!==epoch)return;
      record.workflow=null;
      record.workflowError=true;
    }
  }
  async function fetchBatch(items,ticket,scopeId){
    let next=0;
    const workers=Array.from({length:Math.min(4,items.length)},async()=>{
      while(next<items.length){
        const i=next++;
        if(ticket!==epoch||scopeId!==scope())return;
        await fetchWorkflow(items[i],scopeId,ticket);
      }
    });
    await Promise.all(workers);
  }
  async function load(){
    if(!enabled()){
      reset();
      status(t('Select a shared organization and activate a company in Team / Companies.',
        'Выберите общую организацию и активируйте компанию в разделах «Команда» / «Компании».'),
        'Выберите общую организацию и активируйте компанию в разделах «Команда» / «Компании».');
      loaded=true;return;
    }
    if(busy)return;
    const id=scope();
    reset();
    activeScope=id;busy=true;
    status('Loading saved tenders from your company…',
      'Загружаем сохранённые закупки вашей компании…');
    const ticket=epoch;
    try{
      const response=await apiJSON('/api/v1/organizations/'+encodeURIComponent(state.organizationId)+'/shortlist');
      if(id!==scope()||ticket!==epoch)return;
      const value=prepPayload(response);
      if(!value)throw Error('invalid shortlist');
      records=value.map(row=>({id:Number(row.id),opportunity:row.opportunity,
        date:safeDate(row.opportunity.deadline),workflow:null,workflowError:false}));
      loaded=true;
      if(records.length){
        await fetchBatch(records.slice(0,PAGE_SIZE),ticket,id);
      }
      if(id!==scope()||ticket!==epoch)return;
      status('Showing actual company saved opportunities. Team stages are internal and may not reflect official procurement results.',
        'Показаны настоящие сохранённые закупки компании. Внутренние этапы не подтверждают официальные результаты.');
      render();
    }catch(_){
      if(id!==scope()||ticket!==epoch)return;
      loadError=true;
      status('Saved tenders are unavailable. No sample records were loaded. Check access and retry.',
        'Сохранённые закупки недоступны. Примерные записи не подставляются. Проверьте доступ и повторите.');
      render();
    }finally{if(id===scope()&&ticket===epoch)busy=false;}
  }
  const pill=(record)=>{
    if(!record.date)return make('span','vq-deadline-pill unknown',t('Deadline not verified','Срок не подтверждён'));
    const date=record.date;
    const overdue=date.instant?date.instant<now():date.day.getTime()<new Date(new Date().setHours(0,0,0,0)).getTime();
    return make('span','vq-deadline-pill'+(overdue?' late':''),
      overdue?t('Past date · verify source','Дата прошла · проверьте источник'):
        deadlineInfo(date));
  };
  function stageSelect(record){
    const select=make('select','vq-planner-stage-select');
    select.setAttribute('aria-label',t('Change team stage','Изменить внутренний этап'));
    for(const [key] of stages){
      const option=new Option(stageLabel(key),key);
      select.append(option);
    }
    select.value=record.workflow?.stage||'new';
    select.disabled=!canEdit()||!record.workflow;
    if(record.workflowError){
      select.title=t('Workflow could not be loaded','Не удалось загрузить этапы работы');
    }
    select.addEventListener('change',()=>updateStage(record,select.value,select));
    return select;
  }
  function card(record){
    const article=make('article','vq-planner-card');
    article.dataset.savedId=keyFor(record);
    const header=make('div','vq-planner-card-head');
    header.append(make('span','vq-planner-card-id','#'+String(record.id)),
      pill(record));
    article.append(header);
    const h=make('h4','',title(record));
    article.append(h);
    const facts=make('div','vq-planner-facts');
    const number=record.opportunity?.tender_number||record.opportunity?.external_id;
    if(number)facts.append(make('span','',t('Notice: ','Извещение: ')+String(number).slice(0,60)));
    if(record.opportunity?.initial_price!=null){
      const amount=record.opportunity.initial_price;
      const currency=String(record.opportunity.currency||'').slice(0,12);
      facts.append(make('span','',String(amount).slice(0,25)+' '+currency));
    }
    article.append(facts);
    const footer=make('div','vq-planner-card-foot');
    footer.append(stageSelect(record));
    const link=make('a','vq-planner-to-saved',t('Saved →','Сохранённое →'));
    link.href='#saved';link.title=t('Open Saved and select this tender for full details',
      'Откройте «Сохранённое» для полной карточки этой закупки');
    footer.append(link);article.append(footer);
    if(canEdit()&&record.workflow){
      article.draggable=true;
      article.addEventListener('dragstart',event=>{
        if(!event.dataTransfer)return;
        event.dataTransfer.effectAllowed='move';
        event.dataTransfer.setData('text/plain',String(record.id));
        article.classList.add('is-dragging');
      });
      article.addEventListener('dragend',()=>article.classList.remove('is-dragging'));
    }
    return article;
  }
  function renderBoard(){
    const root=$('vqPlannerBoard');
    root.replaceChildren();
    const items=current();
    for(const [key] of stages){
      const column=make('section','vq-planner-column');
      const matching=items.filter(r=>r.workflow?.stage===key);
      const header=make('header','vq-planner-column-head');
      header.append(make('strong','',stageLabel(key)),
        make('span','vq-planner-col-count',String(matching.length)));
      column.append(header);
      if(canEdit()){
        column.addEventListener('dragover',event=>{
          if(!event.dataTransfer||!Array.from(event.dataTransfer.types).includes('text/plain'))return;
          event.preventDefault();column.classList.add('is-drop-target');
          event.dataTransfer.dropEffect='move';
        });
        column.addEventListener('dragleave',event=>{
          if(!column.contains(event.relatedTarget))column.classList.remove('is-drop-target');
        });
        column.addEventListener('drop',event=>{
          event.preventDefault();column.classList.remove('is-drop-target');
          const id=Number(event.dataTransfer?.getData('text/plain'));
          const record=items.find(x=>x.id===id);
          const select=column.ownerDocument.querySelector('.vq-planner-card[data-saved-id="'+id+'"] select');
          if(!record?.workflow||!select)return;
          updateStage(record,key,select);
        });
      }
      const list=make('div','vq-planner-column-list');
      matching.forEach(record=>list.append(card(record)));
      if(!matching.length)list.append(make('p','vq-planner-blank',
        t('No saved tenders in this stage','Нет закупок на этом этапе')));
      column.append(list);root.append(column);
    }
    const failures=items.filter(r=>!r.workflow);
    if(failures.length){
      const unknown=make('section','vq-planner-column needs-attention');
      const head=make('header','vq-planner-column-head');
      head.append(make('strong','',t('Status unavailable','Этап недоступен')),
        make('span','vq-planner-col-count',String(failures.length)));
      unknown.append(head);
      const list=make('div','vq-planner-column-list');
      failures.forEach(record=>list.append(card(record)));
      unknown.append(list);root.append(unknown);
    }
  }
  function decorateDate(date){
    const isLate=date.instant?date.instant.getTime()<Date.now():
      date.day.getTime()<new Date().setHours(0,0,0,0);
    return isLate?'overdue':'scheduled';
  }
  function renderCalendar(){
    const grid=$('vqMonthGrid');grid.replaceChildren();
    const weekdays=ru()?['Пн','Вт','Ср','Чт','Пт','Сб','Вс']:['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    weekdays.forEach(d=>grid.append(make('div','vq-month-weekday',d)));
    const y=month.getFullYear(),m=month.getMonth();
    $('vqMonthTitle').textContent=new Intl.DateTimeFormat(ru()?'ru-RU':'en-GB',
      {month:'long',year:'numeric'}).format(month);
    const offset=(new Date(y,m,1).getDay()+6)%7;
    const days=new Date(y,m+1,0).getDate();
    const items=current().filter(r=>r.date);
    const grouped=new Map();
    items.forEach(record=>{
      const k=ymd(record.date.day);
      if(!grouped.has(k))grouped.set(k,[]);
      grouped.get(k).push(record);
    });
    for(let i=0;i<offset+days;i++){
      const day=i-offset+1;
      const cell=make('div','vq-month-cell'+(day<1?' muted':''));
      if(day>0){
        const date=ymd(new Date(y,m,day));
        cell.append(make('b','vq-month-day',String(day)));
        for(const record of (grouped.get(date)||[]).slice(0,4)){
          const a=make('a','vq-month-tender '+decorateDate(record.date),title(record));
          a.href='#saved';a.title=deadlineInfo(record.date);
          cell.append(a);
        }
        if((grouped.get(date)||[]).length>4)
          cell.append(make('small','vq-month-extra','+'+String(grouped.get(date).length-4)));
        if(date===ymd(new Date()))cell.classList.add('today');
      }
      grid.append(cell);
    }
  }
  async function updateStage(record,next,select){
    if(!canEdit()||!record.workflow)return;
    if(!stages.some(x=>x[0]===next))return;
    const orgScope=scope(),ticket=epoch,previous=record.workflow;
    if(next===previous.stage)return;
    select.disabled=true;
    try{
      const result=await apiJSON(workflowURL(record.id),{
        method:'PATCH',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({stage:next,note:previous.note,expected_revision:previous.revision})
      });
      if(ticket!==epoch||orgScope!==scope())return;
      if(!stages.some(x=>x[0]===result.stage)||!Number.isInteger(result.revision))throw Error('invalid response');
      record.workflow={stage:result.stage,note:result.note,revision:result.revision};
      status('Team stage saved. This does not submit a bid or confirm an award.',
        'Внутренний этап сохранён. Это не подача заявки и не подтверждение победы.');
    }catch(e){
      if(ticket!==epoch||orgScope!==scope())return;
      status('Stage update failed or conflicted. Refreshed before retrying; no official tender action occurred.',
        'Не удалось обновить этап или возник конфликт. Данные перечитываются; официальное действие по закупке не выполнено.');
      await fetchWorkflow(record,orgScope,ticket);
    }finally{if(ticket===epoch&&orgScope===scope())render();}
  }
  const maybeSoon=date=>{
    if(!date||!date.instant)return false;
    const delta=date.instant.getTime()-Date.now();
    return delta>=0&&delta<=7*86400000;
  };
  function renderStats(){
    if(!loaded||loadError)return;
    const all=records;
    $('vqPlannerTotal').textContent=String(all.length);
    $('vqPlannerSoon').textContent=String(all.filter(r=>maybeSoon(r.date)).length);
    $('vqPlannerLate').textContent=String(all.filter(r=>r.date&&decorateDate(r.date)==='overdue').length);
    $('vqPlannerDateOnly').textContent=String(all.filter(r=>r.date?.kind==='date').length);
  }
  function render(){
    if(loaded&&!loadError)renderStats();
    $('vqPlannerBoard').hidden=view!=='board';
    $('vqPlannerCalendar').hidden=view!=='month';
    $('vqPlannerBoardTab').setAttribute('aria-pressed',String(view==='board'));
    $('vqPlannerMonthTab').setAttribute('aria-pressed',String(view==='month'));
    const n=records.length;
    const showing=Math.min(n,visibleLimit,MAX_ITEMS);
    $('vqPlannerShown').textContent=n?t('Showing '+showing+' of '+n+' saved tenders',
      'Показано '+showing+' из '+n+' сохранённых закупок'):'';
    $('vqPlannerMore').hidden=showing>=n||showing>=MAX_ITEMS;
    $('vqPlannerCalendarExport').disabled=!loaded||!records.some(r=>r.date);
    if(view==='board')renderBoard();
    else renderCalendar();
    if(n>MAX_ITEMS)status('Large shortlist: planner loads at most 300 items. Use Saved for the complete list.',
      'Большая выборка: планировщик загружает не более 300 записей. Полный список доступен в «Сохранённом».');
  }
  const icsEscape=text=>String(text).replace(/\\/g,'\\\\').replace(/[\r\n]+/g,' ')
    .replace(/;/g,'\\;').replace(/,/g,'\\,').slice(0,280);
  const utcStamp=d=>d.toISOString().replace(/[-:]/g,'').replace(/\.\d{3}/,'');
  const makeIcs=()=>{
    const lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//VALYQON AI//Tender Planner//EN','CALSCALE:GREGORIAN','METHOD:PUBLISH'];
    for(const record of records.slice(0,MAX_ITEMS)){
      const date=record.date;if(!date)continue;
      const uid=String(record.id)+'-'+String(state.organizationId)+'@valyqon.local';
      lines.push('BEGIN:VEVENT','UID:'+icsEscape(uid),'DTSTAMP:'+utcStamp(new Date()),
        'SUMMARY:'+icsEscape(t('Tender deadline — ','Срок закупки — ')+title(record)));
      if(date.kind==='date'){
        const stamp=ymd(date.day).replace(/-/g,'');
        const next=new Date(date.day.getFullYear(),date.day.getMonth(),date.day.getDate()+1);
        lines.push('DTSTART;VALUE=DATE:'+stamp,'DTEND;VALUE=DATE:'+ymd(next).replace(/-/g,''),
          'DESCRIPTION:'+icsEscape(t('Date only: exact time not supplied. Verify on the official tender platform.',
            'Указана только дата. Уточните точное время на официальной площадке.')));
      }else{
        const finish=new Date(date.instant.getTime()+15*60000);
        lines.push('DTSTART:'+utcStamp(date.instant),'DTEND:'+utcStamp(finish),
          'DESCRIPTION:'+icsEscape(t('Calendar marker for the stated deadline. Verify it on the official source.',
            'Отметка заявленного срока. Проверьте время на официальной площадке.')));
      }
      lines.push('END:VEVENT');
    }
    lines.push('END:VCALENDAR','');
    // Fold iCalendar content lines by UTF-8 octets (RFC 5545).
    const encoder=new TextEncoder(),folded=[];
    for(const line of lines){
      let segment='',bytes=0;
      for(const char of line){
        const size=encoder.encode(char).length;
        if(bytes+size>75&&segment){folded.push(segment);segment=' ';bytes=1;}
        segment+=char;bytes+=size;
      }
      folded.push(segment);
    }
    return folded.join('\r\n');
  };
  $('vqPlannerCalendarExport').addEventListener('click',()=>{
    if(!enabled()||!loaded||!records.some(r=>r.date))return;
    const blob=new Blob([makeIcs()],{type:'text/calendar;charset=utf-8'});
    const link=document.createElement('a'),url=URL.createObjectURL(blob);
    link.href=url;link.download='valyqon-tender-deadlines.ics';
    document.body.append(link);link.click();link.remove();
    window.setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  $('vqPlannerRefresh').addEventListener('click',load);
  $('vqPlannerQuery').addEventListener('input',render);
  $('vqPlannerBoardTab').addEventListener('click',()=>{view='board';render();});
  $('vqPlannerMonthTab').addEventListener('click',()=>{view='month';render();});
  $('vqMonthPrev').addEventListener('click',()=>{month=new Date(month.getFullYear(),month.getMonth()-1,1);renderCalendar();});
  $('vqMonthNext').addEventListener('click',()=>{month=new Date(month.getFullYear(),month.getMonth()+1,1);renderCalendar();});
  $('vqPlannerMore').addEventListener('click',async()=>{
    if(busy||!enabled())return;
    const next=Math.min(records.length,visibleLimit+PAGE_SIZE,MAX_ITEMS);
    const newBatch=records.slice(visibleLimit,next);
    const ticket=epoch,sc=scope();
    visibleLimit=next;busy=true;
    $('vqPlannerMore').disabled=true;
    await fetchBatch(newBatch,ticket,sc);
    if(sc===scope()&&ticket===epoch){busy=false;$('vqPlannerMore').disabled=false;render();}
  });
  window.addEventListener('hashchange',()=>{
    if(location.hash==='#tender-planner'&&(!loaded||loadError||activeScope!==scope()))load();
  });
  window.addEventListener('workspace-context',()=>{
    if(activeScope!==scope())reset();
    if(location.hash==='#tender-planner'&&(!loaded||loadError))load();
  });
  window.addEventListener('shell-locale-change',render);
  if(location.hash==='#tender-planner')load();
})();
