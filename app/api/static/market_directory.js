/* Public procurement source directory — metadata, not a live-uptime claim. */
(() => {
  'use strict';
  const root = document.getElementById('sourceDirectory');
  if (!root) return;
  const $ = id => document.getElementById(id);
  let records = [];
  let state = 'loading';
  const section = $('sourceRegion');
  const search = $('sourceSearch');
  const catalog = $('sourceCards');
  const message = $('sourceDirectoryStatus');
  const count = $('sourceDirectoryCount');
  const active = $('sourceEnabledCount');
  const mapPins = Array.from(root.querySelectorAll('[data-map-region]'));
  const regionalCountries = {
    europe: ['EU','GB','UK','FR','DE','IT','ES','NL','NO','SE','CH','PL','BE','AT','IE','PT','FI','DK','CZ','RO','GR','HU','SK','SI','HR','BG','LT','LV','EE'],
    asia: ['AE','HK','JP','SG','IN','TR','CN','KR','SA','QA','MY','ID','TH','VN','PH','PK','BD','TW'],
    americas: ['US','CA','BR','MX','CL','CO','PE','AR'],
    africa: ['ZA','NG','KE','EG','MA','GH'],
    oceania: ['AU','NZ']
  };
  function regionOf(item){
    if(item.region==='russia'||item.region==='cis')return item.region;
    const code=String(item.country||'').toUpperCase();
    for(const [group,countries] of Object.entries(regionalCountries)){
      if(countries.includes(code))return group;
    }
    return 'other';
  }

  const translate = key => window.PublicLocale ? PublicLocale.t(key) : key;
  function el(tag, cls, txt) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (txt !== undefined) node.textContent = txt;
    return node;
  }
  function render() {
    const region = section.value;
    const term = search.value.trim().toLocaleLowerCase();
    const filtered = records.filter(item =>
      (region === 'all' || item.region === region || regionOf(item) === region) &&
      [item.name, item.country, item.key].join(' ').toLocaleLowerCase().includes(term)
    );
    catalog.replaceChildren();
    for (const item of filtered) {
      const card = el('article','source-directory-card');
      const top = el('div','source-directory-head');
      const flag = el('span','source-country',item.country);
      const labels = el('div','source-directory-names');
      labels.append(el('h3','',item.name),el('small','',item.key));
      top.append(flag,labels);
      const tags = el('div','source-tags');
      tags.append(
        el('span','source-tag',item.official ? translate('Government or official') : translate('Marketplace or commercial')),
        el('span','source-tag',item.focus === 'regional_small' ? translate('Regional / small procurement') : item.transport.toUpperCase()),
        el('span','source-tag',item.enabled ? translate('Configured for use') : translate('Not enabled'))
      );
      const note = el('p','source-directory-note',translate('Live delivery is not verified by this directory.'));
      card.append(top,tags,note);
      if (item.homepage) {
        const a = el('a','source-official-link',translate('Official source website') + ' ↗');
        a.href = item.homepage;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        card.append(a);
      }
      catalog.append(card);
    }
    if (!filtered.length) {
      catalog.append(el('p','source-empty',state === 'error' ?
        translate('Unable to load source registry right now.') :
        translate('No sources match these filters.')));
    }
    message.textContent = state === 'error'
      ? translate('Unable to load source registry right now.')
      : translate('Showing') + ' ' + filtered.length + ' ' +
        translate('registered adapters. Availability requires a separate check.');
    for(const button of mapPins){
      const selected=button.dataset.mapRegion===region;
      button.setAttribute('aria-pressed', String(selected));
      button.classList.toggle('is-selected',selected);
    }
    count.textContent = String(records.length);
    active.textContent = String(records.filter(x=>x.enabled).length);
  }
  for(const button of mapPins){
    button.addEventListener('click',()=>{
      const selected=button.dataset.mapRegion;
      if(!Array.from(section.options).some(option=>option.value===selected))return;
      section.value=selected;
      render();
      root.querySelector('#sourceDirectoryStatus').scrollIntoView({block:'nearest',behavior:'auto'});
    });
  }
  section.addEventListener('change',render);
  search.addEventListener('input',render);
  document.querySelectorAll('[data-public-locale]').forEach(button=>
    button.addEventListener('click',() => queueMicrotask(render))
  );
  fetch('/public/source-directory.json',{credentials:'omit',cache:'no-store'})
    .then(async response=>{
      if (!response.ok) throw new Error('source registry unavailable');
      const data = await response.json();
      if (!Array.isArray(data.sources)) throw new Error('source registry malformed');
      records = data.sources.filter(item=>
        typeof item.key === 'string' && typeof item.name === 'string' &&
        typeof item.country === 'string' && typeof item.region === 'string'
      );
      state = 'ready';
      render();
    })
    .catch(()=>{state='error';render();});
})();
