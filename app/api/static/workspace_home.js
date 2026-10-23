/* VALYQON workspace workbench: existing account state + local route preferences.
   This file never fetches, fabricates tenders, changes permissions or submits jobs. */
(() => {
  'use strict';
  const get=id=>document.getElementById(id);
  const workbench=get('vqWorkbench');
  const pin=get('vqPinCurrent'),pinLabel=get('vqPinLabel');
  const dialog=get('vqShortcutDialog');
  if(!workbench||!pin)return;

  const routeLinks=new Map();
  document.querySelectorAll('#appNav a[data-nav]').forEach(a=>{
    const key=a.dataset.nav;
    if(/^[a-z][a-z-]{1,32}$/.test(key))routeLinks.set(key,a);
  });
  if(!routeLinks.has('overview'))return;

  const pinnedKey='valyqon.ui.pinned-pages.v1';
  const recentKey='valyqon.ui.recent-pages.v1';
  const local=(store,key)=>{
    try{return JSON.parse(store.getItem(key)||'null');}catch(_){return null;}
  };
  const safeKeys=(raw,max)=>Array.isArray(raw)
    ? [...new Set(raw.filter(item=>typeof item==='string'&&routeLinks.has(item)))].slice(0,max)
    : [];
  const defaults=['discover','saved','source-health'];
  let pinned=safeKeys(local(localStorage,pinnedKey),6);
  if(local(localStorage,pinnedKey)===null)pinned=defaults.filter(key=>routeLinks.has(key));
  let recent=safeKeys(local(sessionStorage,recentKey),5);

  const remember=(store,key,array)=>{
    try{store.setItem(key,JSON.stringify(array));}catch(_){}
  };
  const ru=()=>document.documentElement.lang==='ru' || window.MainLocale?.locale==='ru';
  const tr=(en,russian)=>ru()?russian:en;
  const changeText=(node,en,russian)=>{
    if(!node)return;
    // Normal locale refresh can reliably translate dynamic status copy too.
    node.dataset.uiEn=en;
    node.dataset.uiRu=russian;
    const value=tr(en,russian);
    if(node.textContent!==value)node.textContent=value;
  };
  const label=key=>routeLinks.get(key)?.querySelector('span')?.textContent.trim()
    ||routeLinks.get(key)?.textContent.trim() ||key;
  const route=()=> {
    const hash=window.location.hash.replace(/^#/,'');
    return routeLinks.has(hash)?hash:'overview';
  };
  const navigate=key=> {
    if(!routeLinks.has(key))return;
    window.location.hash='#'+key;
  };
  const addLink=(parent,key)=>{
    const a=document.createElement('a');
    a.href='#'+key;
    a.textContent=label(key);
    parent.append(a);
  };
  function drawLinks(){
    const pins=get('vqPinnedPages'),recents=get('vqRecentPages');
    if(pins){
      pins.replaceChildren();
      pinned.forEach(key=>addLink(pins,key));
      if(!pinned.length)changeText(pins,
        'No pages pinned. Use Pin page above.',
        'Нет закреплённых разделов. Нажмите «Закрепить страницу» выше.');
    }
    if(recents){
      recents.replaceChildren();
      recent.forEach(key=>addLink(recents,key));
      if(!recent.length)changeText(recents,
        'Opened sections will appear here.',
        'Открытые разделы появятся здесь.');
    }
    const isPinned=pinned.includes(route());
    pin.setAttribute('aria-pressed',String(isPinned));
    changeText(pinLabel,isPinned?'Unpin page':'Pin page',
      isPinned?'Открепить':'Закрепить');
    pin.firstChild && pin.firstChild.nodeType===Node.TEXT_NODE
      && (pin.firstChild.textContent=isPinned?'★ ':'☆ ');
    pin.setAttribute('aria-label',tr(
      isPinned?'Unpin current page':'Pin current page',
      isPinned?'Открепить текущий раздел':'Закрепить текущий раздел'));
    changeText(get('vqCurrentSection'),label(route()),label(route()));
  }
  function recordPage(){
    recent=[route(),...recent.filter(key=>key!==route())].slice(0,5);
    remember(sessionStorage,recentKey,recent);
    drawLinks();
  }
  pin.addEventListener('click',()=>{
    const key=route();
    pinned=pinned.includes(key)?pinned.filter(item=>item!==key):[key,...pinned].slice(0,6);
    remember(localStorage,pinnedKey,pinned);
    drawLinks();
  });

  const count=(id)=>{
    const value=get(id)?.textContent.trim()||'';
    return /^\d+$/.test(value)?Number(value):null;
  };
  const activeOrg=()=>{
    if(typeof state==='undefined'||!Number.isInteger(state.organizationId))return null;
    const list=Array.isArray(state.organizations)?state.organizations:[];
    return list.find(o=>o.id===state.organizationId)||null;
  };
  const accountLoaded=()=>typeof state!=='undefined'&&Number.isInteger(state.accountId);
  const usableCompany=()=>accountLoaded()&&Number.isInteger(state.activeCompanyId);
  const setStatus=(id,en,russian)=>changeText(get(id),en,russian);

  function paintReadiness(){
    if(!accountLoaded()){
      setStatus('vqWorkbenchState','Account data not loaded','Данные аккаунта не загружены');
      get('vqWorkbenchState')?.parentElement?.setAttribute('data-mode','missing');
      for(const id of ['vqWbOrg','vqWbCompany','vqWbDiscovered','vqWbSaved'])
        setStatus(id,'—','—');
      setStatus('vqProgressCount','Not checked','Не проверено');
      return;
    }
    const org=activeOrg();
    const shared=!!org&&!org.personal;
    const company=usableCompany();
    const searched=company&&count('discoveredCount')!==null;
    const completed=[shared,company,searched].filter(Boolean).length;
    setStatus('vqWorkbenchState',company?
      'Company context loaded':'Setup required',company?
      'Профиль компании загружен':'Требуется настройка');
    get('vqWorkbenchState')?.parentElement?.setAttribute('data-mode',company?'ready':'missing');
    const name=org?.name||null;
    setStatus('vqWbOrg',name||'Not selected',name||'Не выбрана');
    const companyName=company&&typeof state.activeCompanyName==='string'
      ?state.activeCompanyName:'';
    setStatus('vqWbCompany',companyName||'Not active',companyName||'Не активна');
    const discovered=searched?count('discoveredCount'):null;
    setStatus('vqWbDiscovered',discovered===null?'Not run':String(discovered),
      discovered===null?'Не запускался':String(discovered));
    // This count is a last loaded UI snapshot, never a market or live counter.
    const saved=company?count('savedCount'):null;
    setStatus('vqWbSaved',saved===null?'Not loaded':String(saved),
      saved===null?'Не загружено':String(saved));
    setStatus('vqProgressCount',completed+'/3',completed+'/3');
    const ring=get('vqProgressCount');
    if(ring)ring.style.setProperty('--vq-progress-angle',String(completed*120)+'deg');
    const track=document.querySelector('.vq-progress-track');
    if(track)track.setAttribute('aria-valuenow',String(completed));
    const fill=get('vqProgressFill');
    if(fill)fill.style.width=(completed*100/3).toFixed(1)+'%';
    for(const [id,done] of [['vqStepOrg',shared],['vqStepCompany',company],['vqStepSearch',searched]]){
      const elem=get(id);
      if(!elem)continue;
      elem.classList.toggle('is-done',done);
      const status=elem.querySelector('.vq-step-status');
      if(status)status.textContent=done?'✓':'○';
    }
    if(!shared){
      setStatus('vqNextText',
        'Create or select a shared organization before starting global procurement discovery.',
        'Создайте или выберите общую организацию перед началом поиска закупок.');
      const link=get('vqNextLink');
      link.href='#team';
      changeText(link,'Set up organization →','Настроить организацию →');
    } else if(!company){
      setStatus('vqNextText',
        'Add and activate a company profile with products and search keywords to enable matching.',
        'Добавьте и активируйте профиль компании, товары и ключевые слова для поиска.');
      const link=get('vqNextLink');
      link.href='#companies';
      changeText(link,'Create company profile →','Создать профиль компании →');
    } else if(!searched){
      setStatus('vqNextText',
        'Your company context is ready. Open Discovery to run a real source search when available.',
        'Профиль компании готов. Откройте поиск, чтобы запросить настоящие источники при их доступности.');
      const link=get('vqNextLink');
      link.href='#discover';
      changeText(link,'Go to Discovery →','Перейти к поиску →');
    } else {
      setStatus('vqNextText',
        'Review your latest Discovery results, verify source availability, and save relevant opportunities.',
        'Проверьте результаты последнего поиска и доступность источников, затем сохраните подходящие закупки.');
      const link=get('vqNextLink');
      link.href='#discover';
      changeText(link,'Review opportunities →','Проверить закупки →');
    }
  }

  const openHelp=get('vqShortcutHelp'),closeHelp=get('vqShortcutClose');
  const showHelp=()=>{
    if(!dialog||typeof dialog.showModal!=='function'||dialog.open)return;
    dialog.showModal();
  };
  openHelp?.addEventListener('click',showHelp);
  closeHelp?.addEventListener('click',()=>dialog?.close());
  dialog?.addEventListener('click',e=>{
    if(e.target===dialog)dialog.close();
  });
  document.addEventListener('keydown',e=>{
    if(e.defaultPrevented||e.ctrlKey||e.altKey||e.metaKey)return;
    const target=e.target;
    if(target instanceof HTMLElement &&
      (target.isContentEditable||target.closest('input, textarea, select, [contenteditable="true"]')))
      return;
    if(e.key==='?'&&!e.repeat){
      e.preventDefault();
      showHelp();
    }
  });

  function refresh(){
    recordPage();
    paintReadiness();
  }
  window.addEventListener('hashchange',refresh);
  window.addEventListener('workspace-context',paintReadiness);
  window.addEventListener('discovery-report',paintReadiness);
  window.addEventListener('shell-locale-change',()=>{
    drawLinks();
    paintReadiness();
  });
  refresh();
})();
