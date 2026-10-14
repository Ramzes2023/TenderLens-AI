'use strict';
(function(){
const names=['Discovered','Matched','High Fit','Active Sources','Countries','Closing Soon'];
const bands=['high','medium','low','unknown'];
function count(n){if(!Number.isSafeInteger(n)||n<0)throw Error('invalid count');return n;}
function width(n,d){count(n);count(d);return d===0?0:Math.min(100,Math.max(0,n/d*100));}
function key(i){if(!Array.isArray(i)||i.length!==2||!i.every(x=>typeof x==='string'))throw Error('identity');return JSON.stringify(i);}
function model(r){
 const out=[];const population=new Set(r.U.map(key));if(population.size!==r.U.length)throw Error('duplicate U');
 function metric(name,m,kind){count(m.numerator);count(m.denominator);if(m.value!==null)count(m.value);if(m.numerator>m.denominator)throw Error('denominator');if(!Array.isArray(m.identities))throw Error('identities');if(['distinct_successfully_reached_source','distinct_supported_country'].includes(m.unit)&&(m.identities.some(i=>typeof i!=='string'||!i)||new Set(m.identities).size!==m.numerator||m.identities.length!==m.numerator))throw Error('distinct membership');if(kind==='fit'||m.unit==='unique_tender_identity'){if(m.identities.length!==m.numerator||new Set(m.identities.map(key)).size!==m.numerator||m.identities.some(i=>!population.has(key(i))))throw Error('membership');}return {name,value:m.value,n:m.numerator,d:m.denominator,ids:m.identities,reason:m.reason,kind,unit:m.unit};}
 for(const name of names)out.push(metric(name,r.kpis[name],'kpi'));
 const known=new Set();let denominator=null;
 for(const band of bands.slice(0,3)){const m=metric('Fit '+band,r.fit_bands[band],'fit');if(denominator!==null&&denominator!==m.d)throw Error('fit denominator');denominator=m.d;for(const i of m.ids){if(known.has(key(i)))throw Error('overlap');known.add(key(i));}out.push(m);}
 if(known.size!==denominator)throw Error('known population');
 const unknown=Object.values(r.unknown_fit).flat();if(new Set(unknown.map(key)).size!==unknown.length||unknown.some(i=>!population.has(key(i))||known.has(key(i)))||unknown.length+known.size!==population.size)throw Error('unknown population');
 out.push({name:'Fit unknown',value:unknown.length,n:unknown.length,d:r.U.length,ids:unknown,kind:'fit',reason:'unavailable historical evidence'});
 for(const [kind,day,ids] of r.deadline_grouping.buckets){if(!['instant','date_only'].includes(kind)||!/^\d{4}-\d{2}-\d{2}$/.test(day))throw Error('deadline type');if(ids.some(i=>!population.has(key(i))))throw Error('deadline membership');out.push({name:kind+' · '+day,value:ids.length,n:ids.length,d:r.U.length,ids,kind:'deadline',type:kind,day});}
 for(const [type,state,ids] of r.deadline_grouping.states){if(ids.some(i=>!population.has(key(i))))throw Error('state membership');out.push({name:type+' / '+state,value:ids.length,n:ids.length,d:r.U.length,ids,kind:'state',type,state});}
 return out;
}
function rows(r){model(r);const fits=new Map(r.fits.map(f=>[key(f.identity),f]));return r.U.map(identity=>{const id=key(identity),f=fits.get(id);if(!f||!bands.includes(f.historical_band))throw Error('fit row');const states=r.deadline_grouping.states.filter(x=>x[2].some(i=>key(i)===id)).map(x=>x[0]+' / '+x[1]);const dates=r.deadline_grouping.buckets.filter(x=>x[2].some(i=>key(i)===id)).map(x=>x[1]);return {identity,id,text:identity.join(' / '),band:f.historical_band,current:f.current_band,reason:f.current_reason,states,dates};});}
function project(rs,q='',band='',deadline='',sort='identity',selected=null){let out=rs.filter(x=>x.text.toLowerCase().includes(q.trim().toLowerCase())&&(!band||x.band===band)&&(!deadline||x.states.includes(deadline))&&(!selected||selected.has(x.id)));return out.sort((a,b)=>{if(sort==='fit')return bands.indexOf(a.band)-bands.indexOf(b.band)||a.text.localeCompare(b.text);if(sort==='deadline')return (a.dates[0]||'9999').localeCompare(b.dates[0]||'9999')||a.text.localeCompare(b.text);return (sort==='identity-desc'?-1:1)*a.text.localeCompare(b.text);});}
function arcs(ms){const known=ms.filter(x=>x.kind==='fit'&&x.name!=='Fit unknown');let offset=0;return known.map(m=>{const length=width(m.n,m.d);const a={name:m.name,length,offset};offset=Math.min(100,offset+length);return a;});}
// P4A: projections consume only the frozen worker allowlist; never stored items.
function analyticsEvidence(r){
 if(typeof r.population_id!=='string'||!r.population_id||!Array.isArray(r.scope)||r.scope.length!==2||r.scope.some(n=>!Number.isSafeInteger(n)||n<0)||typeof r.context.timezone!=='string'||!r.context.timezone||!Number.isFinite(Date.parse(r.context.as_of)))throw Error('projection context');
 const ms=model(r),population=r.U.map(i=>i.slice()),members=new Set(population.map(key));
 const copy=ids=>ids.map(i=>Array.isArray(i)?i.slice():i);
 function group(label,ids,d,unit='unique_tender_identity'){
  count(d);count(ids.length);const tokens=ids.map(i=>unit==='unique_tender_identity'?key(i):String(i));
  if(new Set(tokens).size!==ids.length||ids.length>d||unit==='unique_tender_identity'&&tokens.some(i=>!members.has(i)))throw Error('projection membership');
  return {label,identities:copy(ids),numerator:ids.length,denominator:d,unit};
 }
 const provenance={population_id:r.population_id,scope:r.scope.slice(),as_of:r.context.as_of,timezone:r.context.timezone,coverage:r.coverage,sample_window:r.sample_window.slice()};
 const available=(basis,groups,missing='explicit_separate_groups')=>({status:'available',basis,missing,groups});
 const unavailable=reason=>({status:'unavailable',basis:'selected_U',missing:reason,groups:null,numerator:null,denominator:population.length,unit:'unique_tender_identity'});
 const sources=new Map();for(const i of population){if(!sources.has(i[0]))sources.set(i[0],[]);sources.get(i[0]).push(i);}
 const events=new Map(),eventIds=new Set();count(r.observed_events);
 for(const e of r.selected_events){
  if(!Array.isArray(e)||e.length!==3||!Number.isSafeInteger(e[0])||e[0]<0||eventIds.has(e[0])||typeof e[1]!=='string'||!/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(e[1])||!Number.isFinite(Date.parse(e[1]))||typeof e[2]!=='string'||! /^[a-f0-9]{64}$/.test(e[2]))throw Error('event manifest');
  eventIds.add(e[0]);const day=new Date(e[1]).toISOString().slice(0,10);if(!events.has(day))events.set(day,[]);events.get(day).push(e[0]);
 }
 if(eventIds.size>r.observed_events)throw Error('event denominator');
 const seenBuckets=new Set(),bucketIds=new Set(),stateIds=new Set();
 const deadlines=ms.filter(m=>m.kind==='deadline').map(m=>{
  if(new Date(m.day+'T00:00:00Z').toISOString().slice(0,10)!==m.day||seenBuckets.has(m.type+'/'+m.day))throw Error('calendar date');
  seenBuckets.add(m.type+'/'+m.day);for(const i of m.ids){if(bucketIds.has(key(i)))throw Error('duplicate deadline');bucketIds.add(key(i));}
  return {...group(m.day,m.ids,population.length),type:m.type,day:m.day};
 });
 const states=ms.filter(m=>m.kind==='state').map(m=>{
  if(!['instant','date_only','unknown'].includes(m.type)||!['closing_soon','future','past','missing','invalid','unavailable','conflicting'].includes(m.state))throw Error('deadline state');
  for(const i of m.ids){if(stateIds.has(key(i)))throw Error('duplicate state');stateIds.add(key(i));}
  return {...group(m.state,m.ids,population.length),type:m.type};
 });
 if(stateIds.size!==population.length||r.deadline_grouping.population_id!==r.population_id)throw Error('deadline population');
 const fit=ms.filter(m=>m.kind==='fit').map(m=>group(m.name.split(' ')[1],m.ids,m.d));
 const known=fit.slice(0,3).flatMap(g=>g.identities);
 return {provenance,population:group('U',population,population.length),
  activity:available('selected_events_UTC_days',Array.from(events).sort(([a],[b])=>a.localeCompare(b)).map(([day,ids])=>group(day,ids,eventIds.size,'selected_history_event')),'unobserved_days_not_inferred'),
  sources:available('selected_U_identity_source',Array.from(sources).sort(([a],[b])=>a.localeCompare(b)).map(([s,ids])=>group(s,ids,population.length)),'identity_source_known_not_source_health'),
  countries:unavailable('country_identity_mapping_not_allowlisted'),categories:unavailable('classification_identity_mapping_not_allowlisted'),
  deadlines:available('worker_typed_local_day_buckets',deadlines,'outside_window_and_unknown_in_states'),deadlineStates:available('worker_deadline_states',states),
  fit:available('historical_known_bands_unknown_separate',fit),coverage:available('selected_U',[
   group('historical_fit_known',known,population.length),group('historical_fit_unknown',fit[3].identities,population.length)
  ]),observed_events:r.observed_events};
}
// One explicit key inventory: every entry supplies both locales. Never borrow a language.
const dictionary={
widgets:{"en":"Local smart widgets","ru":"Локальные умные виджеты"},
topRecords:{"en":"Top opportunities · exact test records","ru":"Приоритетные предложения · точные тестовые записи"},
topBasis:{"en":"Historical bands first, then identity. Unknown remains separate. No titles, values or predicted wins.","ru":"Сначала исторические группы, затем идентификатор. Неизвестные отдельно. Без названий, сумм и прогнозов победы."},
completeness:{"en":"Assessment evidence coverage","ru":"Покрытие доказательствами оценок"},
recentActivity:{"en":"Recent historical search activity","ru":"Последние исторические события поиска"},
activityBasis:{"en":"Stored selected search events, newest first. Events are not new opportunities; no missing days are inferred.","ru":"Сохранённые выбранные события поиска, сначала последние. События не означают новые предложения; пропущенные дни не достраиваются."},
eventLabel:{"en":"Historical search event","ru":"Историческое событие поиска"},
activityEmpty:{"en":"Insufficient evidence: no stored dated search events.","ru":"Недостаточно доказательств: нет сохранённых датированных событий поиска."},
sourceObservations:{"en":"Source observations","ru":"Наблюдения источников"},
nextAction:{"en":"Next: inspect exact identities and compare historical evidence. Country, CPV and financial analysis require additional evidence.","ru":"Далее: изучите точные записи и сравните исторические доказательства. Для анализа стран, CPV и финансов нужны дополнительные доказательства."},
selectedFilters:{"en":"Selected filters","ru":"Выбранные фильтры"},
clearFilter:{"en":"Clear filter","ru":"Убрать фильтр"},
recordDetails:{"en":"Selected identity evidence","ru":"Доказательства выбранной записи"},
closeDetails:{"en":"Close identity details","ru":"Закрыть доказательства записи"},
recordHint:{"en":"Select an exact record to inspect its immutable evidence.","ru":"Выберите точную запись для просмотра неизменных доказательств."},
recordSource:{"en":"Identity source code","ru":"Код источника записи"},
noScores:{"en":"Insufficient evidence: numeric scores, country, CPV, title and financial values are not supplied for this record.","ru":"Недостаточно доказательств: числовые оценки, страна, CPV, название и финансовые значения этой записи не предоставлены."},
chartActivity:{en:'Tender activity trend',ru:'Динамика закупок'},chartGeography:{en:'Geographic distribution',ru:'География закупок'},chartSources:{en:'Source breakdown',ru:'Распределение по источникам'},chartIndustry:{en:'Industry / CPV breakdown',ru:'Отрасли / CPV'},insufficient:{en:'Insufficient evidence',ru:'Недостаточно доказательств'},trendMissing:{en:'Dated history events cannot be mapped to exact tender identities. A tender trend is unavailable; no days or new opportunities are inferred.',ru:'Датированные события истории нельзя связать с точными закупками. Динамика закупок недоступна; дни и новые предложения не достраиваются.'},countryMissing:{en:'Country codes are observed, but no country-to-record mapping exists. Geographic shares cannot be calculated.',ru:'Коды стран наблюдаются, но связи стран с записями нет. Доли по географии нельзя рассчитать.'},industryMissing:{en:'Per-record classification is unavailable. Industry shares and missing coverage cannot be calculated.',ru:'Классификации отдельных записей нет. Доли отраслей и отсутствующее покрытие нельзя рассчитать.'},sourceBasis:{en:'Historical observed identities / frozen population. This is not live source health.',ru:'Исторически наблюдаемые записи / фиксированная выборка. Это не текущая доступность источников.'},sourceEmpty:{en:'Confirmed empty population: 0 records. No source distribution.',ru:'Подтверждённая пустая выборка: 0 записей. Распределения по источникам нет.'},sourceGroup:{en:'Observed source',ru:'Наблюдаемый источник'},calendarScale:{en:'Bar length: records / frozen population. Only evidenced dates; unknown and outside-window states below.',ru:'Длина полосы: записи / фиксированная выборка. Только подтверждённые даты; неизвестные и вне окна — ниже.'},

analyticsUnavailable:{en:'Countries and industry distribution: Insufficient evidence. Per-record country and classification evidence is unavailable in this frozen result.',ru:'Распределение стран и отраслей: недостаточно доказательств. В этом фиксированном результате нет стран и классификаций отдельных записей.'},
loading:{en:'Preparing local test data…',ru:'Подготовка локальных тестовых данных…'},
coverageGraphic:{en:'Outer track: known assessments / whole population',ru:'Внешний контур: известные оценки / вся выборка'},
keyboardEvidence:{en:'Select with Enter or Space to inspect exact identities',ru:'Нажмите ввод или пробел для просмотра точных сущностей'},
bucketGraphic:{en:'One node per evidenced date; spacing does not represent elapsed time',ru:'Один узел на подтверждённую дату; расстояние не означает длительность'},
'context.Discovered':{en:'Observed tender identities',ru:'Наблюдаемые сущности закупок'},
'context.Matched':{en:'Supported matching evidence',ru:'Подтверждённые совпадения'},
'context.High Fit':{en:'Preliminary historical relevance',ru:'Предварительная историческая релевантность'},
'context.Active Sources':{en:'Historical source observations',ru:'Исторические наблюдения источников'},
'context.Countries':{en:'Supported country evidence',ru:'Подтверждённые страны'},
'context.Closing Soon':{en:'Exact instants in frozen window',ru:'Точные моменты в фиксированном окне'},

pageTitle:{en:'VALYQON AI · Procurement intelligence',ru:'VALYQON AI · Аналитика закупок'},
brandLine:{en:'PROCUREMENT INTELLIGENCE',ru:'АНАЛИТИКА ЗАКУПОК'},nav:{en:'Workspace sections',ru:'Разделы рабочего пространства'},
navOverview:{en:'01 Overview',ru:'01 Обзор'},navFit:{en:'02 Relevance',ru:'02 Релевантность'},navDeadlines:{en:'03 Deadlines',ru:'03 Сроки'},navRecords:{en:'04 Records',ru:'04 Записи'},navEvidence:{en:'05 Evidence',ru:'05 Доказательства'},
lab:{en:'Local laboratory · Synthetic dataset · P3.9 PARTIAL · P4 public rollout BLOCKED · P5 DISABLED',ru:'Локальная лаборатория · Синтетическая выборка · P3.9 ЧАСТИЧНО · Публичный запуск P4 ЗАБЛОКИРОВАН · P5 НЕ ВКЛЮЧЁН'},
command:{en:' / Command center',ru:' / Центр управления'},badge:{en:'OFFLINE TEST FIXTURE — NO CUSTOMER DATA',ru:'АВТОНОМНАЯ ТЕСТОВАЯ ВЫБОРКА — НЕ ДАННЫЕ КЛИЕНТА'},
language:{en:'Language',ru:'Язык'},chooseEn:{en:'Select English',ru:'Выбрать английский'},chooseRu:{en:'Select Russian',ru:'Выбрать русский'},scenario:{en:'Scenario',ru:'Сценарий'},
overview:{en:'OVERVIEW / PINNED TEST POPULATION',ru:'ОБЗОР / ЗАКРЕПЛЁННАЯ ТЕСТОВАЯ ВЫБОРКА'},hero:{en:'Procurement. Relevance. Evidence.',ru:'Закупки. Оценки. Доказательства.'},
heroCopy:{en:'Historical relevance and deadlines in one workspace. Fictional history; no connected organization or live tender search.',ru:'Историческая релевантность и сроки в одном пространстве. Вымышленная история; без подключённой организации и поиска реальных закупок.'},
scope:{en:'TEST ONLY · Observed storage',ru:'ТОЛЬКО ТЕСТ · Наблюдаемое хранилище'},six:{en:'Six indicators',ru:'Шесть показателей'},fitAxis:{en:'01 / RELEVANCE ANALYSIS',ru:'01 / АНАЛИЗ РЕЛЕВАНТНОСТИ'},fitHeading:{en:'Relevance profile',ru:'Профиль релевантности'},historical:{en:'Historical',ru:'Исторические оценки'},
fitCopy:{en:'High Fit is preliminary historical relevance, not win probability. The ring includes known assessments only. Unknown assessments use the whole population as denominator.',ru:'Высокая релевантность — предварительная историческая оценка, не вероятность победы. Кольцо: только известные оценки. Неизвестные — отдельно относительно всей выборки.'},
table:{en:'Text distribution table',ru:'Текстовая таблица распределения'},group:{en:'Group',ru:'Группа'},fraction:{en:'Numerator / denominator',ru:'Числитель / знаменатель'},deadlineAxis:{en:'02 / DEADLINES',ru:'02 / СРОКИ'},deadlineHeading:{en:'Deadline window',ru:'Окно сроков'},frozen:{en:'Frozen window',ru:'Закреплённое окно'},
deadlineCopy:{en:'Closing Soon counts exact instants only. Calendar dates have a separate track. Days without evidence are not inferred.',ru:'Показатель «Скоро завершатся» учитывает только точное время. Календарная дата — отдельный трек. Дни без доказательств не достраиваются.'},
explorerAxis:{en:'03 / OPPORTUNITY EXPLORER',ru:'03 / ОБОЗРЕВАТЕЛЬ ЗАКУПОК'},explorerHeading:{en:'Explore records',ru:'Исследовать записи'},testData:{en:'TEST DATA',ru:'ТЕСТОВЫЕ ДАННЫЕ'},
explorerCopy:{en:'Filter previously calculated test records. Indicators remain fixed; assessments are not recalculated.',ru:'Фильтр по уже рассчитанным тестовым записям. Показатели остаются фиксированными; оценки не пересчитываются.'},
search:{en:'Search by identity',ru:'Поиск по идентификатору'},searchHint:{en:'For example, ted / high',ru:'Например, ted / high'},historicalFit:{en:'Historical relevance',ru:'Историческая релевантность'},allFits:{en:'All assessments',ru:'Все оценки'},deadlineEvidence:{en:'Deadline evidence',ru:'Доказательство срока'},order:{en:'Order',ru:'Порядок'},identityUp:{en:'Identity ↑',ru:'Идентификатор ↑'},identityDown:{en:'Identity ↓',ru:'Идентификатор ↓'},dateUp:{en:'Window date ↑',ru:'Дата окна ↑'},reset:{en:'Reset',ru:'Сбросить'},
evidenceAxis:{en:'04 / EVIDENCE INSPECTOR',ru:'04 / ИНСПЕКТОР ДОКАЗАТЕЛЬСТВ'},evidenceHeading:{en:'Selected group evidence',ru:'Основание выбранной группы'},retry:{en:'Render again',ru:'Повторить отображение'},technical:{en:'Technical details: provenance, commitment, policies',ru:'Технические детали: происхождение, контрольная сумма, политики'},
evidenceCopy:{en:'0 is a confirmed zero. “No data” means insufficient evidence. Source observations do not indicate current availability. This fixture has no titles, CPV, amounts or win probability.',ru:'0 — подтверждённый ноль. «Нет данных» — недостаточно доказательств. Наблюдения источников не означают доступность сейчас. Названий, CPV, сумм и вероятности победы в выборке нет.'},
footer:{en:'VALYQON AI / OFFLINE TEST FIXTURE · P3.9 PARTIAL · P4 public rollout BLOCKED · P5 DISABLED',ru:'VALYQON AI / АВТОНОМНАЯ ТЕСТОВАЯ ВЫБОРКА · P3.9 ЧАСТИЧНО · Публичный запуск P4 ЗАБЛОКИРОВАН · P5 НЕ ВКЛЮЧЁН'},
'scenario.normal':{en:'Normal · 4 records',ru:'Основной · 4 записи'},'scenario.empty':{en:'Empty history',ru:'Пустая история'},'scenario.unknown':{en:'Missing assessments',ru:'Нет оценок'},'scenario.legacy':{en:'Legacy evidence',ru:'Старые доказательства'},'scenario.foreign':{en:'Different profile',ru:'Другой профиль'},'scenario.future':{en:'Future evidence',ru:'Будущие доказательства'},'scenario.filtered':{en:'Pinned ted/zero',ru:'Фиксированный ted/zero'},
'kpi.Discovered':{en:'Discovered',ru:'Найдено закупок'},'kpi.Matched':{en:'Matched',ru:'Релевантные оценки'},'kpi.High Fit':{en:'High Fit',ru:'Высокая релевантность'},'kpi.Active Sources':{en:'Active Sources',ru:'Успешные источники'},'kpi.Countries':{en:'Countries',ru:'Страны'},'kpi.Closing Soon':{en:'Closing Soon',ru:'Скоро завершатся'},
'fit.high':{en:'High relevance',ru:'Высокая релевантность'},'fit.medium':{en:'Medium relevance',ru:'Средняя релевантность'},'fit.low':{en:'Low relevance',ru:'Низкая релевантность'},'fit.unknown':{en:'Unknown relevance',ru:'Нет оценки'},'fit.unavailable':{en:'Unavailable relevance',ru:'Оценка недоступна'},
noData:{en:'No data',ru:'Нет данных'},whole:{en:'whole population',ru:'вся выборка'},known:{en:'known historical assessments',ru:'известные исторические оценки'},tenders:{en:'tenders',ru:'закупки'},sources:{en:'observed sources',ru:'наблюдаемые источники'},countries:{en:'countries',ru:'страны'},units:{en:'indicator units',ru:'единицы показателя'},
entities:{en:'Exact identities',ru:'Точные сущности'},commitment:{en:'Population commitment',ru:'Контрольная сумма выборки'},coverage:{en:'Coverage',ru:'Охват'},reason:{en:'Reason',ru:'Причина'},unspecified:{en:'Not specified',ru:'Не указана'},sourceDrill:{en:'These are sources/countries, not tender identities. Record selection is unchanged.',ru:'Это источники/страны, не идентификаторы закупок. Отбор записей не изменён.'},opened:{en:'Opened group',ru:'Открыта группа'},explorer:{en:'Record explorer',ru:'Обозреватель записей'},of:{en:'of',ru:'из'},records:{en:'population records · Indicators fixed',ru:'записей выборки · Показатели фиксированы'},empty:{en:'No records for this selection. Reset filters or change the scenario.',ru:'Нет записей для текущего выбора. Сбросьте фильтры или смените сценарий.'},open:{en:'Open',ru:'Открыть'},pair:{en:'Exact source / notice identity pair',ru:'Точная пара: источник / идентификатор извещения'},noGrouping:{en:'No grouping',ru:'Нет группировки'},noDate:{en:'No window date',ru:'Дата окна отсутствует'},origin:{en:'H · TEST FIXTURE',ru:'H · ТЕСТОВАЯ ВЫБОРКА'},currentFit:{en:'Current relevance',ru:'Текущая релевантность'},ringAria:{en:'Known historical relevance distribution; unknown shown separately',ru:'Распределение известных исторических оценок; неизвестные отдельно'},knownCaption:{en:'known assessments',ru:'известных оценок'},allStates:{en:'All states',ru:'Все состояния'},pinned:{en:'Independent pinned scenario',ru:'Независимый закреплённый сценарий'},snapshot:{en:'Snapshot',ru:'Срез'},timezone:{en:'Timezone',ru:'Часовой пояс'},history:{en:'History',ru:'История'},testScope:{en:'Test scope',ru:'Тестовый охват'},days:{en:'days',ru:'дней'},selectEvidence:{en:'Select an indicator, relevance group, deadline or record. Previous selection cleared.',ru:'Выберите показатель, группу релевантности, срок или запись. Предыдущий выбор очищен.'},noDates:{en:'No dates in the pinned window',ru:'Нет дат в закреплённом окне'},observed:{en:'Observed sources / countries',ru:'Наблюдаемые источники / страны'},values:{en:'values',ru:'значения'},error:{en:'Test data contract error. Data cleared. Rebuild the local test file.',ru:'Ошибка контракта тестовых данных. Данные очищены. Повторите сборку локального тестового файла.'},cleared:{en:'Selection cleared.',ru:'Выбор очищен.'},storageDenied:{en:'Language saving is unavailable in this browser. Your choice works for this page only.',ru:'Браузер не разрешает сохранить язык. Выбор действует только на этой странице.'},
'instant':{en:'Exact time',ru:'Точное время'},'date_only':{en:'Calendar date',ru:'Календарная дата'},'unavailable':{en:'Unavailable',ru:'Недоступно'},'future':{en:'Future',ru:'В будущем'},'past':{en:'Past',ru:'В прошлом'},'missing':{en:'Missing',ru:'Отсутствует'},'invalid':{en:'Invalid',ru:'Некорректно'},'unknown':{en:'Unknown',ru:'Неизвестно'},'in_window':{en:'Within window',ru:'В окне'},'outside_window':{en:'Outside window',ru:'Вне окна'},'undated':{en:'Undated',ru:'Без даты'},
'coverage.complete_observed_storage':{en:'Complete observed storage',ru:'Полный охват наблюдаемого хранилища'},
closing_soon:{en:'Closing soon',ru:'Скоро завершится'},
'reason.missing_or_malformed_score':{en:'Missing or malformed assessment',ru:'Оценка отсутствует или некорректна'},
'reason.missing_provenance':{en:'Missing provenance',ru:'Нет доказательств происхождения'},
'reason.scope_mismatch':{en:'Profile scope mismatch',ru:'Профиль не соответствует охвату'},
'reason.version_conflict':{en:'Evidence version conflict',ru:'Конфликт версий доказательств'},
'reason.no_supported_instant_deadline_evidence':{en:'No supported exact-time deadline evidence',ru:'Нет подтверждённых сроков с точным временем'},
'reason.no_eligible_preview_scores':{en:'No eligible preview assessments',ru:'Нет подходящих предварительных оценок'},
clearGroup:{en:'Clear selected group',ru:'Сбросить выбранную группу'},backRecords:{en:'Back to records',ru:'Вернуться к записям'},frozenPopulation:{en:'Frozen indicator population',ru:'Фиксированная выборка показателей'},technicalReference:{en:'See collapsed technical details',ru:'См. свёрнутые технические детали'},
'organization':{en:'Fictional organization',ru:'Вымышленная организация'},'company':{en:'Fictional company',ru:'Вымышленная компания'},
'reason.unavailable historical evidence':{en:'Historical evidence unavailable',ru:'Исторические доказательства недоступны'}
};
function translate(locale,k){const entry=dictionary[k],v=entry&&entry[locale];if(!['en','ru'].includes(locale)||typeof v!=='string'||!v)throw Error(locale==='ru'?'Отсутствует перевод':'Missing translation');return v;}
function validateDictionary(){for(const k of Object.keys(dictionary))for(const l of ['en','ru'])translate(l,k);return true;}
function initialLanguage(storage){try{const l=storage.getItem('valyqon.preview.language');return l==='ru'?'ru':'en';}catch(e){return 'en';}}
validateDictionary();
if(typeof module!=='undefined')module.exports={analyticsEvidence,count,width,model,names,rows,project,arcs,key,dictionary,translate,validateDictionary,initialLanguage};
if(typeof document==='undefined')return;
const $=id=>document.getElementById(id);const data=JSON.parse($('fixture').textContent);let r,rs=[],selected=null,active=null,locale='en',storageBlocked=false,recordId=null,controls=[];
try{locale=initialLanguage(localStorage);localStorage.getItem('valyqon.preview.language');}catch(e){storageBlocked=true;}
const t=k=>translate(locale,k),number=n=>new Intl.NumberFormat(locale).format(n);
function date(value,instant=false){return new Intl.DateTimeFormat(locale,{timeZone:instant?r.context.timezone:'UTC',year:'numeric',month:'short',day:'numeric',...(instant?{hour:'2-digit',minute:'2-digit',second:'2-digit'}:{})}).format(new Date(instant?value:value+'T00:00:00Z'));}
function el(tag,text){const e=document.createElement(tag);if(text!==undefined)e.textContent=String(text);return e;}
function title(m){if(m.kind==='record')return m.name;if(m.kind==='coverage')return t(m.name);if(m.kind==='source')return t('sourceGroup')+' · '+m.name;if(m.kind==='kpi')return t('kpi.'+m.name);if(m.kind==='fit')return t('fit.'+m.name.split(' ')[1]);if(m.kind==='deadline')return t(m.type)+' · '+date(m.day);return stateLabel(m.name);}
function stateLabel(v){return v.split(' / ').map(t).join(' / ');}
function idsText(ids){return ids.map(i=>Array.isArray(i)?i.join(' / '):i).join(', ')||'—';}
function basis(m){return number(m.n)+' / '+number(m.d)+' · '+t(m.kind==='fit'?(m.name==='Fit unknown'?'whole':'known'):m.kind==='kpi'?({'unique_tender_identity':'tenders','distinct_successfully_reached_source':'sources','distinct_supported_country':'countries'}[m.unit]||'units'):'whole');}
function reason(v){return v?t('reason.'+v):t('unspecified');}
function inspect(m){recordId=m.kind==='record'?key(m.ids[0]):null;if(m.kind!=='record')active=m;if(m.kind!=='record')selected=(m.kind!=='kpi'||m.unit==='unique_tender_identity')&&m.ids.every(Array.isArray)?new Set(m.ids.map(key)):null;$('detail').textContent=title(m)+' · '+(m.value===null?t('noData'):number(m.value))+' · '+basis(m)+' · '+t('entities')+': '+idsText(m.ids)+' · '+t('commitment')+': '+t('technicalReference')+' · '+t('coverage')+': '+t('coverage.'+r.coverage)+' · '+t('reason')+': '+reason(m.reason)+(m.kind==='kpi'&&m.unit!=='unique_tender_identity'?' · '+t('sourceDrill'):'');if(m.kind!=='record')resetInputs();syncControls();renderRecords();$('status').textContent=t('opened')+': '+title(m);}
function syncControls(){for(const [b,m]of controls)b.setAttribute('aria-pressed',String(active===m));$('clear-group').disabled=!active;}function resetInputs(){for(const id of ['search','fit-filter','deadline-filter'])$(id).value='';$('sort').value='identity';}
function renderRecords(){renderChips();const focused=document.activeElement;const focusedId=focused&&focused.getAttribute?focused.getAttribute('data-record-id'):null;const subset=project(rs,$('search').value,$('fit-filter').value,$('deadline-filter').value,$('sort').value,selected);if(recordId&&!subset.some(x=>x.id===recordId)){recordId=null;$('detail').textContent=active?title(active)+' · '+basis(active):t('cleared');}renderIdentity();$('records').replaceChildren();$('subset').textContent=t('explorer')+': '+number(subset.length)+' '+t('of')+' '+number(rs.length)+' '+t('records')+' · '+t('frozenPopulation')+': '+number(rs.length)+(active?' · '+t('group')+': '+title(active):'');if(!subset.length)$('records').append(el('p',t('empty')));for(const x of subset){const b=el('button');b.className='record'+(recordId===x.id?' selected':'');b.setAttribute('aria-label',t('open')+' '+x.text);b.setAttribute('aria-pressed',String(recordId===x.id));b.setAttribute('data-record-id',x.id);const id=el('span');id.append(el('strong',x.text),el('small',t('pair')));const fit=el('span',t('fit.'+x.band));fit.className='pill '+x.band;const deadline=el('span',x.states.map(stateLabel).join(' · ')||t('noGrouping'));deadline.append(el('small',x.dates.map(v=>date(v)).join(', ')||t('noDate')));const origin=el('span',t('origin'));origin.append(el('small',t('currentFit')+': '+t('fit.'+x.current)+' · '+reason(x.reason)));b.append(id,fit,deadline,origin);b.addEventListener('click',()=>inspect({name:x.text,value:1,n:1,d:rs.length,ids:[x.identity],kind:'record',reason:x.reason}));$('records').append(b);if(focusedId===x.id&&b.focus)b.focus();}}
function button(m,cls){const b=el('button');b.className=cls;b.setAttribute('aria-label',title(m)+' · '+basis(m));b.setAttribute('title',title(m)+' · '+basis(m)+' · '+t('keyboardEvidence'));b.setAttribute('aria-controls','records detail');b.setAttribute('aria-pressed','false');controls.push([b,m]);b.addEventListener('click',()=>inspect(m));return b;}
function svgNode(tag,attrs){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v]of Object.entries(attrs)){if(typeof v==='number'&&!Number.isFinite(v))throw Error('geometry');e.setAttribute(k,String(v));}return e;}
function renderRing(ms){const a=arcs(ms),svg=svgNode('svg',{viewBox:'0 0 220 220',role:'img','aria-label':t('ringAria')});svg.append(svgNode('circle',{cx:110,cy:110,r:78,fill:'none',stroke:'#203650','stroke-width':18}));const colors=['#65a8ff','#65d9ed','#566d8b'];a.forEach((x,i)=>{if(x.length)svg.append(svgNode('circle',{cx:110,cy:110,r:78,fill:'none',stroke:colors[i],'stroke-width':18,pathLength:100,'stroke-dasharray':x.length+' '+(100-x.length),'stroke-dashoffset':-x.offset,transform:'rotate(-90 110 110)'}));});const text=svgNode('text',{x:110,y:110,'text-anchor':'middle'});text.textContent=number(ms.find(x=>x.name==='Fit high').d);const caption=svgNode('text',{x:110,y:131,'text-anchor':'middle',class:'caption'});caption.textContent=t('knownCaption');svg.append(text,caption);const known=ms.find(x=>x.name==='Fit high').d,whole=ms.find(x=>x.name==='Fit unknown').d;
svg.append(svgNode('circle',{cx:110,cy:110,r:98,fill:'none',stroke:'#59472c','stroke-width':4}));
const coverageLength=width(known,whole);if(coverageLength)svg.append(svgNode('circle',{cx:110,cy:110,r:98,fill:'none',stroke:'#65d9ed','stroke-width':4,pathLength:100,'stroke-dasharray':coverageLength+' '+(100-coverageLength),transform:'rotate(-90 110 110)'}));
$('ring').append(svg,el('p',t('coverageGraphic')+' · '+number(known)+' / '+number(whole)));
}

