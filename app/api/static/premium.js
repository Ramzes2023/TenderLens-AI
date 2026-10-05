/* Navigation-only command menu: no implied global search or hidden API calls. */
(function(){
 const $=id=>document.getElementById(id),dialog=$('commandPalette');
 function render(){const query=$('commandQuery').value.trim().toLowerCase();const links=[...document.querySelectorAll('[data-nav]')].filter(a=>a.textContent.trim().toLowerCase().includes(query));$('commandResults').replaceChildren();for(const link of links){const button=document.createElement('button');button.textContent='Go to '+link.textContent.trim();button.onclick=()=>{location.hash=link.dataset.nav;dialog.close();};$('commandResults').append(button);}if(!links.length)$('commandResults').textContent='No matching pages.';}
 function open(){render();dialog.showModal();$('commandQuery').focus();}
 $('openCommands').onclick=open;$('closeCommands').onclick=()=>dialog.close();$('commandQuery').addEventListener('input',render);
 window.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();if(!dialog.open)open();}});
 const system=$('healthBadge')?.closest('article');if(system)system.dataset.page='settings';
 window.addEventListener('workspace-context',()=>{$('sideCompany').textContent=state.activeCompanyName||'Choose a company';});
 window.addEventListener('discovery-report',e=>{const r=e.detail;$('sourcesChecked').textContent=r?String((r.attempted_sources||[]).length):'—';$('lastDiscovery').textContent=r?new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):'Not run';});
 // Reconcile the technical card after initial shell navigation.
 if(system)system.hidden=(location.hash.slice(1)||'overview')!=='settings';
})();
