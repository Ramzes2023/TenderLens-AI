/* Presentation-only setup guidance. Existing services enforce permissions and tenancy. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const launcher=$('globalSupportLauncher');
  const toolbar=document.querySelector('.product-topbar > .toolbar');
  if(launcher && toolbar)toolbar.append(launcher);
  function link(parent, destination, en, ru) {
    const a = document.createElement('a'); a.href = '#' + destination;
    a.dataset.uiEn = en; a.dataset.uiRu = ru; a.textContent = en;
    parent.append(a); return a;
  }
  const routes = ['discover','search-history','saved','monitoring','source-health','ai-analysis','documents'];
  const gates = [];
  for (const page of routes) {
    const panel = document.querySelector(`[data-page="${page}"]`);
    if (!panel) continue;
    const gate = document.createElement('section'); gate.className = 'setup-guidance';
    gate.setAttribute('aria-label','Workspace setup');
    const p = document.createElement('p');
    p.dataset.uiEn = 'Your personal workspace holds your account. Global discovery requires a shared organization and an active company profile. Set up the organization, add a company with search keywords, then search enabled sources.';
    p.dataset.uiRu = 'Личное пространство содержит ваш аккаунт. Для глобального поиска нужна общая организация и активный профиль компании. Настройте организацию, добавьте компанию с поисковыми словами, затем выполните поиск по доступным источникам.';
    p.textContent = p.dataset.uiEn; p.dataset.setupEn=p.dataset.uiEn; p.dataset.setupRu=p.dataset.uiRu; gate.append(p);
    link(gate,'team','1. Set up organization','1. Настроить организацию');
    link(gate,'companies','2. Set up company profile','2. Настроить профиль компании');
    link(gate,'discover','3. Find opportunities','3. Найти закупки');
    const retry=document.createElement('button'); retry.type='button';
    retry.dataset.uiEn='Refresh workspace'; retry.dataset.uiRu='Обновить рабочую область'; retry.textContent=retry.dataset.uiEn;
    retry.addEventListener('click',()=>refreshAll()); gate.append(retry);
    panel.prepend(gate); gates.push(gate);
  }
  const documents = document.querySelector('[data-page="documents"]');
  if (documents) link(documents,'ai-analysis','Start PDF analysis','Начать анализ PDF');
  function refresh() {
    const ready = Boolean(state.activeCompanyId);
    const loading = String(state.activeCompanyName || '').startsWith('Loading workspace');
    const failed = state.activeCompanyName === 'Workspace unavailable';
    gates.forEach(gate => {
      gate.hidden = ready;
      const p=gate.querySelector('p');
      p.dataset.uiEn=failed?'Workspace failed to load. Refresh before continuing setup.':loading?'Loading workspace. Setup availability has not been checked yet.':p.dataset.setupEn;
      p.dataset.uiRu=failed?'Не удалось загрузить рабочую область. Обновите её перед настройкой.':loading?'Загрузка рабочей области. Доступность настройки ещё не проверена.':p.dataset.setupRu;
      gate.querySelectorAll('a').forEach(a=>{a.hidden=loading||failed;});
      gate.querySelector('button').hidden=!failed;
      gate.parentElement.dataset.setupBlocked=String(!ready);
    });
    for (const id of ['historyCount','savedCount','sourceHealthyCount','sourceFailedCount','sourceDisabledCount','sourceUncheckedCount']) {
      const metric = $(id); if (!metric) continue;
      if (!ready) {
        metric.dataset.uiEn = failed ? 'Workspace unavailable' : loading ? 'Loading…' : 'Company not selected';
        metric.dataset.uiRu = failed ? 'Рабочая область недоступна' : loading ? 'Загрузка…' : 'Компания не выбрана';
      } else { delete metric.dataset.uiEn; delete metric.dataset.uiRu; }
    }
    const center = $('commandCenter');
    if (center) center.querySelectorAll('.command-kpis,.command-grid,.command-scope').forEach(el => { el.hidden = !ready; });
    const access = $('monitoringAccess');
    if (!ready && access) {
      access.dataset.uiEn = 'Company setup required'; access.dataset.uiRu = 'Требуется настройка компании';
      access.textContent = window.MainLocale.locale === 'ru' ? access.dataset.uiRu : access.dataset.uiEn;
    } else if (access) { delete access.dataset.uiEn; delete access.dataset.uiRu; }
    window.MainLocale.refresh();
  }
  window.addEventListener('workspace-context',refresh);
  refresh();
})();
