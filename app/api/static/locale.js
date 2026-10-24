/* Shared locale for authenticated presentation. Workspace state remains locale-neutral. */
(function () {
  'use strict';
  const entries = {
    geoEyebrow: ['GEOGRAPHY INTELLIGENCE', 'ГЕОГРАФИЧЕСКАЯ АНАЛИТИКА'],
    geoIntro: ['Explore country geography and prepare your procurement focus. Map outlines do not indicate tender coverage.', 'Изучайте географию стран и выбирайте направление закупок. Контуры на карте не означают наличие тендерных данных.'],
    geoSearch: ['Search countries', 'Поиск стран'], geoChoose: ['Choose a country', 'Выберите страну'],
    geoSearchPlaceholder: ['Country name or ISO code', 'Название страны или код ISO'],
    geoZoomIn: ['Zoom in +', 'Приблизить +'], geoZoomOut: ['Zoom out −', 'Отдалить −'],
    geoReset: ['Reset world view', 'Вся карта'], geoFit: ['Fit selected country', 'Показать выбранную страну'],
    geoLoading: ['Loading bundled geography…', 'Загрузка локальной карты…'],
    geoReady: ['Geographical background only · Tender metrics unavailable', 'Только географическая подложка · Тендерные метрики недоступны'],
    geoFallback: ['Backup country outlines loaded after an asset failure · Tender metrics unavailable', 'После ошибки загрузки используются резервные контуры стран · Тендерные метрики недоступны'],
    geoError: ['Map outlines could not be loaded. Country tender metrics remain unavailable.', 'Не удалось загрузить контуры карты. Тендерные метрики по странам недоступны.'],
    geoNoMatches: ['No countries match. Try another name or ISO code.', 'Страны не найдены. Попробуйте другое название или код ISO.'],
    geoMapLabel: ['World map: selectable country outlines', 'Карта мира: выбор контуров стран'],
    geoHint: ['Select a country on the map or in the list. On country shapes: arrows to move, Enter or Space to select. On the map background: arrows to pan, +/− to zoom; drag the ocean to pan.', 'Выберите страну на карте или в списке. На контурах: стрелки для перехода, Enter или пробел для выбора. На фоне карты: стрелки для перемещения, +/− для масштаба; перетаскивайте фон океана.'],
    geoSource: ['Source: Natural Earth, public domain, 1:110m generalized outlines. Equirectangular projection. Illustrative geography; not definitive sovereignty or border claims. Small territories may be omitted; names without ISO codes retain the source label.', 'Источник: Natural Earth, общественное достояние, обобщённые контуры 1:110 млн. Равнопромежуточная проекция. Иллюстративная география, не утверждение о суверенитете или границах. Малые территории могут отсутствовать; названия без кодов ISO сохранены из источника.'],
    geoSelection: ['COUNTRY FOCUS', 'ВЫБРАННАЯ СТРАНА'], geoNoSelection: ['Choose your country focus', 'Выберите интересующую страну'],
    geoSelectCopy: ['Use the map or searchable country list to inspect a location.', 'Используйте карту или поиск по списку стран, чтобы выбрать территорию.'],
    geoCodes: ['ISO 2 / 3-letter codes', 'Коды ISO из 2 / 3 букв'], geoMissing: ['Not supplied', 'Не указан'],
    geoUnavailableBadge: ['DATA UNAVAILABLE', 'ДАННЫЕ НЕДОСТУПНЫ'],
    geoUnavailable: ['Country tender metrics unavailable. No verified country tender data is connected in this screen. Missing data does not mean zero tenders.', 'Данные о тендерах по странам пока недоступны. Проверенные тендерные данные по странам к этому экрану не подключены. Отсутствие данных не означает отсутствие тендеров.'],
    geoRanking: ['Geographic ranking', 'Рейтинг стран'],
    geoRankingCopy: ['Country counts and rankings are unavailable. A country cannot be ranked without verified tender metrics.', 'Количество тендеров и рейтинг стран недоступны. Без проверенных тендерных метрик страны нельзя ранжировать.'],
    geoFuture: ['Prepared for future authenticated data wiring after the required production gates pass. No analytics requests are made here.', 'Подготовлено для будущего подключения данных с авторизацией после прохождения обязательных производственных проверок. Запросы к аналитике здесь не выполняются.'],
    geography: ['Geography Intelligence', 'География закупок'],
    overview: ['Overview', 'Обзор'], discover: ['Discover', 'Поиск'],
    'search-history': ['Search History', 'История поиска'], recommended: ['Recommended', 'Рекомендации'],
    saved: ['Saved', 'Сохранённое'], 'tender-planner': ['Tender Planner', 'Планировщик'], monitoring: ['Monitoring', 'Мониторинг'],
    'source-health': ['Source Health', 'Состояние источников'], 'ai-analysis': ['AI Analysis', 'ИИ-анализ'],
    documents: ['Documents', 'Документы'], companies: ['Companies', 'Компании'],
    notifications: ['Notifications', 'Уведомления'], team: ['Team', 'Команда'],
    billing: ['Billing', 'Оплата'], support: ['Support', 'Поддержка'], settings: ['Settings', 'Настройки'],
    Workspace: ['Workspace', 'Рабочая область'], Intelligence: ['Intelligence', 'Аналитика'],
    Organization: ['Organization', 'Организация'], System: ['System', 'Система'],
    skip: ['Skip to content', 'Перейти к содержимому'], menu: ['Menu', 'Меню'],
    tagline: ['Find. Analyze. Score. Win.', 'Находите. Анализируйте. Оценивайте. Побеждайте.'],
    navigation: ['Main navigation', 'Основная навигация'], active: ['Active company', 'Активная компания'],
    choose: ['Choose a company', 'Выберите компанию'], loading: ['Loading workspace...', 'Загрузка рабочей области…'],
    none: ['No active company', 'Нет активной компании'], help: ['Help & support', 'Помощь и поддержка'],
    eyebrow: ['PROCUREMENT WORKSPACE', 'РАБОЧАЯ ОБЛАСТЬ ЗАКУПОК'],
    subtitle: ['Global Procurement Intelligence powered by AI', 'Глобальная аналитика закупок с ИИ'],
    open: ['Go to workspace...', 'Перейти к разделу…'], openAria: ['Open workspace navigation', 'Открыть навигацию по разделам'],
    account: ['Account', 'Аккаунт'], accountLoading: ['Loading account...', 'Загрузка аккаунта…'],
    workspaceSettings: ['Workspace settings', 'Настройки рабочей области'], docs: ['API documentation', 'Документация API'],
    refresh: ['Refresh workspace', 'Обновить рабочую область'], logout: ['Sign out', 'Выйти'],
    manage: ['Switch / manage company', 'Выбрать / настроить компанию'],
    palette: ['Go to workspace', 'Перейти к разделу'],
    paletteCopy: ['Navigation only - this does not search tenders or buyers.', 'Только навигация: поиск закупок и заказчиков не выполняется.'],
    query: ['Find a page', 'Найти раздел'], close: ['Close', 'Закрыть'],
    go: ['Go to ', 'Перейти: '], noPages: ['No matching pages.', 'Подходящие разделы не найдены.'],
    language: ['Language', 'Язык'],
    unavailable: ['Workspace unavailable', 'Рабочая область недоступна'],
    scope: ['Language applies to workspace controls. Official source names and customer content retain their original language.', 'Язык применяется к элементам рабочей области. Названия официальных источников и пользовательские данные сохраняются в исходном виде.']
  };
  const dictionary = Object.freeze(Object.fromEntries(Object.entries(entries).map(([key, pair]) => [key, Object.freeze({en: pair[0], ru: pair[1]})])));
  let locale = 'en';
  try { if (localStorage.getItem('valyqon.shell.locale') === 'ru') locale = 'ru'; } catch (_) { /* Storage may be disabled. */ }
  function t(key, fallback = key) { return dictionary[key]?.[locale] || dictionary[key]?.en || fallback; }
  const bindings = [
    ['.skip-link','skip'], ['#navToggle','menu'], ['#appNav > .fine','tagline'],
    ['#appNav nav','navigation','aria-label'], ['.sidebar-context small','active'],
    ['.sidebar-context a','help'], ['.product-heading .eyebrow','eyebrow'],
    ['.product-subtitle','subtitle'], ['#openCommands','openAria','aria-label'],
    ['.notification-link','notifications'], ['.account-menu summary','account'],
    ['.account-menu a[href="#settings"]','workspaceSettings'], ['.account-menu a[href="/docs"]','docs'],
    ['.account-menu button[onclick="refreshAll()"]','refresh'], ['.account-menu button[onclick="logout()"]','logout'],
    ['.workspace-context > div > .fine','active'], ['.workspace-context a[href="#companies"]','manage'],
    ['#commandTitle','palette'], ['#commandPalette p','paletteCopy'], ['label[for="commandQuery"]','query'],
    ['#closeCommands','close'], ['#shellLocaleLabel','language'], ['#shellLocaleScope','scope'],
    ['#shellLocale','language','aria-label']
  ];
  const setText = (node, text) => { if (node && node.textContent !== text) node.textContent = text; };
  function refresh() {
    document.documentElement.lang = locale;
    document.querySelectorAll('[data-ui-en][data-ui-ru]').forEach(node => {
      setText(node,locale === 'ru' ? node.dataset.uiRu : node.dataset.uiEn);
      node.lang = locale;
    });
    for (const [selector,key,attribute] of bindings) {
      document.querySelectorAll(selector).forEach(node => {
        if (attribute) { if (node.getAttribute(attribute) !== t(key)) node.setAttribute(attribute,t(key)); }
        else setText(node,t(key));
      });
    }
    document.querySelectorAll('[data-nav]').forEach(node => setText(node.querySelector('span'),t(node.dataset.nav)));
    document.querySelectorAll('.nav-group-label').forEach((node,index) => setText(node,t(['Workspace','Intelligence','Organization','System'][index])));
    const current = document.querySelector('[data-nav][aria-current="page"]');
    setText(document.getElementById('pageHeading'),t(current?.dataset.nav || 'overview'));
    setText(document.getElementById('futureTitle'),t(current?.dataset.nav || 'overview'));
    // Preserve the shortcut child and existing click handler.
    const trigger = document.getElementById('openCommands');
    if (trigger?.firstChild?.nodeType === 3 && trigger.firstChild.nodeValue.trim() !== t('open')) trigger.firstChild.nodeValue = t('open') + ' ';
    const company = typeof state !== 'undefined' ? state : null;
    const name = company?.activeCompanyName;
    const label = name?.startsWith('Loading workspace') ? t('loading') : !name ? t('choose') : !company?.activeCompanyId && name === 'No active company' ? t('none') : name === 'Workspace unavailable' ? t('unavailable') : name;
    setText(document.getElementById('sideCompany'),label);
    const activeLabel = document.getElementById('activeCompanyLabel');
    setText(activeLabel,label);
    if (activeLabel) activeLabel.lang = locale;
    const email = document.getElementById('email');
    if (email && ['Loading account...',entries.accountLoading[1]].includes(email.textContent.trim())) setText(email,t('accountLoading'));
    document.querySelectorAll('[data-page],#orgControl,#futurePage,#appNotice,#globalSupportPanel,#globalSupportLauncher').forEach(node => { if(node.lang !== locale) node.lang = locale; });
    const select = document.getElementById('shellLocale');
    if (select) select.value = locale;
  }
  function setLocale(value) {
    if (!['en','ru'].includes(value)) return false;
    locale = value;
    try { localStorage.setItem('valyqon.shell.locale',locale); } catch (_) {}
    refresh();
    window.dispatchEvent(new Event('shell-locale-change'));
    return true;
  }
  window.MainLocale = Object.freeze({t,setLocale,refresh,dictionary,get locale(){return locale;}});
  document.getElementById('shellLocale')?.addEventListener('change',event => setLocale(event.target.value));
  // Reconcile only presentation after asynchronous renderers; never publish workspace events.
  new MutationObserver(refresh).observe(document.body,{childList:true,subtree:true,characterData:true});
  window.addEventListener('workspace-context',refresh);
  window.addEventListener('hashchange',refresh);
  refresh();
})();
