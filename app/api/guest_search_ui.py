"""Public guest search markup. Results are populated only by the real DB API."""

GUEST_SEARCH_HTML = """<section id="guest-search" class="guest-search-zone" aria-labelledby="guest-title">
<div class="guest-search-panel">
  <div class="guest-search-head">
    <span class="guest-label">VALYQON AI · ГОСТЕВОЙ ПОИСК</span>
    <h2 id="guest-title">Ищите реальные тендеры <span>без регистрации</span></h2>
    <p>Проверьте поиск по объявлениям, которые уже поступили в VALYQON AI из подключённых источников. Без вымышленных результатов.</p>
  </div>
  <form id="guestSearchForm" class="guest-search-form" role="search" autocomplete="off">
    <label class="guest-sr-only" for="guestSearchInput">Что хотите найти?</label>
    <input id="guestSearchInput" name="q" type="search" maxlength="120"
      placeholder="Например: медицинское оборудование, строительство, топливо" />
    <button type="submit" id="guestSearchButton">Найти закупки ↗</button>
  </form>
  <div class="guest-popular" aria-label="Примеры поисковых запросов">
    <span>Популярные направления:</span>
    <button type="button" data-guest-term="строительство">Строительство</button>
    <button type="button" data-guest-term="медицинское">Медицина</button>
    <button type="button" data-guest-term="оборудование">Оборудование</button>
    <button type="button" data-guest-term="услуги">Услуги</button>
  </div>
</div>
<div class="guest-results-layout">
 <div class="guest-results-main">
  <div class="guest-results-heading">
    <div><span class="guest-kicker">РЕЗУЛЬТАТЫ ИЗ НАШЕЙ БАЗЫ</span>
      <h3>Предварительный просмотр закупок</h3>
      <p id="guestSearchStatus" role="status" aria-live="polite">Загружаем последние сохранённые извещения…</p>
    </div>
    <span class="guest-no-demo">● Только сохранённые объявления</span>
  </div>
  <div id="guestSearchResults" class="guest-result-list" aria-label="Результаты гостевого поиска"></div>
  <p class="guest-reality-note">Это ограниченная выборка сохранённых закупок, а не прямой запрос на площадки в момент поиска. Актуальность, условия и срок подачи необходимо проверять по официальному извещению после получения полного доступа.</p>
 </div>
 <aside class="guest-unlock">
  <span class="guest-unlock-icon" aria-hidden="true">✦</span>
  <span class="guest-kicker">РАСШИРЕННЫЙ ДОСТУП</span>
  <h3>Вся информация — в вашем рабочем кабинете</h3>
  <p>Гостям доступны только названия закупок, указанные суммы и сроки подачи.</p>
  <ul>
    <li>Заказчик и его контакты</li>
    <li>Название площадки и ссылка на оригинал</li>
    <li>Техническое задание и документы</li>
    <li>Условия участия и полный анализ</li>
  </ul>
  <a class="guest-register-cta" href="/register">Создать аккаунт →</a>
  <p class="guest-pay-note">Подробный коммерческий доступ будет требовать действующую подписку. Приём платежей пока не включён.</p>
 </aside>
</div>
</section>"""
