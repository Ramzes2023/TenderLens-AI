/* MAIN geography: bundled outlines only; no tender service or workspace mutations. */
(function () {
  'use strict';
  const root = document.getElementById('geographyWorkspace');
  if (!root) return;
  const t = key => window.MainLocale.t(key);
  const NS = 'http://www.w3.org/2000/svg';
  const node = (tag, cls, parent, svg = false) => {
    const el = svg ? document.createElementNS(NS, tag) : document.createElement(tag);
    if (cls) el.setAttribute('class', cls);
    if (parent) parent.append(el);
    return el;
  };
  const text = (tag, key, parent, cls) => { const el = node(tag, cls, parent); el.dataset.geoText = key; return el; };
  const header = node('header', 'geo-header', root);
  text('span', 'geoEyebrow', header, 'geo-eyebrow');
  text('h2', 'geography', header);
  text('p', 'geoIntro', header);
  const layout = node('div', 'geo-layout', root);
  const main = node('div', 'geo-main', layout);
  const tools = node('div', 'geo-tools', main);
  const label = text('label', 'geoSearch', tools); label.setAttribute('for', 'geoSearch');
  const search = node('input', '', tools); search.id = 'geoSearch'; search.type = 'search'; search.autocomplete = 'off';
  const selectLabel = text('label', 'geoChoose', tools); selectLabel.setAttribute('for', 'geoCountry');
  const select = node('select', '', tools); select.id = 'geoCountry';
  search.setAttribute('aria-controls','geoCountry');
  const controls = node('div', 'geo-controls', tools);
  function button(key, action) { const el = text('button', key, controls); el.type = 'button'; el.addEventListener('click', action); return el; }
  let features = [], paths = [], selected = -1, view = {x:0,y:0,w:1000,h:500}, loadState = 'geoLoading';
  const zoomIn = button('geoZoomIn', () => zoom(1.5));
  const zoomOut = button('geoZoomOut', () => zoom(1 / 1.5));
  const reset = button('geoReset', () => { view = {x:0,y:0,w:1000,h:500}; applyView(); });
  const fit = button('geoFit', () => { if (selected < 0) return; const b = paths[selected].getBBox(); const w = Math.min(1000, Math.max(125, b.width * 1.5, b.height * 3)); view = {x:b.x+b.width/2-w/2,y:b.y+b.height/2-w/4,w,h:w/2}; applyView(); });
  const stage = node('div', 'geo-stage', main);
  const svg = node('svg', 'geo-map', stage, true); svg.setAttribute('viewBox', '0 0 1000 500'); svg.setAttribute('role','group'); svg.setAttribute('tabindex','0');
  const grid = node('g','geo-grid',svg,true); grid.setAttribute('aria-hidden','true');
  for (let x = 0; x <= 1000; x += 1000/12) { const line = node('path','',grid,true); line.setAttribute('d',`M${x} 0V500`); }
  for (let y = 0; y <= 500; y += 500/6) { const line = node('path','',grid,true); line.setAttribute('d',`M0 ${y}H1000`); }
  const land = node('g','geo-land',svg,true);
  const status = node('p','geo-status',main); status.setAttribute('role','status'); status.setAttribute('aria-live','polite');
  text('p','geoHint',main,'geo-hint');
  text('p','geoSource',main,'geo-source');
  const aside = node('aside','geo-details',layout);
  text('span','geoSelection',aside,'geo-eyebrow');
  const country = node('h3','',aside);
  country.id = 'geoSelectedCountry'; aside.setAttribute('aria-labelledby',country.id);
  country.setAttribute('aria-live','polite'); country.setAttribute('aria-atomic','true');
  const codes = node('p','geo-codes',aside);
  text('span','geoUnavailableBadge',aside,'geo-badge');
  text('p','geoUnavailable',aside);
  const ranking = node('div','geo-ranking',aside);
  text('h3','geoRanking',ranking);
  text('p','geoRankingCopy',ranking);
  text('p','geoFuture',ranking,'geo-source');
  function name(f) {
    const code = f.properties.iso_a2;
    if (code && /^[A-Z]{2}$/.test(code)) {
      try { return new Intl.DisplayNames([window.MainLocale.locale], {type:'region'}).of(code) || f.properties.name; } catch (_) {}
    }
    return f.properties.name;
  }
  function selection(index) {
    if (!Number.isInteger(index) || index < -1 || index >= features.length) return;
    selected = index;
    paths.forEach((path,i) => { path.setAttribute('aria-pressed',String(i === index)); path.setAttribute('tabindex',i === (index < 0 ? 0 : index) ? '0' : '-1'); });
    // Map selection must remain representable in the filtered native dropdown.
    if (index >= 0 && !Array.from(select.children).some(option => option.value === String(index))) search.value = '';
    options(); renderDetails();
    fit.disabled = selected < 0;
  }
  function renderDetails() {
    country.textContent = selected < 0 ? t('geoNoSelection') : name(features[selected]);
    codes.textContent = selected < 0 ? t('geoSelectCopy') : `${t('geoCodes')}: ${features[selected].properties.iso_a2 || t('geoMissing')} / ${features[selected].properties.iso_a3 || t('geoMissing')}`;
    select.value = selected < 0 || !Array.from(select.children).some(option => option.value === String(selected)) ? '' : String(selected);
  }
  function options() {
    const query = search.value.trim().toLocaleLowerCase(); select.replaceChildren();
    const placeholder = node('option','',select); placeholder.value = ''; placeholder.textContent = t('geoChoose');
    let matches = 0;
    features.map((f,i) => ({f,i,label:name(f)})).sort((a,b) => a.label.localeCompare(b.label,window.MainLocale.locale)).forEach(({f,i,label}) => {
      if (![label,f.properties.name,f.properties.iso_a2 || '',f.properties.iso_a3 || ''].join(' ').toLocaleLowerCase().includes(query)) return;
      const option = node('option','',select); option.value = String(i); option.textContent = label; matches++;
    });
    select.value = selected < 0 || !Array.from(select.children).some(option => option.value === String(selected)) ? '' : String(selected);
    select.disabled = !matches; search.disabled = !features.length;
    status.textContent = ['geoReady','geoFallback'].includes(loadState) && query && !matches ? t('geoNoMatches') : t(loadState);
  }
  function refresh() {
    root.lang = window.MainLocale.locale;
    root.querySelectorAll('[data-geo-text]').forEach(el => { el.textContent = t(el.dataset.geoText); });
    svg.setAttribute('aria-label',t('geoMapLabel')); svg.setAttribute('aria-describedby', 'geoMapHint');
    root.querySelector('[data-geo-text="geoHint"]').id = 'geoMapHint';
    search.setAttribute('placeholder',t('geoSearchPlaceholder'));
    paths.forEach((path,i) => path.setAttribute('aria-label',name(features[i])));
    options(); renderDetails(); fit.disabled = selected < 0;
    [zoomIn,zoomOut,reset].forEach(el => { el.disabled = !features.length; });
  }
  function applyView() {
    view.x = Math.max(0, Math.min(1000-view.w,view.x)); view.y = Math.max(0,Math.min(500-view.h,view.y));
    svg.setAttribute('viewBox',`${view.x} ${view.y} ${view.w} ${view.h}`);
  }
  function zoom(factor) { const w = Math.max(125,Math.min(1000,view.w/factor)); view = {x:view.x+(view.w-w)/2,y:view.y+(view.h-w/2)/2,w,h:w/2}; applyView(); }
  search.addEventListener('input', options);
  select.addEventListener('change', () => selection(select.value === '' ? -1 : Number(select.value)));
  svg.addEventListener('keydown', e => {
    if (e.target !== svg) return;
    if (e.key === '+' || e.key === '=') { e.preventDefault(); zoom(1.5); }
    else if (e.key === '-') { e.preventDefault(); zoom(1/1.5); }
    else if (['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)) { e.preventDefault(); view.x += (e.key==='ArrowRight'?1:e.key==='ArrowLeft'?-1:0)*view.w/10; view.y += (e.key==='ArrowDown'?1:e.key==='ArrowUp'?-1:0)*view.h/10; applyView(); }
  });
  let drag;
  svg.addEventListener('pointerdown', e => { if (e.target !== svg || e.button !== 0) return; drag = {id:e.pointerId,x:e.clientX,y:e.clientY,v:{...view}}; svg.setPointerCapture(e.pointerId); });
  svg.addEventListener('pointermove', e => { if (!drag || e.pointerId !== drag.id) return; const rect = svg.getBoundingClientRect(); const scale = Math.min(rect.width/view.w,rect.height/view.h); if (!scale) return; view.x = drag.v.x-(e.clientX-drag.x)/scale; view.y = drag.v.y-(e.clientY-drag.y)/scale; applyView(); });
  const stop = () => { drag = null; }; svg.addEventListener('pointerup',stop); svg.addEventListener('pointercancel',stop); svg.addEventListener('lostpointercapture',stop);
  // Split antimeridian polygons by unwrapping and clipping translated copies in the SVG viewport.
  function outline(geometry) {
    const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates;
    return [-1000,0,1000].map(offset => polygons.map(polygon => polygon.map(ring => {
      let previous;
      return ring.map(([lon,lat],i) => { let x = (lon+180)*1000/360; if (previous !== undefined) { while(x-previous>500)x-=1000; while(x-previous < -500)x+=1000; } previous=x; return `${i?'L':'M'}${(x+offset).toFixed(2)} ${((90-lat)*500/180).toFixed(2)}`; }).join(' ')+'Z'; }).join(' ')).join(' ')).join(' ');
  }
  window.addEventListener('shell-locale-change',refresh);
  refresh();
  let usingFallback = false;
  function validOutlines(data) {
    return data?.type === 'FeatureCollection' && data.features?.length && !data.features.some(f => !f.properties?.name || !['Polygon','MultiPolygon'].includes(f.geometry?.type));
  }
  async function loadOutlines() {
    try {
      const response = await fetch('/assets/geography_world.geojson', {credentials:'omit', ...(typeof AbortSignal !== 'undefined' && AbortSignal.timeout ? {signal:AbortSignal.timeout(8000)} : {})});
      if (!response.ok) throw Error('outline');
      const data = await response.json();
      if (!validOutlines(data)) throw Error('outline');
      return data;
    } catch (_) {
      if (validOutlines(window.ValyqonWorldOutlines)) { usingFallback = true; return window.ValyqonWorldOutlines; }
      throw Error('outline');
    }
  }
  loadOutlines().then(data => {
    if (data.type !== 'FeatureCollection' || !data.features?.length || data.features.some(f => !f.properties?.name || !['Polygon','MultiPolygon'].includes(f.geometry?.type))) throw Error('outline');
    // Natural Earth omits France's ISO metadata in this bundle. Correct only the
    // in-memory UI metadata; the source geometry and asset remain untouched.
    features = data.features.map(f => f.properties.name === 'France' && !f.properties.iso_a2 && !f.properties.iso_a3
      ? {...f,properties:{...f.properties,iso_a2:'FR',iso_a3:'FRA'}} : f);
    paths = features.map((f,i) => {
      const path = node('path','geo-country',land,true); path.setAttribute('d',outline(f.geometry)); path.setAttribute('fill-rule','evenodd'); path.setAttribute('role','button'); path.setAttribute('aria-pressed','false'); path.setAttribute('tabindex',i===0?'0':'-1');
      path.addEventListener('click',() => selection(i));
      path.addEventListener('keydown',e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selection(i); } else if (['ArrowRight','ArrowLeft','ArrowDown','ArrowUp','Home','End'].includes(e.key)) { e.preventDefault(); const next = e.key==='Home'?0:e.key==='End'?paths.length-1:(i+(['ArrowLeft','ArrowUp'].includes(e.key)?-1:1)+paths.length)%paths.length; paths.forEach((p,j)=>p.setAttribute('tabindex',j===next?'0':'-1')); paths[next].focus(); } });
      return path;
    });
    loadState = usingFallback ? 'geoFallback' : 'geoReady'; refresh();
  }).catch(() => { features = []; paths = []; land.replaceChildren(); loadState = 'geoError'; refresh(); });
})();
