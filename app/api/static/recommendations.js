/* Read-only ranking of genuinely recorded company Discovery results.
   No upstream fetch and no restricted buyer, source URL or pricing disclosure. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  if(!$('vqRecommendations'))return;
  const ru=()=>window.MainLocale?.locale==='ru'||document.documentElement.lang==='ru';
  const t=(en,rus)=>ru()?rus:en;
  const current=()=>{
    if(typeof state==='undefined'||typeof usingSharedOrganization!=='function'||
       !usingSharedOrganization()||!Number.isInteger(state.organizationId)||
       !Number.isInteger(state.activeCompanyId))return null;
    return {organizationId:state.organizationId,companyId:state.activeCompanyId,
      uiEpoch:state.uiEpoch||0};
  };
  const key=o=>o?o.organizationId+':'+o.companyId+':'+o.uiEpoch:null;
  const make=(tag,cls,value)=>{
    const node=document.createElement(tag);
    if(cls)node.className=cls;
    if(value!==undefined)node.textContent=String(value);
    return node;
  };
  const scoreOf=item=>{
    const x=item?.preliminary_scoring?.fit_score;
    return typeof x==='number'&&Number.isFinite(x)&&x>=0&&x<=100?x:null;
  };
  const completenessOf=item=>{
    const x=item?.preliminary_scoring?.completeness_percent;
    return typeof x==='number'&&Number.isFinite(x)&&x>=0&&x<=100?x:null;
  };
  const age=raw=>{
    const dt=new Date(raw);
    return Number.isNaN(dt.getTime())?t('Time not verified','Время не подтверждено'):
      new Intl.DateTimeFormat(ru()?'ru-RU':'en-GB',{dateStyle:'medium'}).format(dt);
  };
  let entries=[],runs=0,loadedKey=null,serial=0,busy=false;
  let statusWords=['Select Recommended to inspect previous real Discovery results.',
    'Откройте рекомендации для просмотра сохранённых результатов поисков.'];
  const message=(en,rus)=>{
    statusWords=[en,rus];$('vqRecommendationsStatus').textContent=t(en,rus);
  };
  function clear(){
    ++serial;entries=[];runs=0;loadedKey=null;busy=false;
    $('vqRecommendationsResults').replaceChildren();
    for(const id of ['vqRecommendedCount','vqRecommendedRuns','vqRecommendedTopScore'])
      $(id).textContent='—';
    $('vqRecommendationsRefresh').disabled=false;
  }
  function render(){
    $('vqRecommendationsResults').replaceChildren();
    $('vqRecommendedCount').textContent=String(entries.length);
    $('vqRecommendedRuns').textContent=String(runs);
    $('vqRecommendedTopScore').textContent=entries.length?
      Math.round(entries[0].score)+'%':'—';
    const cutoff=Number($('vqRecommendedMinimum').value)||0;
    const shown=entries.filter(x=>x.score>=cutoff).slice(0,12);
    if(!shown.length){
      const empty=make('section','vq-recommend-empty');
      empty.append(make('span','vq-recommend-empty-icon','◇'));
      empty.append(make('h3','',entries.length?
        t('No saved match reaches this threshold','Нет сохранённых оценок выше порога'):
        t('No historical scored tenders yet','Пока нет закупок с оценками в истории')));
      empty.append(make('p','',entries.length?
        t('Lower the filter or run an updated Discovery search.',
          'Уменьшите порог или выполните новый поиск.'):
        t('Only actual company-scoped saved searches can appear here. No tender is invented.',
          'Здесь могут появиться только сохранённые реальные поиски компании. Закупки не подставляются.')));
      const a=make('a','',t('Open Discovery →','Открыть поиск →'));
      a.href='#discover';empty.append(a);
      $('vqRecommendationsResults').append(empty);return;
    }
    for(const entry of shown){
      const card=make('article','vq-recommend-card');
      const heading=make('div','vq-recommend-card-top');
      heading.append(make('span','vq-recommend-source',entry.source.slice(0,65)),
        make('strong','vq-recommend-score',Math.round(entry.score)+'%'));
      card.append(heading,make('h3','',entry.title));
      const bar=make('div','vq-recommend-bar'),fill=make('div','vq-recommend-bar-fill');
      fill.style.width=entry.score+'%';bar.append(fill);card.append(bar);
      card.append(make('p','vq-recommend-meta',
        t('Search recorded: ','Дата поиска: ')+age(entry.searchAt)));
      card.append(make('small','vq-recommend-completeness',
        entry.completeness===null?
          t('Completeness unknown','Полнота неизвестна'):
          t('Metadata completeness: ','Полнота метаданных: ')+Math.round(entry.completeness)+'%'));
      const a=make('a','vq-recommend-open',
        t('Open previous Search History →','Открыть предыдущий поиск →'));
      a.href='#search-history';
      a.title=t('See recorded Discovery #','См. сохранённый поиск №')+entry.historyId;
      card.append(a);$('vqRecommendationsResults').append(card);
    }
    message(
      'Showing '+shown.length+' of '+entries.length+' previously scored opportunities from '+runs+' real stored searches. No new source call was made.',
      'Показано '+shown.length+' из '+entries.length+' сохранённых оценок по '+runs+' поискам. Новых запросов к источникам нет.'
    );
  }
  async function get(url){
    const response=await fetch(url,{credentials:'same-origin',cache:'no-store'});
    if(response.status===401){location.replace('/login');throw Error('login required');}
    if(!response.ok)throw Error('HTTP '+response.status);
    return response.json();
  }
  async function load(force=false){
    if(location.hash!=='#recommended')return;
    const scope=current(),id=key(scope);
    if(!scope){
      clear();
      message('Select a shared organization and active company first.',
        'Сначала выберите общую организацию и активную компанию.');
      return;
    }
    if(!force&&loadedKey===id){render();return;}
    if(busy)return;
    clear();busy=true;
    const ticket=serial;
    $('vqRecommendationsRefresh').disabled=true;
    message('Reading previous company Discovery snapshots…',
      'Читаем сохранённые поиски активной компании…');
    try{
      const base='/api/v1/organizations/'+encodeURIComponent(scope.organizationId)+'/discovery/history';
      const summaries=await get(base+'?limit=5');
      if(ticket!==serial||id!==key(current()))return;
      if(!Array.isArray(summaries))throw Error('Invalid history list');
      const good=summaries.filter(r=>r&&r.organization_id===scope.organizationId&&
        r.company_id===scope.companyId&&Number.isInteger(r.id)&&r.id>0&&
        r.total_failure===false&&r.result_count>0).slice(0,3);
      const found=new Map();
      let completed=0;
      for(const row of good){
        const detail=await get(base+'/'+encodeURIComponent(row.id));
        if(ticket!==serial||id!==key(current()))return;
        if(detail.organization_id!==scope.organizationId||
           detail.company_id!==scope.companyId||detail.id!==row.id||
           !detail.discovery||!Array.isArray(detail.discovery.items))
           throw Error('Snapshot tenant or identity mismatch');
        completed++;
        if(detail.discovery.total_failure)continue;
        for(const item of detail.discovery.items.slice(0,120)){
          const score=scoreOf(item);
          if(score===null||typeof item.source!=='string'||!item.source.trim()||
            typeof item.external_id!=='string'||!item.external_id.trim()||
            typeof item.title!=='string'||!item.title.trim())continue;
          const identifier=JSON.stringify([item.source,item.external_id]);
          const entry={source:item.source,title:item.title.slice(0,220),
            score,completeness:completenessOf(item),
            searchAt:row.created_at,historyId:row.id};
          if(!found.has(identifier)||found.get(identifier).score<score)
            found.set(identifier,entry);
        }
      }
      if(ticket!==serial||id!==key(current()))return;
      entries=[...found.values()].sort((a,b)=>
        b.score-a.score||(b.completeness??-1)-(a.completeness??-1)).slice(0,150);
      runs=completed;loadedKey=id;render();
    }catch(_){
      if(ticket===serial&&id===key(current())){
        entries=[];runs=0;loadedKey=null;
        $('vqRecommendationsResults').replaceChildren();
        message('Previous matches could not be loaded. No sample results are shown.',
          'Не удалось загрузить предыдущие оценки. Демонстрационные результаты не подставляются.');
      }
    }finally{
      if(ticket===serial){busy=false;$('vqRecommendationsRefresh').disabled=false;}
    }
  }
  $('vqRecommendationsRefresh').addEventListener('click',()=>load(true));
  $('vqRecommendedMinimum').addEventListener('change',()=>{if(loadedKey)render();});
  window.addEventListener('hashchange',()=>load());
  window.addEventListener('workspace-context',()=>{
    if(key(current())!==loadedKey)clear();
    load();
  });
  window.addEventListener('shell-locale-change',()=>{message(...statusWords);if(loadedKey)render();});
  load();
})();