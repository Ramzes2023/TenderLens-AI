/* Real company-scoped tender assignee and internal two-person approval.
   Read/write the authenticated API, never local mock stages or bid submissions. */
(() => {
  'use strict';
  const el=id=>document.getElementById(id), panel=el('savedTenderTeamPanel');
  if(!panel)return;
  let selection=null,revision=0,ticket=0,data=null,working=false;
  const ru=()=>window.MainLocale?.locale==='ru'||document.documentElement.lang==='ru';
  const t=(en,rus)=>ru()?rus:en;
  const active=()=>selection&&typeof state!=='undefined'&&
    selection.organizationId===state.organizationId&&
    selection.companyId===state.activeCompanyId&&el('savedDetail').open;
  const url=savedId=>'/api/v1/organizations/'+encodeURIComponent(state.organizationId)+
    '/shortlist/'+encodeURIComponent(savedId)+'/team';
  const status=(en,rus)=>{el('savedTenderTeamStatus').textContent=t(en,rus);};
  const actions={
    assign:'saveTenderAssignee',request:'requestTenderApproval',
    approve:'approveTenderParticipation',reject:'rejectTenderParticipation',
    withdraw:'withdrawTenderApproval'
  };
  const label={
    not_requested:['Not requested','Не запрошено'],
    pending:['Awaiting review','Ожидает согласования'],
    approved:['Approved internally','Согласовано внутри команды'],
    rejected:['Rejected internally','Отклонено внутри команды']
  };
  const reset=()=>{
    ticket++;selection=null;data=null;revision=0;working=false;panel.hidden=true;
    el('savedTenderTeamEvents').replaceChildren();
    Object.values(actions).forEach(id=>el(id).disabled=true);
    el('savedTenderAssignee').disabled=true;
  };
  function draw(){
    if(!data||!active())return;
    const stateName=label[data.approval_state]||label.not_requested;
    el('savedTenderTeamApproval').textContent=t(...stateName);
    const admin=['owner','admin'].includes(data.your_role);
    const writer=['owner','admin','member'].includes(data.your_role);
    const currentId=Number(typeof state!=='undefined'?state.accountId:NaN);
    const canDecide=admin&&data.approval_state==='pending'&&
      data.requested_by_account_id!==currentId;
    const pending=data.approval_state==='pending';
    el(actions.assign).disabled=working||!admin;
    el(actions.request).disabled=working||!writer||pending;
    el(actions.approve).disabled=working||!canDecide;
    el(actions.reject).disabled=working||!canDecide;
    el(actions.withdraw).disabled=working||!pending||!writer||
      (data.requested_by_account_id!==currentId&&!admin);
    const assignee=el('savedTenderAssignee');
    assignee.replaceChildren();
    assignee.add(new Option(t('Unassigned','Не назначен'),''));
    (Array.isArray(data.members)?data.members:[]).forEach(member=>{
      // Authorized organization member directory returned by scoped endpoint.
      assignee.add(new Option(String(member.email)+' · '+String(member.role),String(member.account_id)));
    });
    assignee.value=data.assignee_account_id==null?'':String(data.assignee_account_id);
    assignee.disabled=working||!admin;
    el('savedTenderTeamExplanation').textContent=pending?
      t('The requester cannot approve their own participation request. A different owner/admin must decide.',
        'Автор запроса не может согласовать его самостоятельно. Решение принимает другой владелец или администратор.'):
      t('Approval records are team decisions only. They do not submit bids or validate official tender outcomes.',
        'Решения команды не подают заявки и не подтверждают официальный результат закупки.');
  }
  async function request(path,options={}){
    const response=await fetch(path,{credentials:'same-origin',cache:'no-store',...options});
    if(response.status===401){location.replace('/login');throw Error('signed out');}
    if(!response.ok)throw Error('HTTP '+response.status);
    return response.json();
  }
  async function loadEvents(epoch,sc){
    try{
      const events=await request(url(sc.id)+'/events');
      if(ticket!==epoch||!active()||selection.id!==sc.id)return;
      const root=el('savedTenderTeamEvents');root.replaceChildren();
      for(const event of (Array.isArray(events)?events:[]).slice(0,40)){
        const row=document.createElement('li');
        const action=String(event.action||'').slice(0,20);
        const date=String(event.changed_at||'').slice(0,22);
        row.textContent=action+' · '+t('Member ','Участник ')+
          String(event.actor_account_id)+' · '+date;
        root.append(row);
      }
      if(!root.children.length){
        const li=document.createElement('li');
        li.textContent=t('No team decisions recorded.','Решений пока нет.');
        root.append(li);
      }
    }catch(_){
      if(ticket===epoch&&active())status('Decision history unavailable.','Журнал решений недоступен.');
    }
  }
  async function reload(epoch,sc){
    try{
      const payload=await request(url(sc.id));
      if(ticket!==epoch||!active()||selection.id!==sc.id)return;
      data=payload;revision=Number(payload.revision);
      if(!Number.isInteger(revision))throw Error('bad revision');
      panel.hidden=false;draw();
      status('Team decisions loaded from your company.','Решения команды загружены из базы компании.');
      await loadEvents(epoch,sc);
    }catch(_){
      if(ticket!==epoch||!active())return;
      data=null;panel.hidden=false;
      Object.values(actions).forEach(id=>el(id).disabled=true);
      el('savedTenderAssignee').disabled=true;
      status('Team decisions unavailable. Check access and reopen this tender.',
        'Командное согласование недоступно. Проверьте доступ и откройте закупку повторно.');
    }
  }
  window.addEventListener('valyqon-saved-detail-open',event=>{
    const item=event.detail;
    reset();
    if(!item||!Number.isInteger(item.id)||item.id<=0)return;
    if(item.organizationId!==state.organizationId||item.companyId!==state.activeCompanyId)return;
    selection={...item};panel.hidden=false;
    status('Loading assignee and review state…','Загружаем ответственного и согласование…');
    reload(ticket,selection);
  });
  el('savedDetail').addEventListener('close',reset);
  window.addEventListener('workspace-context',()=>{
    if(!active()&&selection)reset();
  });
  async function commit(action){
    if(!active()||!data||working)return;
    const id=selection.id,scope={...selection},epoch=ticket;
    const assigneeValue=el('savedTenderAssignee').value;
    const body={action,expected_revision:revision};
    if(action==='assign')body.assignee_account_id=assigneeValue===''?null:Number(assigneeValue);
    const admin=['owner','admin'].includes(data.your_role);
    if(action==='assign'&&!admin)return;
    if(['approve','reject'].includes(action)&&
      (!admin||data.requested_by_account_id===state.accountId))return;
    if(data.your_role==='viewer')return;
    working=true;draw();
    status('Saving team decision…','Сохраняем решение команды…');
    try{
      await request(url(id),{method:'PATCH',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(body)});
      if(epoch!==ticket||!active())return;
      status('Decision saved. Reloading audit…','Решение сохранено. Загружаем журнал…');
    }catch(_){
      if(epoch!==ticket||!active())return;
      status('Decision not saved or another user updated it. Reloading the authoritative record.',
        'Не удалось сохранить решение или другой сотрудник изменил данные. Обновляем запись из базы.');
    }finally{
      if(epoch===ticket&&active()){
        working=false;
        await reload(epoch,scope);
      }
    }
  }
  for(const [action,id] of Object.entries(actions)){
    el(id).addEventListener('click',()=>commit(action));
  }
})();