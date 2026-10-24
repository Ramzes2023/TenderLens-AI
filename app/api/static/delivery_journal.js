/* VALYQON private delivery journal — only real database sender receipts.
   No automatic message sending, no simulated data, and no read/unread claims. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  if(!$('vqDeliveryJournal'))return;
  const ru=()=>window.MainLocale?.locale==='ru'||document.documentElement.lang==='ru';
  const t=(en,rus)=>ru()?rus:en;
  const scope=()=>{
    if(typeof state==='undefined'||!Number.isInteger(state.accountId)||
       !Number.isInteger(state.organizationId)||!Number.isInteger(state.activeCompanyId))return null;
    return {accountId:state.accountId,organizationId:state.organizationId,
      companyId:state.activeCompanyId};
  };
  const key=o=>o?o.accountId+':'+o.organizationId+':'+o.companyId:null;
  let cache=null,loadedKey=null,serial=0,busy=false;
  let statusCopy=['Open this section to load your recorded delivery attempts.',
    'Откройте этот раздел для загрузки журнала отправки.'];
  const setStatus=(en,rus)=>{statusCopy=[en,rus];$('vqDeliveryStatus').textContent=t(en,rus);};
  const formatTime=raw=>{
    if(typeof raw!=='string'||!raw)return t('No timestamp','Время неизвестно');
    const d=new Date(raw);
    if(Number.isNaN(d.getTime()))return t('Unverified timestamp','Время не подтверждено');
    return new Intl.DateTimeFormat(ru()?'ru-RU':'en-GB',{
      dateStyle:'medium',timeStyle:'short'
    }).format(d);
  };
  const labelFor=stateName=>stateName==='sent'
    ?t('Sender returned successfully','Отправитель ответил успешно')
    :stateName==='failed'
      ?t('Sender failed','Ошибка отправителя')
      :t('Pending sender attempt','Попытка в ожидании');
  const channelFor=channel=>channel==='telegram'?'Telegram':'Email';
  const el=(tag,cls,value)=>{
    const node=document.createElement(tag);
    if(cls)node.className=cls;
    if(value!==undefined)node.textContent=String(value);
    return node;
  };
  function blank(){
    $('vqDeliveryRows').replaceChildren();
    for(const id of ['vqDeliveryCount','vqDeliverySent','vqDeliveryFailed','vqDeliveryPending'])
      $(id).textContent='—';
  }
  function render(){
    blank();
    if(!cache)return;
    const records=cache.records;
    $('vqDeliveryCount').textContent=String(records.length);
    $('vqDeliverySent').textContent=String(records.filter(r=>r.state==='sent').length);
    $('vqDeliveryFailed').textContent=String(records.filter(r=>r.state==='failed').length);
    $('vqDeliveryPending').textContent=String(records.filter(r=>r.state==='pending').length);
    if(!records.length){
      const empty=el('div','vq-delivery-empty');
      empty.append(el('span','vq-delivery-empty-icon','✉'));
      empty.append(el('h3','',t('No recorded reminders yet','Пока нет сохранённых напоминаний')));
      empty.append(el('p','',t(
        'This only means no delivery attempts are recorded for this account and company. It does not prove that monitoring ran or that external channels are configured.',
        'Для этого аккаунта и компании пока нет записанных попыток отправки. Это не подтверждает запуск мониторинга или настройку внешних каналов.')));
      const a=el('a','',t('Review notification settings →','Проверить настройки →'));
      a.href='#settings';empty.append(a);
      $('vqDeliveryRows').append(empty);
      return;
    }
    for(const record of records){
      const row=el('article','vq-delivery-row '+record.state);
      const glyph=el('div','vq-delivery-glyph',record.channel==='telegram'?'↗':'✉');
      glyph.setAttribute('aria-hidden','true');
      const content=el('div','vq-delivery-row-copy');
      content.append(el('strong','',t('Tender deadline reminder','Напоминание о сроке закупки')));
      content.append(el('small','',channelFor(record.channel)+' · '+
        t('Lead: ','До срока: ')+String(record.lead_hours)+' '+t('hours','ч')));
      content.append(el('span','',t('Attempt recorded: ','Попытка записана: ')+formatTime(record.claimed_at)));
      const meta=el('div','vq-delivery-row-meta');
      meta.append(el('span','vq-delivery-state '+record.state,labelFor(record.state)));
      if(record.state==='sent'&&record.sent_at)
        meta.append(el('small','',formatTime(record.sent_at)));
      if(Number.isInteger(record.saved_id)&&record.saved_id>0){
        const link=el('a','',t('Open saved tender →','Открыть закупку →'));
        link.href='#saved';
        link.addEventListener('click',()=>{
          const current=scope();
          if(!current||key(current)!==loadedKey)return;
          window.dispatchEvent(new CustomEvent('valyqon-open-saved',{
            detail:{id:record.saved_id,organizationId:current.organizationId,
                    companyId:current.companyId}
          }));
        });
        meta.append(link);
      }
      row.append(glyph,content,meta);
      $('vqDeliveryRows').append(row);
    }
  }
  function invalidate(){
    ++serial;cache=null;loadedKey=null;busy=false;blank();
    $('vqDeliveryRefresh').disabled=false;
  }
  async function load(force=false){
    if(location.hash!=='#notifications')return;
    const current=scope(),sc=key(current);
    if(!sc){
      invalidate();
      setStatus('Select an organization and active company to view your delivery history.',
        'Выберите организацию и активную компанию для просмотра истории.');
      return;
    }
    if(!force && loadedKey===sc && cache){render();return;}
    if(busy)return;
    invalidate();
    const ticket=serial;busy=true;
    $('vqDeliveryRefresh').disabled=true;
    setStatus('Checking recorded reminder attempts…','Проверяем записанные попытки отправки…');
    try{
      const url='/api/v1/organizations/'+encodeURIComponent(current.organizationId)+'/deadline-alerts/history';
      const response=await fetch(url,{credentials:'same-origin',cache:'no-store'});
      if(response.status===401){window.location.replace('/login');return;}
      if(!response.ok)throw Error('HTTP '+response.status);
      const data=await response.json();
      if(ticket!==serial||key(scope())!==sc)return;
      if(data.organization_id!==current.organizationId||data.company_id!==current.companyId||
          data.scope!=='my_recorded_deadline_delivery_attempts'||!Array.isArray(data.records)||
          data.records.length>50)throw Error('Invalid delivery journal response');
      const allow=['sent','failed','pending'];
      if(!data.records.every(r=>allow.includes(r.state)&&['email','telegram'].includes(r.channel)))
        throw Error('Invalid delivery records');
      cache={records:data.records};loadedKey=sc;
      render();
      setStatus('Showing real recorded attempts for this account and company.',
        'Показаны реальные записи попыток для этого аккаунта и компании.');
    }catch(_){
      if(ticket===serial&&key(scope())===sc){
        blank();setStatus('Delivery journal unavailable. No artificial records are shown.',
          'Журнал недоступен. Демонстрационные записи не подставляются.');
      }
    }finally{
      if(ticket===serial){busy=false;$('vqDeliveryRefresh').disabled=false;}
    }
  }
  $('vqDeliveryRefresh').addEventListener('click',()=>load(true));
  window.addEventListener('hashchange',()=>load());
  window.addEventListener('workspace-context',()=>{if(key(scope())!==loadedKey)invalidate();load();});
  window.addEventListener('shell-locale-change',()=>{setStatus(...statusCopy);if(cache)render();});
  load();
})();
