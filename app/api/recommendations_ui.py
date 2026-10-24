"""No synthetic recommendations: archived authentic Discovery scoring only."""

RECOMMENDATIONS_HTML = """
<section id="vqRecommendations" class="vq-recommendations" data-page="recommended" hidden aria-labelledby="vqRecommendationsTitle">
  <div class="vq-recommend-hero">
    <div>
      <span class="vq-recommend-eyebrow" data-ui-en="MATCHED PROCUREMENT · VERIFIED SEARCH HISTORY" data-ui-ru="ЗАКУПКИ ПО СООТВЕТСТВИЮ · ИСТОРИЯ ПОИСКА">MATCHED PROCUREMENT · VERIFIED SEARCH HISTORY</span>
      <h2 id="vqRecommendationsTitle" data-ui-en="Previously matched tenders" data-ui-ru="Подходящие закупки из истории">Previously matched tenders</h2>
      <p data-ui-en="Ranked from up to three previous real Discovery runs for your active company. This page never searches external sources automatically." data-ui-ru="Ранжирование на основе трёх последних реальных поисков активной компании. Этот экран не опрашивает внешние площадки автоматически.">Ranked from up to three previous real Discovery runs for your active company. This page never searches external sources automatically.</p>
    </div>
    <div class="vq-recommend-actions">
      <button id="vqRecommendationsRefresh" type="button" data-ui-en="↻ Refresh from history" data-ui-ru="↻ Обновить из истории">↻ Refresh from history</button>
      <a href="#discover" data-ui-en="New real search →" data-ui-ru="Новый поиск →">New real search →</a>
    </div>
  </div>
  <p id="vqRecommendationsStatus" role="status" aria-live="polite" data-ui-en="Open this section to examine your company's previous Discovery runs." data-ui-ru="Откройте раздел для анализа прошлых поисков вашей компании.">Open this section to examine your company's previous Discovery runs.</p>
  <div class="vq-recommend-metrics">
    <article><small data-ui-en="Historical ranked matches" data-ui-ru="Совпадения из истории">Historical ranked matches</small><strong id="vqRecommendedCount">—</strong></article>
    <article><small data-ui-en="Search runs checked" data-ui-ru="Проверено поисков">Search runs checked</small><strong id="vqRecommendedRuns">—</strong></article>
    <article><small data-ui-en="Top preliminary match" data-ui-ru="Максимальное предварительное соответствие">Top preliminary match</small><strong id="vqRecommendedTopScore">—</strong></article>
  </div>
  <div class="vq-recommend-controls">
    <label for="vqRecommendedMinimum" data-ui-en="Minimum preliminary fit" data-ui-ru="Минимальное соответствие">Minimum preliminary fit</label>
    <select id="vqRecommendedMinimum">
      <option value="0" data-ui-en="All scored tenders" data-ui-ru="Все оценённые тендеры">All scored tenders</option>
      <option value="50" data-ui-en="50% and above" data-ui-ru="От 50%">50% and above</option>
      <option value="70" data-ui-en="70% and above" data-ui-ru="От 70%">70% and above</option>
      <option value="85" data-ui-en="85% and above" data-ui-ru="От 85%">85% and above</option>
    </select>
    <a href="#search-history" data-ui-en="View exact historic results →" data-ui-ru="Открыть сохранённую историю →">View exact historic results →</a>
  </div>
  <div id="vqRecommendationsResults" class="vq-recommend-results" aria-live="polite"></div>
  <p class="vq-recommend-disclosure" data-ui-en="Preliminary scores are generated from available notice metadata. They are not eligibility, official tender availability, document analysis, bidding, or confirmed customer-fit results. Source URLs, buyers, budgets and restricted paid details are not copied into this list. Verify current official documents before participating." data-ui-ru="Предварительные оценки рассчитаны по доступным метаданным. Это не подтверждение допуска, актуальности закупки, анализа документов, подачи заявки или окончательного соответствия. Ссылки, заказчики, бюджеты и закрытые платные данные здесь не дублируются. Проверяйте оригинальные документы перед участием.">Preliminary scores are generated from available notice metadata. They are not eligibility, official tender availability, document analysis, bidding, or confirmed customer-fit results. Source URLs, buyers, budgets and restricted paid details are not copied into this list. Verify current official documents before participating.</p>
</section>
"""