function renderSources(p){
 const host=$('chart-sources');
 if(!p.groups.length){host.append(el('p',t('sourceEmpty')));return;}
 for(const g of p.groups){
  const m={name:g.label,value:g.numerator,n:g.numerator,d:g.denominator,ids:g.identities,kind:'source'};
  const b=button(m,'source-row');b.setAttribute('data-source',g.label);
  b.append(el('span',g.label),el('strong',number(m.n)+' / '+number(m.d)));
  const svg=svgNode('svg',{viewBox:'0 0 300 12',class:'source-scale','aria-hidden':'true'});
  svg.append(svgNode('rect',{x:0,y:0,width:300,height:12,rx:6,fill:'#1b3048'}),svgNode('rect',{x:0,y:0,width:width(m.n,m.d)*3,height:12,rx:6,fill:'#65d9ed'}));
  b.append(svg);host.append(b);
 }
}

function renderIdentity(){
 const host=$('identity-body');host.replaceChildren();const x=rs.find(x=>x.id===recordId);
 if(!x){host.append(el('p',t('recordHint')));return;}
 const b=el('button',t('closeDetails'));b.setAttribute('aria-controls','identity-body');
 b.addEventListener('click',()=>{recordId=null;renderRecords();const target=Array.from($('records').children).find(b=>b.getAttribute('data-record-id')===x.id);if(target&&target.focus)target.focus();});
 host.append(el('h3',x.text),el('p',t('recordSource')+': '+x.identity[0]),el('p',t('historicalFit')+': '+t('fit.'+x.band)),el('p',t('currentFit')+': '+t('fit.'+x.current)+' · '+reason(x.reason)),el('p',t('deadlineEvidence')+': '+x.states.map(stateLabel).join(' · ')+' · '+(x.dates.map(v=>date(v)).join(', ')||t('noDate'))),el('p',t('snapshot')+': '+date(r.context.as_of,true)+' · '+r.context.timezone),el('p',t('noScores')),b);
}
function renderChips(){
 const host=$('filter-chips');host.replaceChildren();
 for(const [id,label]of [['search','search'],['fit-filter','historicalFit'],['deadline-filter','deadlineEvidence']]){
  const v=$(id).value;if(!v)continue;
  const text=t(label)+(id==='search'?'':': '+(id==='fit-filter'?t('fit.'+v):stateLabel(v)));
  const b=el('button',text+' ×');b.setAttribute('data-clear-filter',id);b.setAttribute('aria-label',t('clearFilter')+' · '+text);
  b.addEventListener('click',()=>{$(id).value='';renderRecords();if($(id).focus)$(id).focus();});host.append(b);
 }
 if(active){const b=el('button',title(active)+' ×');b.setAttribute('data-clear-filter','group');b.setAttribute('aria-label',t('clearFilter')+' · '+title(active));b.addEventListener('click',()=>{selected=null;active=null;recordId=null;syncControls();$('detail').textContent=t('cleared');renderRecords();if($('clear-group').focus)$('clear-group').focus();});host.append(b);}
}
function renderWidgets(p){
 for(const x of project(rs,'','','','fit')){
  const b=el('button',x.text+' · '+t('fit.'+x.band));b.setAttribute('data-widget-id',x.id);b.setAttribute('aria-label',t('open')+' '+x.text);b.setAttribute('aria-controls','records detail identity-body');
  b.addEventListener('click',()=>{inspect({name:x.text,value:1,n:1,d:rs.length,ids:[x.identity],kind:'record',reason:x.reason});const target=Array.from($('records').children).find(b=>b.getAttribute('data-record-id')===x.id);if(target&&target.focus)target.focus();else if($('identity-panel').focus)$('identity-panel').focus();});$('top-records').append(b);
 }
 if(!rs.length)$('top-records').append(el('p',t('empty')));
 for(const g of p.coverage.groups){const m={name:g.label==='historical_fit_known'?'known':'fit.unknown',kind:'coverage',value:g.numerator,n:g.numerator,d:g.denominator,ids:g.identities};
  const b=button(m,'coverage-row');b.setAttribute('data-coverage',g.label);const label=t(g.label==='historical_fit_known'?'known':'fit.unknown');b.setAttribute('aria-label',label+' · '+number(g.numerator)+' / '+number(g.denominator));b.append(el('span',label),el('strong',number(g.numerator)+' / '+number(g.denominator)));$('widget-coverage').append(b);
 }
 $('widget-coverage').append(el('p',t('analyticsUnavailable')));
 const events=r.selected_events.slice().sort((a,b)=>Date.parse(b[1])-Date.parse(a[1])||a[0]-b[0]);
 for(const e of events){const row=el('p',t('eventLabel')+' · '+number(e[0])+' · '+date(e[1],true));row.setAttribute('data-event-id',String(e[0]));$('widget-activity').append(row);}
 if(!events.length)$('widget-activity').append(el('p',t('activityEmpty')));
 for(const g of p.sources.groups){const b=button({name:g.label,kind:'source',value:g.numerator,n:g.numerator,d:g.denominator,ids:g.identities},'observation-row');b.setAttribute('data-observed-source',g.label);b.append(el('span',g.label),el('strong',number(g.numerator)+' / '+number(g.denominator)));$('widget-sources').append(b);}
 if(!p.sources.groups.length)$('widget-sources').append(el('p',t('sourceEmpty')));
}

