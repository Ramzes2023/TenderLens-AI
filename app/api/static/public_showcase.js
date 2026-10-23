/* Original VALYQON public interactions. No fake tenders, mock API data or arbitrary HTML. */
(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const ru = () => document.documentElement.lang === 'ru';
  const t = (en, rus) => ru() ? rus : en;
  const create = (tag, className, label) => {
    const x = document.createElement(tag);
    if (className) x.className = className;
    if (label !== undefined) x.textContent = label;
    return x;
  };
  const stages = {
    discover: {
      title: ['Find opportunities that match your focus', 'Находите закупки по вашему запросу'],
      description: [
        'Search persisted procurement notices, then open a qualified workspace for the evidence.',
        'Ищите сохранённые объявления и изучайте подтверждённые сведения в рабочем кабинете.'
      ]
    },
    assess: {
      title: ['Understand requirements and missing data', 'Оценивайте требования и полноту данных'],
      description: [
        'Review metadata and any documents you upload. An AI fit score is never a win guarantee.',
        'Проверяйте сведения и загруженные документы. Оценка соответствия не гарантирует победу.'
      ]
    },
    coordinate: {
      title: ['Keep your team aligned on the next step', 'Согласовывайте решения с командой'],
      description: [
        'Use shared organizations, access roles and deliberate actions to review procurement work.',
        'Работайте в общей организации, распределяйте роли и согласовывайте действия по закупкам.'
      ]
    }
  };
  const title = el('vqStageTitle');
  const desc = el('vqStageDescription');
  if (title && desc) {
    document.querySelectorAll('[data-vq-step]').forEach(button => {
      button.addEventListener('click', () => {
        const data = stages[button.dataset.vqStep];
        if (!data) return;
        title.textContent = data.title[ru() ? 1 : 0];
        desc.textContent = data.description[ru() ? 1 : 0];
        document.querySelectorAll('[data-vq-step]').forEach(peer => {
          const active = peer === button;
          peer.classList.toggle('is-active', active);
          peer.setAttribute('aria-pressed', String(active));
        });
      });
    });
    document.querySelectorAll('[data-public-locale]').forEach(button => {
      button.addEventListener('click', () => {
        const active = document.querySelector('[data-vq-step][aria-pressed="true"]');
        if (active) active.click();
      });
    });
  }

  const chart = el('vqPulseChart'), total = el('vqPulseTotal'),
        sample = el('vqPulseSample'), status = el('vqPulseStatus'),
        range = el('vqPulseRange');
  if (chart && total && sample && status && range) {
    async function updateMarketPulse() {
      try {
        const response = await fetch('/api/v1/public/market-pulse', {
          credentials: 'omit', cache: 'no-store',
          headers: {'Accept': 'application/json'}
        });
        if (!response.ok) throw new Error('Data unavailable');
        const data = await response.json();
        if (data.scope !== 'bounded_persisted_source_observations' ||
            !Array.isArray(data.days) || data.days.length !== 14 ||
            !Number.isInteger(data.scanned_recent_rows) ||
            !Number.isInteger(data.new_notices_in_sample)) throw new Error('Invalid snapshot');
        const rows = data.days.map(day => {
          if (!/^\d{4}-\d{2}-\d{2}$/.test(day.date) ||
              !Number.isInteger(day.count) || day.count < 0 || day.count > 5000) {
            throw new Error('Invalid sample');
          }
          return day;
        });
        const max = Math.max(1, ...rows.map(day => day.count));
        chart.replaceChildren();
        const fmt = new Intl.NumberFormat(ru() ? 'ru-RU' : 'en-US');
        rows.forEach((day, index) => {
          const date = day.date.slice(8);
          const column = create('div', 'vq-pulse-column');
          const bar = create('div', 'vq-pulse-bar');
          bar.style.height = Math.max(3, Math.round((day.count / max) * 154)) + 'px';
          bar.title = day.date + ': ' + fmt.format(day.count);
          column.append(bar, create('small', '', index % 2 === 0 ? date : ''));
          chart.append(column);
        });
        total.textContent = fmt.format(data.new_notices_in_sample);
        sample.textContent = fmt.format(data.scanned_recent_rows);
        range.textContent = rows[0].date + ' — ' + rows[rows.length - 1].date + ' UTC';
        chart.setAttribute('aria-label', t(
          'New stored notices by UTC day in a limited real-data sample',
          'Новые сохранённые извещения по дням UTC в ограниченной реальной выборке'
        ) + ': ' + rows.map(d => d.date + '=' + d.count).join(', '));
        status.textContent = data.scanned_recent_rows
          ? t('Chart built from saved connector records, not sample illustrations.', 'График построен по сохранённым извещениям, а не по демонстрационным данным.')
          : t('No saved source records are available in this database yet.', 'В этой базе пока нет сохранённых извещений из источников.');
      } catch (_) {
        total.textContent = '—';
        sample.textContent = '—';
        chart.replaceChildren();
        status.textContent = t(
          'Real market observations are temporarily unavailable; no demo values are shown.',
          'Реальные показатели временно недоступны; демонстрационные значения не подставляются.'
        );
      }
    }
    updateMarketPulse();
  }

  const openButton = el('vqOpenHelp'), closeButton = el('vqCloseHelp'),
        floatButton = el('vqFloatingHelp'), panel = el('vqHelpDrawer'),
        content = el('vqHelpContent');
  const topics = {
    search: [
      'Guest search reads real notices already saved in the VALYQON database. It does not request an upstream website on each keystroke. Only a limited preview is available.',
      'Гостевой поиск работает с реальными извещениями, которые VALYQON уже сохранил в базе. Он не обращается к каждой площадке в момент ввода. Гостям доступен только ограниченный просмотр.'
    ],
    source: [
      'Guest result cards deliberately omit buyer names, original source platforms, external links, documents and participation terms.',
      'В гостевой выдаче скрыты заказчик, название площадки, исходная ссылка, документы и условия участия.'
    ],
    payment: [
      'Commercial billing is not enabled in the current pilot. Registration alone does not prove a paid subscription. Full paid access will require a verified subscription.',
      'Коммерческая оплата пока не включена. Регистрация не подтверждает наличие подписки. Для полного платного доступа потребуется проверенная активная подписка.'
    ],
    privacy: [
      'Guest search reads shared public source notices. It does not read your company profiles, uploaded documents or organizational records.',
      'Гостевой поиск читает общую базу публичных извещений. Он не обращается к профилям компаний, загруженным документам или данным организаций.'
    ]
  };
  function setOpen(open) {
    if (!panel || !openButton) return;
    panel.hidden = !open;
    openButton.setAttribute('aria-expanded', String(open));
    if (floatButton) floatButton.setAttribute('aria-expanded', String(open));
    if (open && closeButton) closeButton.focus();
    else if (!open) openButton.focus();
  }
  if (panel && openButton && closeButton && content) {
    openButton.addEventListener('click', () => setOpen(panel.hidden));
    if (floatButton) floatButton.addEventListener('click', () => setOpen(panel.hidden));
    closeButton.addEventListener('click', () => setOpen(false));
    document.querySelectorAll('[data-vq-help]').forEach(button => {
      button.addEventListener('click', () => {
        const response = topics[button.dataset.vqHelp];
        if (!response) return;
        content.textContent = response[ru() ? 1 : 0];
      });
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !panel.hidden) setOpen(false);
    });
  }
})();
