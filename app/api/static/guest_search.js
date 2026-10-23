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
  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = String(text);
    return element;
  }
  function fmtPrice(value, currency) {
    if (typeof value !== 'number' || !Number.isFinite(value)) return 'Не указана';
    const amount = new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 2}).format(value);
    const codes = {RUB: '₽', USD: '$', EUR: '€', AZN: '₼'};
    return amount + ' ' + (codes[currency] || currency || '');
  }
  function addResult(item) {
    const article = node('article', 'guest-tender');
    article.append(node('h4', 'guest-tender-title', item.title));
    const facts = node('div', 'guest-tender-facts');
    const amount = node('span', '', 'Начальная цена: ');
    amount.append(node('strong', '', fmtPrice(item.initial_price, item.currency)));
    const deadline = node('span', '', 'Срок подачи: ');
    deadline.append(node('strong', '', item.deadline || 'Не указан'));
    facts.append(amount, deadline);
    article.append(facts);
    const restricted = node('div', 'guest-locked');
    restricted.append(
      node('span', 'guest-lock-symbol', '🔒'),
      node('span', '', 'Площадка, заказчик, документы, ссылки и условия участия скрыты. Требуются регистрация и подписка.')
    );
    article.append(restricted);
    output.append(article);
  }
  async function run(query) {
    if (pending) pending.abort();
    pending = new AbortController();
    button.disabled = true;
    status.textContent = 'Ищем среди реально сохранённых закупок…';
    output.replaceChildren();
    try {
      const response = await fetch('/api/v1/public/opportunities?q=' + encodeURIComponent(query), {
        signal: pending.signal,
        credentials: 'omit',
        headers: {'Accept': 'application/json'},
        cache: 'no-store'
      });
      if (!response.ok) {
        throw new Error(response.status === 429 ? 'Слишком много запросов. Повторите поиск позже.' : 'Поиск временно недоступен. Попробуйте позже.');
      }
      const payload = await response.json();
      if (!Array.isArray(payload.results) || payload.source !== 'stored_connector_notices') {
        throw new Error('Сервис вернул неожиданный ответ.');
      }
      const rows = payload.results.slice(0, 12);
      rows.forEach(addResult);
      if (!rows.length) output.append(node('div', 'guest-empty',
        'Среди доступных сохранённых извещений ничего не найдено. Попробуйте другое слово. Примеры не подставляются.'));
      status.textContent = rows.length
        ? 'Показано ' + rows.length + ' реальных сохранённых извещений (ограниченная выборка, без раскрытия деталей).'
        : 'Совпадений в просмотренной части базы нет.';
    } catch (error) {
      if (error.name === 'AbortError') return;
      status.textContent = error.message || 'Ошибка поиска.';
      output.append(node('div', 'guest-empty', 'Не удалось загрузить реальные результаты. Выдуманные тендеры не показываются.'));
    } finally {
      button.disabled = false;
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
