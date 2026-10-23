/* Dynamic VALYQON visual intelligence. Every plotted point is persisted data. */
(() => {
  'use strict';
  const ns = 'http://www.w3.org/2000/svg';
  const el = id => document.getElementById(id);
  const ru = () => document.documentElement.lang === 'ru';
  const t = (en, russian) => ru() ? russian : en;
  const fmt = n => new Intl.NumberFormat(ru() ? 'ru-RU' : 'en-US').format(n);
  const colors = ['#376df8','#8368e9','#22b6b0','#ffbe62','#698ac6','#b6c7ee'];
  const number = v => Number.isInteger(v) && v >= 0 && v <= 5000;
  const put = (id, value) => { const node = el(id); if (node) node.textContent = value; };
  const make = (tag, cls, label) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (label !== undefined) node.textContent = String(label);
    return node;
  };
  const svgEl = (tag, attrs, title) => {
    const item = document.createElementNS(ns, tag);
    Object.entries(attrs || {}).forEach(([key, val]) => item.setAttribute(key, String(val)));
    if (title) {
      const detail = document.createElementNS(ns, 'title');
      detail.textContent = title;
      item.append(detail);
    }
    return item;
  };

  function drawChart(node, rows, large, name) {
    if (!node) return;
    node.replaceChildren();
    const w = large ? 720 : 450, h = large ? 238 : 124;
    const pad = large ? {l:32,r:16,t:12,b:29} : {l:17,r:9,t:8,b:11};
    const innerW = w - pad.l - pad.r, innerH = h - pad.t - pad.b;
    const max = Math.max(1, ...rows.map(d => d.count));
    node.setAttribute('aria-label', name + ': ' + rows.map(d => d.date + '=' + d.count).join(', '));
    for (let i = 0; i < 4; i++) {
      const y = pad.t + innerH * i / 3;
      node.append(svgEl('line', {x1:pad.l,y1:y,x2:w-pad.r,y2:y,stroke:'#e4eafa','stroke-width':1}));
      if (large) node.append(svgEl('text', {x:pad.l-7,y:y+3,'text-anchor':'end','font-size':10,fill:'#8a99b4'}, fmt(Math.round(max*(3-i)/3))));
    }
    const coords = rows.map((d,i) => ({
      x: pad.l + (rows.length === 1 ? innerW/2 : i * innerW / (rows.length-1)),
      y: pad.t + innerH - (d.count/max) * innerH
    }));
    const defs = svgEl('defs');
    const fill = svgEl('linearGradient',{id:large?'vqxGraphFill':'vqxHeroFill',x1:0,y1:0,x2:0,y2:1});
    fill.append(svgEl('stop',{offset:'0%','stop-color':'#5b85ff','stop-opacity':.23}),
                svgEl('stop',{offset:'100%','stop-color':'#8c9ff5','stop-opacity':0}));
    defs.append(fill);node.append(defs);
    const pathData = coords.map((d,i)=>(i?'L':'M')+d.x.toFixed(2)+','+d.y.toFixed(2)).join(' ');
    if (coords.length) {
      const area = pathData + ' L' + coords[coords.length-1].x + ',' + (pad.t+innerH) +
                   ' L' + coords[0].x + ',' + (pad.t+innerH) + ' Z';
      node.append(svgEl('path',{d:area,fill:'url(#'+(large?'vqxGraphFill':'vqxHeroFill')+')'}));
    }
    if (large) {
      const step=innerW/Math.max(1,rows.length);
      rows.forEach((row,i)=>{
        const barH = Math.max(row.priced ? 2 : 0, row.priced/max*innerH);
        const x=pad.l+i*innerW/Math.max(1,rows.length-1)-step*.17;
        node.append(svgEl('rect',{x:x.toFixed(2),y:(pad.t+innerH-barH).toFixed(2),
          width:Math.max(3,step*.33).toFixed(2),height:barH.toFixed(2),
          rx:3,fill:'#ae96f9',opacity:.65},row.date+': '+fmt(row.priced)+' '+t('priced records','с указанной ценой')));
      });
    }
    if (pathData) node.append(svgEl('path',{d:pathData,fill:'none',stroke:'#396df8',
      'stroke-width':large?3:2.8,'stroke-linecap':'round','stroke-linejoin':'round'}));
    coords.forEach((d,i)=>{
      node.append(svgEl('circle',{cx:d.x.toFixed(2),cy:d.y.toFixed(2),r:large?3:2.3,
        fill:'#fff',stroke:'#346cf6','stroke-width':large?2:1.5},
        rows[i].date+': '+fmt(rows[i].count)+' '+t('new observations','новых извещений')));
      if(large && (i===0||i===rows.length-1||i%3===0))
        node.append(svgEl('text',{x:d.x.toFixed(2),y:h-9,'text-anchor':'middle',
          'font-size':10,fill:'#8195b4'},rows[i].date.slice(5)));
    });
  }

  function addBars(parentId, pairs, options) {
    const parent = el(parentId);
    if (!parent) return;
    parent.replaceChildren();
    const highest = Math.max(1,...pairs.map(x=>x[1]));
    pairs.forEach(([label,value])=>{
      const row = make('div','vqx-hrow');
      const name = make('span','',label);
      const track = make('div','vqx-hbar-track');
      const bar = make('div','vqx-hbar-fill');
      bar.style.width = (value/highest*100).toFixed(2)+'%';
      bar.setAttribute('aria-label',label+': '+fmt(value));
      track.append(bar);
      row.append(name,track,make('strong','',fmt(value)));
      parent.append(row);
    });
  }

  const bands = [
    ['under_1m', '<1m ₽', 'До 1 млн ₽'],
    ['1_to_5m', '1–5m ₽', '1–5 млн ₽'],
    ['5_to_10m', '5–10m ₽', '5–10 млн ₽'],
    ['10_to_50m', '10–50m ₽', '10–50 млн ₽'],
    ['50m_plus', '50m+ ₽', '50+ млн ₽']
  ];
  function drawPriceBand(data) {
    const values=bands.map(([key,en,russian])=>({label:t(en,russian),count:data[key]}));
    const total=values.reduce((sum,item)=>sum+item.count,0);
    put('vqxDonutTotal',fmt(total));
    const donut=el('vqxPriceDonut'), legend=el('vqxPriceLegend'), histogram=el('vqxPriceHistogram');
    if (legend) legend.replaceChildren();
    if (histogram) histogram.replaceChildren();
    let angle=0;const portions=[];
    values.forEach((item,i)=>{
      const pct = total ? (item.count/total*100) : 0;
      if(pct) {portions.push(colors[i]+' '+angle.toFixed(3)+'% '+(angle+pct).toFixed(3)+'%');angle+=pct;}
      if(legend) {
        const row=make('div');
        const color=make('i');color.style.background=colors[i];
        row.append(color,make('span','',item.label),make('strong','',fmt(item.count)));
        legend.append(row);
      }
      if(histogram) {
        const col=make('div','vqx-hist-col'),track=make('div','vqx-hist-track'),bar=make('div','vqx-hist-fill');
        const highest=Math.max(1,...values.map(v=>v.count));
        bar.style.height=(item.count/highest*100).toFixed(2)+'%';
        bar.title=item.label+': '+fmt(item.count);
        track.append(bar);
        col.append(make('strong','',fmt(item.count)),track,make('small','',item.label));
        histogram.append(col);
      }
    });
    if (donut){
      donut.style.background=portions.length?'conic-gradient('+portions.join(', ')+')':'conic-gradient(#e3eaf7 0% 100%)';
      donut.setAttribute('aria-label',t('Real RUB price bands','Диапазоны цен в рублях')+': '+values.map(x=>x.label+' '+x.count).join(', '));
    }
  }
  function drawWeeks(rows) {
    const parent=el('vqxWeeksBars');
    if(!parent) return;
    parent.replaceChildren();
    const values=[rows.previous_7d,rows.latest_7d];
    const max=Math.max(1,...values);
    values.forEach((value,i)=>{
      const column=make('div','vqx-week-col'),track=make('div','vqx-week-track'),fill=make('div','vqx-week-fill');
      fill.style.height=(value/max*100).toFixed(2)+'%';
      fill.title=fmt(value);
      track.append(fill);
      column.append(track,make('strong','',fmt(value)),
        make('small','',i===0?t('Previous 7 days','Предыдущие 7 дней'):t('Latest 7 days','Последние 7 дней')));
      parent.append(column);
    });
  }
  function drawCoverage(fields, total) {
    const parent=el('vqxCoverageBars');if(!parent)return;
    parent.replaceChildren();
    const choices=[['title',t('Title','Название')],['price',t('Price','Цена')],
      ['currency',t('Currency','Валюта')],['deadline',t('Deadline','Срок подачи')]];
    choices.forEach(([key,label])=>{
      const pct=total?100*fields[key]/total:0;
      const card=make('div','vqx-field');
      const track=make('div','vqx-field-track'),fill=make('div','vqx-field-fill');
      fill.style.width=pct.toFixed(1)+'%';
      track.append(fill);
      card.append(make('span','',label),make('strong','',total?pct.toFixed(0)+'%':'—'),track);
      parent.append(card);
    });
  }
  function validReport(data) {
    if(!data || data.scope!=='bounded_persisted_source_observations' ||
       !number(data.scanned_recent_rows) || !number(data.valid_records_in_sample) ||
       !number(data.new_notices_14d) || !number(data.priced_notices) ||
       !number(data.priced_rub_notices) || !Array.isArray(data.daily) ||
       data.daily.length!==14) return false;
    if (!data.daily.every(row=>row && /^\d{4}-\d{2}-\d{2}$/.test(row.date) &&
          number(row.count) && number(row.priced) && row.priced<=row.count))return false;
    for(const key of ['rub_price_bands','deadline_bands','currency_counts','field_coverage','week_comparison']){
      if(!data[key] || typeof data[key]!=='object' ||
         !Object.values(data[key]).every(number))return false;
    }
    return true;
  }
  function render(data) {
    if (!validReport(data)) throw new Error('Unverified report');
    put('vqxHeroTotal',fmt(data.scanned_recent_rows));
    put('vqxHeroFresh',fmt(data.new_notices_14d));
    put('vqxHeroPriced',fmt(data.priced_notices));
    put('vqxStatObserved',fmt(data.scanned_recent_rows));
    put('vqxStatNew',fmt(data.new_notices_14d));
    put('vqxStatPriced',fmt(data.priced_notices));
    put('vqxStatDeadline',fmt(data.field_coverage.deadline));
    const daily=data.daily;
    drawChart(el('vqxHeroLine'),daily,false,t('Saved observations','Сохранённые наблюдения'));
    const dropdown=el('vqxDaysRange');
    const drawRange=()=>{
      const days=dropdown && dropdown.value==='7'?7:14;
      drawChart(el('vqxDailyChart'),daily.slice(-days),true,
        t('Saved observations for the last ','Сохранённые наблюдения за последние ')+days+t(' days',' дней'));
      put('vqxDailyCaption',t('Only first-observed notices in the selected UTC window.','Только впервые сохранённые извещения за выбранный период UTC.'));
    };
    drawRange();
    if(dropdown) dropdown.addEventListener('change',drawRange);
    drawPriceBand(data.rub_price_bands);
    drawWeeks(data.week_comparison);
    const dl=data.deadline_bands;
    addBars('vqxDeadlineBars',[
      [t('Past due','Срок прошёл'),dl.overdue],
      [t('Next 7 days','До 7 дней'),dl.within_7d],
      [t('8–30 days','8–30 дней'),dl['8_to_30d']],
      [t('Over 30 days','Более 30 дней'),dl.over_30d],
      [t('Not specified','Не указано'),dl.unspecified]]);
    addBars('vqxCurrencyBars',Object.entries(data.currency_counts).map(([key,value])=>[
      key==='OTHER'?t('Other','Другие'):key,value]));
    drawCoverage(data.field_coverage,data.valid_records_in_sample);
    put('vqxIntelligenceStatus',data.valid_records_in_sample
      ?t('Figures loaded from stored connector observations.','Показатели загружены из сохранённых извещений.')
      :t('No connector notices in this database yet. No demo values are displayed.','В этой базе пока нет извещений. Демонстрационные значения не подставляются.'));
  }
  const getReport=async()=>{
    try {
      const response=await fetch('/api/v1/public/market-intelligence',{credentials:'omit',
        cache:'no-store',headers:{'Accept':'application/json'}});
      if(!response.ok)throw new Error('Unavailable');
      render(await response.json());
    } catch(_) {
      put('vqxIntelligenceStatus',t('Analytics temporarily unavailable. No estimated values are shown.',
        'Аналитика временно недоступна. Примерные значения не показываются.'));
      const line=el('vqxHeroLine'),chart=el('vqxDailyChart');
      if(line)line.replaceChildren();
      if(chart)chart.replaceChildren();
    }
  };
  getReport();
})();
