/* Guest cards are built with textContent, never untrusted HTML or URLs. */
(() => {
  'use strict';
  const form = document.getElementById('guestSearchForm');
  const output = document.getElementById('guestSearchResults');
  const status = document.getElementById('guestSearchStatus');
  const input = document.getElementById('guestSearchInput');
  const button = document.getElementById('guestSearchButton');
  if (!form || !output || !status || !input || !button) return;

  let pending = null;
  const tr = (en, ru) => document.documentElement.lang === 'ru' ? ru : en;
  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = String(text);
    return element;
  }
  function fmtPrice(value, currency) {
    if (typeof value !== 'number' || !Number.isFinite(value)) return tr('Not specified', 'Не указана');
    const amount = new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 2}).format(value);
    const codes = {RUB: '₽', USD: '$', EUR: '€', AZN: '₼'};
    return amount + ' ' + (codes[currency] || currency || '');
  }
  function addResult(item) {
    const article = node('article', 'guest-tender');
    article.append(node('h4', 'guest-tender-title', item.title));
    const facts = node('div', 'guest-tender-facts');
    const amount = node('span', '', tr('Starting price: ', 'Начальная цена: '));
    amount.append(node('strong', '', fmtPrice(item.initial_price, item.currency)));
    const deadline = node('span', '', tr('Deadline: ', 'Срок подачи: '));
    deadline.append(node('strong', '', item.deadline || tr('Not specified', 'Не указан')));
    facts.append(amount, deadline);
    article.append(facts);
    const restricted = node('div', 'guest-locked');
    restricted.append(
      node('span', 'guest-lock-symbol', '🔒'),
      node('span', '', tr('Platform, buyer, documents, links and participation terms are locked. Registration and an active subscription are required.', 'Площадка, заказчик, документы, ссылки и условия участия скрыты. Требуются регистрация и подписка.'))
    );
    article.append(restricted);
    output.append(article);
  }
  async function run(query) {
    if (pending) pending.abort();
    const controller = new AbortController();
    pending = controller;
    button.disabled = true;
    status.textContent = tr('Searching real stored notices…', 'Ищем среди реально сохранённых закупок…');
    output.replaceChildren();
    try {
      const response = await fetch('/api/v1/public/opportunities?q=' + encodeURIComponent(query), {
        signal: controller.signal,
        credentials: 'omit',
        headers: {'Accept': 'application/json'},
        cache: 'no-store'
      });
      if (!response.ok) {
        throw new Error(response.status === 429 ? tr('Too many requests. Try again later.', 'Слишком много запросов. Повторите поиск позже.') : tr('Search is temporarily unavailable. Try again later.', 'Поиск временно недоступен. Попробуйте позже.'));
      }
      const payload = await response.json();
      if (!Array.isArray(payload.results) || payload.source !== 'stored_connector_notices') {
        throw new Error(tr('Unexpected server response.', 'Сервис вернул неожиданный ответ.'));
      }
      const rows = payload.results.slice(0, 12);
      rows.forEach(addResult);
      if (!rows.length) output.append(node('div', 'guest-empty',
        tr('No matches found in the available stored notices. Try another keyword. No example notices are substituted.', 'Среди доступных сохранённых извещений ничего не найдено. Попробуйте другое слово. Примеры не подставляются.')));
      status.textContent = rows.length
        ? tr('Showing ', 'Показано ') + rows.length + tr(' real stored notices (limited selection; details locked).', ' реальных сохранённых извещений (ограниченная выборка, без раскрытия деталей).')
        : tr('No matches in the scanned portion of the database.', 'Совпадений в просмотренной части базы нет.');
    } catch (error) {
      if (error.name === 'AbortError') return;
      status.textContent = error.message || tr('Search error.', 'Ошибка поиска.');
      output.append(node('div', 'guest-empty', tr('Could not load real results. Fabricated tender notices are never shown.', 'Не удалось загрузить реальные результаты. Выдуманные тендеры не показываются.')));
    } finally {
      if (pending === controller) button.disabled = false;
    }
  }
  form.addEventListener('submit', event => {
    event.preventDefault();
    run(input.value.trim());
  });
  document.querySelectorAll('[data-guest-term]').forEach(chip => {
    chip.addEventListener('click', () => {
      input.value = chip.dataset.guestTerm || '';
      run(input.value);
    });
  });
  run('');
})();