function staticText(){if(document.documentElement)document.documentElement.lang=locale;for(const [attribute,target]of [['data-i18n',null],['data-i18n-loading',null],['data-i18n-aria','aria-label'],['data-i18n-placeholder','placeholder']])for(const node of document.querySelectorAll('['+attribute+']')){const value=t(node.getAttribute(attribute));if(target)node.setAttribute(target,value);else node.textContent=value;}for(const l of ['en','ru'])if($('lang-'+l))$('lang-'+l).setAttribute('aria-pressed',String(locale===l));if($('storage-note'))$('storage-note').textContent=storageBlocked?t('storageDenied'):'';}
function scenarios(){const v=$('scenario').value||'normal';$('scenario').replaceChildren();for(const k of Object.keys(data.cases)){const o=el('option',t('scenario.'+k));o.value=k;$('scenario').append(o);}$('scenario').value=v;}
const clearIds=['cards','fit','ring','deadline','deadline-states','rows','provenance','context','detail','records','observations','window','subset','chart-sources','top-records','widget-coverage','widget-activity','widget-sources','filter-chips','identity-body'];
function render(){recordId=null;controls=[];$('clear-group').disabled=true;for(const id of clearIds)$(id).replaceChildren();r=null;rs=[];selected=null;active=null;resetInputs();$('deadline-filter').replaceChildren(el('option',t('allStates')));$('deadline-filter').children[0].value='';try{const scenario=$('scenario').value;r=data.cases[scenario];const ms=model(r);const analytics=analyticsEvidence(r);rs=rows(r);$('status').textContent=t('scenario.'+scenario)+' · '+t('pinned');$('context').textContent=t('snapshot')+': '+date(r.context.as_of,true)+' · '+t('timezone')+': '+r.context.timezone+' · '+t('history')+' ['+r.sample_window.map(v=>date(v,true)).join(', ')+') · '+t('testScope')+' · '+t('organization')+' '+r.scope[0]+' / '+t('company')+' '+r.scope[1];$('window').textContent=number(r.context.days)+' '+t('days')+' · '+t('snapshot')+' '+date(r.context.as_of,true)+' · '+r.context.timezone;$('detail').textContent=t('selectEvidence');
for(const m of ms.filter(x=>x.kind==='kpi')){const b=button(m,'card'+(['High Fit','Closing Soon'].includes(m.name)?' priority':''));b.append(el('span',title(m)),el('strong',m.value===null?t('noData'):number(m.value)),el('small',basis(m)),el('small',t('context.'+m.name)));b.setAttribute('data-metric',String(names.indexOf(m.name)));$('cards').append(b);}
renderWidgets(analytics);renderSources(analytics.sources);renderRing(ms);for(const m of ms.filter(x=>x.kind==='fit')){const b=button(m,'legend-item '+m.name.split(' ')[1]);const label=el('span');const dot=el('span');dot.className='dot';label.append(dot,el('span',title(m)));b.append(label,el('small',basis(m)));$('fit').append(b);const tr=el('tr');tr.append(el('td',title(m)),el('td',basis(m)));$('rows').append(tr);}
for(const type of ['instant','date_only']){const track=el('div');track.className='deadline-track '+type;track.append(el('h3',t(type)));const groups=ms.filter(x=>x.kind==='deadline'&&x.type===type).sort((a,b)=>a.day.localeCompare(b.day));if(!groups.length)track.append(el('p',t('noDates')));for(const m of groups){const b=button(m,'deadline-row');b.setAttribute('data-day',m.day);b.setAttribute('data-deadline-type',type);b.append(el('span',date(m.day)),el('strong',number(m.n)));
const glyph=svgNode('svg',{viewBox:'0 0 160 24','aria-hidden':'true',class:'deadline-glyph'});
glyph.append(svgNode('rect',{x:0,y:0,width:width(m.n,m.d)*1.6,height:24,rx:4,fill:type==='instant'?'#163d50':'#403420'}),svgNode('path',{d:'M 4 12 L 156 12',fill:'none',stroke:'#315272','stroke-width':2}),svgNode('circle',{cx:80,cy:12,r:6,fill:type==='instant'?'#65d9ed':'#e3b665',stroke:'#07101f','stroke-width':2}));b.append(glyph);track.append(b);}track.append(el('small',t('bucketGraphic')));$('deadline').append(track);}
for(const m of ms.filter(x=>x.kind==='state')){const b=button(m,'state');b.append(el('span',title(m)+' · '+number(m.n)));$('deadline-states').append(b);const option=el('option',title(m));option.value=m.name;$('deadline-filter').append(option);}
$('observations').textContent=t('observed')+': '+idsText(r.kpis['Active Sources'].identities)+' / '+idsText(r.kpis.Countries.identities)+' · '+t('values')+': '+(r.kpis['Active Sources'].value===null?t('noData'):number(r.kpis['Active Sources'].value))+' / '+(r.kpis.Countries.value===null?t('noData'):number(r.kpis.Countries.value));$('observations').append(el('p',t('analyticsUnavailable')));$('provenance').textContent=JSON.stringify({fixture_sha256:data.fixture_sha256,case:scenario,...r,analytics},null,2);syncControls();renderRecords();
}catch(e){r=null;rs=[];selected=null;active=null;recordId=null;controls=[];syncControls();for(const id of clearIds)$(id).replaceChildren();$('status').textContent=t('error');}}
function switchLanguage(next){const filters=['search','fit-filter','deadline-filter','sort'].map(id=>[id,$(id).value]);locale=next;try{localStorage.setItem('valyqon.preview.language',locale);}catch(e){storageBlocked=true;}staticText();scenarios();render();if(r){for(const [id,v]of filters)$(id).value=v;renderRecords();}}
for(const l of ['en','ru'])if($('lang-'+l))$('lang-'+l).addEventListener('click',()=>switchLanguage(l));
$('scenario').addEventListener('change',render);$('retry').addEventListener('click',render);for(const id of ['search','fit-filter','deadline-filter','sort'])$(id).addEventListener(id==='search'?'input':'change',()=>{if(r)renderRecords();});$('reset').addEventListener('click',()=>{selected=null;active=null;recordId=null;resetInputs();syncControls();$('detail').textContent=t('cleared');if(r)renderRecords();});
$('clear-group').addEventListener('click',()=>{selected=null;active=null;recordId=null;syncControls();if(r)renderRecords();$('detail').textContent=t('cleared');});$('back-records').addEventListener('click',()=>{const target=$('records').children[0];if(target&&target.focus)target.focus();if($('explorer').scrollIntoView)$('explorer').scrollIntoView({block:'start'});});const nav=Array.from(document.querySelectorAll('nav a'));for(const a of nav)a.addEventListener('click',()=>{for(const n of nav)n.removeAttribute('aria-current');a.setAttribute('aria-current','location');});staticText();scenarios();render();
})();
