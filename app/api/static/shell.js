/* Keep existing organization/company services and give them a shared navigation shell. */
(function(){
 const $=id=>document.getElementById(id);
 const sections={companies:['companies','companyCreator'],documents:['tenders'],monitoring:['monitoringCenter'],team:['organizationCard'],settings:['telegramCard']};
 for(const [page,ids] of Object.entries(sections))for(const id of ids){const node=$(id);if(node)node.closest('article').dataset.page=page;}
 const org=$('organizationSelect').parentElement; $('orgControl').append(org);
 document.querySelectorAll('#existingWorkspace > article:not([data-page])').forEach(n=>n.dataset.page='overview');
 const future={recommended:'Personalized recommendations are not available yet. Use Discover to inspect preliminary company fit.', 'ai-analysis':'A standalone analysis workspace is not available yet. Open an opportunity in Discover or Saved and upload its tender PDF for full AI document analysis. Automatic document import is not available.',notifications:'The notifications inbox is not available yet. Configured personal Telegram alerts remain available through Settings.',billing:'Billing and paid plans are not available yet.'};
 function navigate(){const key=location.hash.slice(1)||'overview';const link=document.querySelector(`[data-nav="${CSS.escape(key)}"]`);const page=link?key:'overview';const workspaceContext=document.querySelector('.workspace-context');if(workspaceContext)workspaceContext.hidden=page==='support';document.querySelectorAll('[data-nav]').forEach(n=>n.setAttribute('aria-current',n.dataset.nav===page?'page':'false'));document.querySelectorAll('[data-page]').forEach(n=>n.hidden=n.dataset.page!==page);$('pageHeading').textContent=link?link.textContent:'Overview';$('futurePage').hidden=!future[page];$('futureTitle').textContent=link?.textContent||'';$('futureText').textContent=future[page]||'';const next={recommended:['discover','Open Discover'],'ai-analysis':['discover','Open Discover'],notifications:['settings','Open Telegram settings']};const destination=next[page];$('futureNext').hidden=!destination;if(destination){$('futureNext').href='#'+destination[0];$('futureNext').textContent=destination[1];}else{$('futureNext').removeAttribute('href');$('futureNext').textContent='';}$('appNav').classList.remove('open');$('navToggle').setAttribute('aria-expanded','false');}
 function closeNavigation(returnFocus=false){$('appNav').classList.remove('open');$('navToggle').setAttribute('aria-expanded','false');if(returnFocus)$('navToggle').focus();}
 $('navToggle').onclick=()=>{const open=$('appNav').classList.toggle('open');$('navToggle').setAttribute('aria-expanded',String(open));if(open)$('appNav').querySelector('[aria-current="page"]')?.focus();};
 window.addEventListener('hashchange',()=>{navigate();window.dispatchEvent(new Event('workspace-context'));$('pageHeading').focus();});window.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('appNav').classList.contains('open'))closeNavigation(true);});
 $('appNav').addEventListener('click',e=>{if(e.target.closest('[data-nav]')){closeNavigation();$('pageHeading').focus();}});
 window.matchMedia('(max-width:1050px)').addEventListener('change',()=>closeNavigation());navigate();
})();
/* Workspace lifecycle: drop stale results before organization/company transitions. */
(function(){
 const $=id=>document.getElementById(id);
 state.uiEpoch=0;state.companies=[];state.activeCompanyId=null;state.activeCompanyName='Loading workspace...';
 function publish(){window.dispatchEvent(new Event('workspace-context'));}
 function resetMonitoringUi(){
  state.monitoringStatus=null;

  const values={
   monitorCompany:'Loading...',
   monitorDetails:'',
   monitoringCompany:'Loading...',
   monitoringMode:'Loading...',
   monitoringFeeds:'Loading...',
   monitoringBackground:'Loading...',
   monitoringNotifications:'Loading...',
   monitoringAccess:'Loading...',
   monitoringExplanation:'Loading monitoring status...'
  };

  for(const [id,value] of Object.entries(values)){
   const node=$(id);

   if(node){
    node.textContent=value;
   }
  }

  const summary=$(
   'monitoringScanSummary'
  );

  if(summary){
   summary.replaceChildren();
  }

  const results=$(
   'scanResults'
  );

  if(results){
   results.innerHTML=
    '<div class="empty">Load a workspace to scan for new matching notices.</div>';
  }

  const scan=$(
   'scanButton'
  );

  if(scan){
   scan.disabled=true;
   scan.textContent=
    'Scan for new matches';
  }
 }

 function invalidate(){
  hideCompanyForm();
  resetCompanyForm();

  state.uiEpoch++;
  state.activeCompanyId=null;
  state.hasActiveCompany=false;
  state.companies=[];
  state.activeCompanyName=
   'Loading workspace...';

  for(const id of [
   'companies',
   'tenders'
  ]){
   const node=$(id);

   if(node){
    node.replaceChildren();
   }
  }

  resetMonitoringUi();

  $('onboarding').hidden=true;

  publish();
 }
 for(const name of ['selectOrganization','activateCompany','refreshAll','createOrganization']){const original=window[name];window[name]=async function(...args){invalidate();$('appNotice').textContent='';try{return await original(...args);}catch{$('appNotice').textContent='Workspace could not be loaded. Refresh or choose a workspace again.';}finally{publish();}};}
 window.addEventListener('workspace-context',()=>{$('activeCompanyLabel').textContent=state.activeCompanyName;const loaded=Boolean(state.activeCompanyName)&&!state.activeCompanyName.startsWith('Loading workspace');const currentPage=location.hash.slice(1)||'overview';$('onboarding').hidden=currentPage!=='overview'||!loaded||Boolean(state.activeCompanyId);$('onboardingStart').disabled=!canWriteWorkspace();$('onboardingStart').textContent=usingSharedOrganization()?'Create company':'Set up shared workspace';$('onboardingStart').onclick=()=>{if(usingSharedOrganization()){location.hash='companies';showCompanyForm();}else{location.hash='team';$('newOrganizationName').focus();}};});
 window.addEventListener('unhandledrejection',e=>{$('appNotice').textContent='This action could not be completed. Refresh the workspace and retry.';e.preventDefault();});
})();
