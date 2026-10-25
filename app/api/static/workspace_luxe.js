/* Progressive navigation enhancements: no API data, fake counts or new permissions. */
(() => {
  'use strict';
  const menu=document.getElementById('appNav');
  const collapse=document.getElementById('vqSidebarCompact');
  const openPalette=document.getElementById('openCommands');
  if(!menu || !collapse)return;
  const storeKey='valyqon.workspace.nav.v1';
  const isDesktop=()=>window.matchMedia('(min-width:761px)').matches;
  const state={compact:false,collapsed:{}};
  try{
    const saved=JSON.parse(localStorage.getItem(storeKey)||'{}');
    if(typeof saved==='object'&&saved){
      state.compact=saved.compact===true;
      if(saved.collapsed && typeof saved.collapsed==='object'){
        for(const name of ['Workspace','Intelligence','Organization','System']){
          state.collapsed[name]=saved.collapsed[name]===true;
        }
      }
    }
  }catch(_){/* Storage may be disabled, navigation still works. */}
  const save=()=>{
    try{localStorage.setItem(storeKey,JSON.stringify(state));}catch(_){}
  };
  const groups=[];
  menu.querySelectorAll('.nav-group').forEach((group,index)=>{
    const label=group.querySelector('.nav-group-label');
    if(!label)return;
    const key=label.textContent.trim();
    const items=[...group.querySelectorAll(':scope > a[data-nav]')];
    if(!items.length)return;
    const list=document.createElement('div');
    list.className='nav-group-links';
    list.id='vqNavGroup'+index;
    items.forEach(link=>{
      link.title=link.textContent.trim();
      link.setAttribute('aria-label',link.textContent.trim());
      list.append(link);
    });
    const button=document.createElement('button');
    button.type='button';
    button.className='nav-group-toggle';
    button.setAttribute('aria-controls',list.id);
    button.setAttribute('aria-expanded','true');
    const text=document.createElement('span');
    text.textContent=key;
    const arrow=document.createElement('span');
    arrow.className='vq-chevron';
    arrow.setAttribute('aria-hidden','true');
    arrow.textContent='⌄';
    button.append(text,arrow);
    label.replaceWith(button);
    group.append(list);
    groups.push({button,list,key,items});
    button.addEventListener('click',()=>{
      if(document.body.classList.contains('sidebar-compact'))return;
      const open=button.getAttribute('aria-expanded')!=='true';
      state.collapsed[key]=!open;
      button.setAttribute('aria-expanded',String(open));
      list.hidden=!open;
      save();
    });
  });
  function updateCompact(){
    const enabled=state.compact && isDesktop();
    document.body.classList.toggle('sidebar-compact',enabled);
    collapse.setAttribute('aria-pressed',String(enabled));
    collapse.setAttribute('aria-label',enabled?'Expand sidebar':'Collapse sidebar');
    collapse.title=enabled?'Expand sidebar':'Collapse sidebar';
    groups.forEach(({list,button})=>{
      if(enabled){list.hidden=false;button.setAttribute('aria-expanded','true');}
    });
  }
  function reflectRoute(){
    const route=location.hash.slice(1)||'overview';
    menu.querySelectorAll('.nav-group').forEach(g=>g.classList.remove('is-active-group'));
    groups.forEach(({key,list,button,items})=>{
      const active=items.some(link=>link.dataset.nav===route);
      if(active)button.closest('.nav-group').classList.add('is-active-group');
      const open=active||!state.collapsed[key]||state.compact&&isDesktop();
      list.hidden=!open;
      button.setAttribute('aria-expanded',String(open));
    });
    document.querySelectorAll('.vq-workspace-shortcuts a[href^="#"]').forEach(link=>{
      const active=link.getAttribute('href')==='#'+route;
      link.setAttribute('aria-current',active?'page':'false');
    });
  }
  collapse.addEventListener('click',()=>{
    state.compact=!state.compact;
    save();
    updateCompact();
    reflectRoute();
  });
  const actionCommand=document.getElementById('vqActionCommand');
  if(actionCommand&&openPalette)actionCommand.addEventListener('click',()=>openPalette.click());
  window.addEventListener('hashchange',reflectRoute);
  window.matchMedia('(min-width:761px)').addEventListener('change',()=>{
    updateCompact();
    reflectRoute();
  });
  updateCompact();
  reflectRoute();
})();
