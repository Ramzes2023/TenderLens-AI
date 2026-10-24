"""Honest user-facing journal for existing deadline reminder worker receipts.

This is not a simulated inbox or a new messaging provider.
"""

DELIVERY_JOURNAL_HTML = """
<section id="vqDeliveryJournal" class="vq-delivery-journal" data-page="notifications" hidden aria-labelledby="vqDeliveryTitle">
  <div class="vq-delivery-hero">
    <div>
      <span class="vq-delivery-eyebrow" data-ui-en="NOTIFICATIONS · EVIDENCE" data-ui-ru="УВЕДОМЛЕНИЯ · ПОДТВЕРЖДЁННЫЕ ДЕЙСТВИЯ">NOTIFICATIONS · EVIDENCE</span>
      <h2 id="vqDeliveryTitle" data-ui-en="Delivery journal" data-ui-ru="Журнал уведомлений">Delivery journal</h2>
      <p data-ui-en="See the real sending attempts recorded for your account and active company. No fictional notifications." data-ui-ru="Здесь отображаются реально записанные попытки отправки для вашего аккаунта и активной компании. Без вымышленных уведомлений.">See the real sending attempts recorded for your account and active company. No fictional notifications.</p>
    </div>
    <div class="vq-delivery-actions">
      <button type="button" id="vqDeliveryRefresh" data-ui-en="↻ Refresh" data-ui-ru="↻ Обновить">↻ Refresh</button>
      <a href="#settings" data-ui-en="Notification settings →" data-ui-ru="Настройки уведомлений →">Notification settings →</a>
    </div>
  </div>
  <p id="vqDeliveryStatus" role="status" aria-live="polite" data-ui-en="Open this section to load your recorded delivery attempts." data-ui-ru="Откройте этот раздел для загрузки журнала отправки.">Open this section to load your recorded delivery attempts.</p>
  <div class="vq-delivery-summary" aria-label="Last 50 recorded attempts">
    <article><small data-ui-en="Recorded attempts" data-ui-ru="Попытки">Recorded attempts</small><strong id="vqDeliveryCount">—</strong></article>
    <article><small data-ui-en="Sender returned OK" data-ui-ru="Отправитель ответил успешно">Sender returned OK</small><strong id="vqDeliverySent">—</strong></article>
    <article><small data-ui-en="Sender errors" data-ui-ru="Ошибки отправки">Sender errors</small><strong id="vqDeliveryFailed">—</strong></article>
    <article><small data-ui-en="Still pending" data-ui-ru="В ожидании">Still pending</small><strong id="vqDeliveryPending">—</strong></article>
  </div>
  <div class="vq-delivery-list-heading">
    <div><span class="vq-delivery-eyebrow" data-ui-en="RECENT DELIVERY ATTEMPTS" data-ui-ru="ПОСЛЕДНИЕ ПОПЫТКИ">RECENT DELIVERY ATTEMPTS</span><h3 data-ui-en="Your reminder activity" data-ui-ru="История напоминаний">Your reminder activity</h3></div>
    <span data-ui-en="Last 50 only" data-ui-ru="Только последние 50">Last 50 only</span>
  </div>
  <div id="vqDeliveryRows" class="vq-delivery-rows" aria-live="polite"></div>
  <p class="vq-delivery-disclaimer" data-ui-en="“Sent” means the configured sender returned successfully. It does not verify inbox delivery, receipt, reading or Telegram reachability. A pending attempt is not guaranteed to be retried. Only records stored by the worker appear here." data-ui-ru="«Отправлено» означает успешное завершение вызова отправителя. Это не подтверждает доставку, получение, прочтение письма или доступность Telegram. Повтор ожидающей попытки не гарантируется. Показываются только записи, сохранённые обработчиком.">“Sent” means the configured sender returned successfully. It does not verify inbox delivery, receipt, reading or Telegram reachability. A pending attempt is not guaranteed to be retried. Only records stored by the worker appear here.</p>
</section>
"""
