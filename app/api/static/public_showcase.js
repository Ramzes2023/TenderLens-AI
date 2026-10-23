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

    function demoPulse(days) {
      const rows=Array.isArray(days) && days.length===14 ? days :
        [4,9,6,12,8,15,11,14,18,10,17,22,16,24].map((count,i)=>{
          const now=new Date();
          const day=new Date(Date.UTC(now.getUTCFullYear(),now.getUTCMonth(),
            now.getUTCDate()-13+i)).toISOString().slice(0,10);
          return {date:day,count,priced:Math.floor(count*.66)};
        });
      const values=rows.map(x=>x.count);
      const highest=Math.max(1,...values);
      const format=new Intl.NumberFormat(ru()?'ru-RU':'en-US');
      total.textContent=format.format(values.reduce((a,b)=>a+b,0));
      sample.textContent='186';
      chart.replaceChildren();
      rows.forEach((day,i)=>{
        const column=create('div','vq-pulse-column');
        const bar=create('div','vq-pulse-bar');
        bar.style.height=Math.max(3,Math.round(day.count/highest*154))+'px';
        bar.title=day.date+' · '+format.format(day.count)+' · '+t('ILLUSTRATIVE','УЧЕБНЫЕ ДАННЫЕ');
        column.append(bar,create('small','',i%2===0?day.date.slice(8):''));
        chart.append(column);
      });
      chart.setAttribute('aria-label',t('Illustrative 14-day chart, not real procurement numbers.',
        'Учебный график за 14 дней, не реальные показатели закупок.'));
      range.textContent=t('ILLUSTRATIVE 14 DAYS','УЧЕБНЫЕ 14 ДНЕЙ');
      status.textContent=t(
        'DEMONSTRATION: all numbers in this chart are invented for design preview, not observed procurement data.',
        'ДЕМОНСТРАЦИЯ: все цифры этого графика придуманы для оценки дизайна, а не получены из закупок.');
      const note=el('vqPulseDemoDisclosure');
      if(note){note.hidden=false;note.textContent=t(
        'ILLUSTRATIVE DATA · EXAMPLE GRAPH · NOT REAL PROCUREMENT ACTIVITY',
        'УЧЕБНЫЕ ДАННЫЕ · ПРИМЕР ГРАФИКА · НЕ РЕАЛЬНАЯ АКТИВНОСТЬ ЗАКУПОК');
      }
      const badge=document.querySelector('.vq-pulse-verified');
      if(badge){badge.classList.add('is-demo');badge.textContent=t(
        'DEMO DATA — NOT VERIFIED', 'УЧЕБНЫЕ ДАННЫЕ — НЕ РЕАЛЬНЫЕ');
      }
    }
    function realPulse(){
      const note=el('vqPulseDemoDisclosure');
      if(note)note.hidden=true;
      const badge=document.querySelector('.vq-pulse-verified');
      if(badge){badge.classList.remove('is-demo');badge.textContent=t(
        'Verified database snapshot','Показатели из сохранённой базы');
      }
      updateMarketPulse();
    }
    window.addEventListener('valyqon-demo-chart-mode', event=>{
      if(event.detail?.demo)demoPulse(event.detail.daily);
      else realPulse();
    });
    if(document.body.dataset.publicAnalyticsMode==='demo')demoPulse();
    else realPulse();
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

  const aiForm = el('vqAskAIForm'), aiInput = el('vqAIQuestion'),
        aiStatus = el('vqAIStatus'), aiSend = el('vqAISend');
  if (aiForm && aiInput && aiStatus && aiSend && content) {
    aiForm.addEventListener('submit', async event => {
      event.preventDefault();
      const question = aiInput.value.trim();
      if (question.length < 3) return;
      aiSend.disabled = true;
      aiStatus.textContent = t('Contacting the configured AI provider…',
        'Отправляем вопрос настроенному ИИ-провайдеру…');
      try {
        const response = await fetch('/api/v1/public/help/ask', {
          method: 'POST', credentials: 'omit', cache: 'no-store',
          headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
          body: JSON.stringify({question})
        });
        if (!response.ok) {
          throw new Error(response.status === 429
            ? t('Question limit reached. Please try later.', 'Лимит вопросов исчерпан. Повторите позже.')
            : response.status === 503
            ? t('Public AI help is currently unavailable.', 'Гостевой ИИ-помощник сейчас недоступен.')
            : t('Could not process the question.', 'Не удалось обработать вопрос.'));
        }
        const data = await response.json();
        if (data.scope !== 'public_product_only' || typeof data.answer !== 'string') {
          throw new Error(t('Unexpected AI response.', 'Неожиданный ответ ИИ.'));
        }
        content.textContent = data.answer;
        aiStatus.textContent = t('AI answer generated; verify any important facts.',
          'Ответ ИИ получен. Важные сведения необходимо проверить.');
      } catch (error) {
        aiStatus.textContent = error.message || t('AI service unavailable.', 'ИИ-сервис недоступен.');
      } finally {
        aiSend.disabled = false;
      }
    });
  }
})();
