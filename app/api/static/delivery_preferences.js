/* Real persisted, opt-in-only reminder preferences for current company.
   No alert is sent or scheduled from this browser form. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  if(!$('vqDeliveryPrefs'))return;
  const ru=()=>window.MainLocale?.locale==='ru'||document.documentElement.lang==='ru';
  const t=(en,rus)=>ru()?rus:en;
  const scope=()=>{
    if(typeof state==='undefined'||!Number.isInteger(state.accountId)||
       !Number.isInteger(state.organizationId)||!Number.isInteger(state.activeCompanyId))return null;
    return {accountId:state.accountId,organizationId:state.organizationId,
            companyId:state.activeCompanyId};
  };
  const key=v=>v?v.accountId+':'+v.organizationId+':'+v.companyId:null;
  let loadedKey=null,loadingKey=null,serial=0,busy=false;
  let copy=['Select an active company to load your reminder permissions.',
            'Выберите активную компанию, чтобы загрузить настройки.'];
  const status=(en,rus)=>{copy=[en,rus];$('vqDeliveryPrefsStatus').textContent=t(en,rus);};
  const email=$('vqDeliveryEmailOptIn');
  const telegram=$('vqDeliveryTelegramOptIn');
  const save=$('vqDeliverySavePrefs');
  const setEnabled=enabled=>{
    email.disabled=!enabled;
    telegram.disabled=!enabled;
    save.disabled=!enabled;
  };
  const reset=()=>{
    ++serial;loadedKey=null;loadingKey=null;busy=false;
    email.checked=false;telegram.checked=false;
    setEnabled(false);
  };
  const url=s=>'/api/v1/organizations/'+encodeURIComponent(s.organizationId)+
    '/deadline-alerts/preferences';
  function selectedScope(){
    const current=scope();
    return location.hash==='#notifications'?current:null;
  }
  async function load(force=false){
    const current=selectedScope();
    if(!current){
      reset();
      status('Select a company to manage reminder preferences.',
             'Выберите компанию для настройки напоминаний.');
      return;
    }
    const target=key(current);
    if(!force&&(target===loadedKey||target===loadingKey))return;
    reset();
    loadingKey=target;
    const ticket=serial;
    busy=true;
    status('Loading your saved reminder permissions…',
           'Загружаем сохранённые настройки напоминаний…');
    try{
      const response=await fetch(url(current),{credentials:'same-origin',cache:'no-store'});
      if(response.status===401){window.location.replace('/login');return;}
      if(!response.ok)throw Error('Preferences unavailable');
      const data=await response.json();
      if(serial!==ticket||key(selectedScope())!==target)return;
      if(typeof data.email_enabled!=='boolean'||typeof data.telegram_enabled!=='boolean')
        throw Error('Invalid preference state');
      email.checked=data.email_enabled;
      telegram.checked=data.telegram_enabled;
      loadedKey=target;
      setEnabled(true);
      status('Your current preferences are loaded. Saving does not send any message.',
             'Настройки загружены. Сохранение не отправляет сообщения.');
    }catch(_){
      if(serial===ticket&&key(selectedScope())===target)
        status('Reminder preferences unavailable; no changes were made.',
               'Настройки недоступны; ничего не изменено.');
    }finally{
      if(serial===ticket){busy=false;loadingKey=null;}
    }
  }
  async function persist(){
    const current=selectedScope();
    if(!current||key(current)!==loadedKey||busy)return;
    const target=loadedKey, ticket=++serial;
    busy=true;
    setEnabled(false);
    status('Saving your explicit choices…','Сохраняем выбранные настройки…');
    try{
      const response=await fetch(url(current),{
        method:'PUT',credentials:'same-origin',cache:'no-store',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({email_enabled:email.checked,
                             telegram_enabled:telegram.checked})
      });
      if(response.status===401){window.location.replace('/login');return;}
      if(!response.ok)throw Error('Preference change failed');
      const data=await response.json();
      if(serial!==ticket||key(selectedScope())!==target)return;
      if(typeof data.email_enabled!=='boolean'||typeof data.telegram_enabled!=='boolean')
        throw Error('Invalid preference confirmation');
      email.checked=data.email_enabled;
      telegram.checked=data.telegram_enabled;
      status('Preferences saved in the database. No message was sent.',
             'Настройки сохранены в базе. Сообщения не отправлялись.');
    }catch(_){
      if(serial===ticket&&key(selectedScope())===target){
        loadedKey=null;
        status('Could not save. Recheck your actual preferences before trying again.',
               'Не удалось сохранить. Перечитайте настройки перед повторной попыткой.');
      }
    }finally{
      if(serial===ticket){
        busy=false;
        setEnabled(loadedKey===target);
      }
    }
  }
  save.addEventListener('click',persist);
  window.addEventListener('hashchange',()=>load());
  window.addEventListener('workspace-context',()=>{
    if(key(selectedScope())!==loadedKey&&key(selectedScope())!==loadingKey)reset();
    load();
  });
  window.addEventListener('shell-locale-change',()=>status(...copy));
  load();
})();
