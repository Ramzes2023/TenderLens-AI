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
  <section id="vqDeliveryReliability" class="vq-delivery-reliability" aria-labelledby="vqDeliveryReliabilityTitle">
    <div class="vq-delivery-reliability-head">
      <div><span class="vq-delivery-eyebrow" data-ui-en="DELIVERY RELIABILITY" data-ui-ru="НАДЁЖНОСТЬ ОТПРАВКИ">DELIVERY RELIABILITY</span>
        <h3 id="vqDeliveryReliabilityTitle" data-ui-en="Attempts needing attention" data-ui-ru="Попытки, требующие внимания">Attempts needing attention</h3>
      </div>
      <strong id="vqDeliveryReliabilityStatus" role="status" aria-live="polite" data-ui-en="Not checked" data-ui-ru="Не проверено">Not checked</strong>
    </div>
    <div class="vq-delivery-reliability-counts">
      <div><small data-ui-en="Failed sender calls · entire history" data-ui-ru="Ошибки отправителя · вся история">Failed sender calls · entire history</small><strong id="vqDeliveryAllFailed">—</strong></div>
      <div><small data-ui-en="Pending over 30 minutes · possibly stranded" data-ui-ru="Ожидают более 30 минут · возможное зависание">Pending over 30 minutes · possibly stranded</small><strong id="vqDeliveryOldPending">—</strong></div>
    </div>
    <p data-ui-en="These counts cover all saved attempts for your account and active company, unlike the last-50 journal. An old pending claim may be in progress or stranded; sender errors may occur after provider acceptance. No automatic retries occur, since blindly resending could duplicate a notification. Contact support to investigate."
       data-ui-ru="Это подсчёт всех записанных попыток вашего аккаунта и активной компании, а не только последних 50. Старая ожидающая попытка может выполняться или зависнуть; ошибка могла возникнуть уже после принятия сообщения провайдером. Автоматических повторов нет: слепая отправка создаёт риск дублей. Для расследования обратитесь в поддержку.">These counts cover all saved attempts for your account and active company, unlike the last-50 journal. An old pending claim may be in progress or stranded; sender errors may occur after provider acceptance. No automatic retries occur, since blindly resending could duplicate a notification. Contact support to investigate.</p>
  </section>
  <div class="vq-delivery-list-heading">
    <div><span class="vq-delivery-eyebrow" data-ui-en="RECENT DELIVERY ATTEMPTS" data-ui-ru="ПОСЛЕДНИЕ ПОПЫТКИ">RECENT DELIVERY ATTEMPTS</span><h3 data-ui-en="Your reminder activity" data-ui-ru="История напоминаний">Your reminder activity</h3></div>
    <span data-ui-en="Last 50 only" data-ui-ru="Только последние 50">Last 50 only</span>
  </div>
  <div id="vqDeliveryRows" class="vq-delivery-rows" aria-live="polite"></div>
  <section id="vqDeliveryPrefs" class="vq-delivery-prefs" aria-labelledby="vqDeliveryPrefsTitle">
    <div><span class="vq-delivery-eyebrow" data-ui-en="YOUR PERMISSION" data-ui-ru="ВАШЕ СОГЛАСИЕ">YOUR PERMISSION</span>
      <h3 id="vqDeliveryPrefsTitle" data-ui-en="Deadline reminder preferences" data-ui-ru="Настройки напоминаний о сроках">Deadline reminder preferences</h3>
      <p data-ui-en="Opt in for the current company. This saves only your preference; actual delivery requires a verified email or linked Telegram chat, configured sender, and a scheduled Worker. No test email or Telegram message is sent by these controls." data-ui-ru="Включайте напоминания для текущей компании добровольно. Здесь сохраняется только согласие: для доставки нужны подтверждённая почта или привязанный Telegram, настроенный отправитель и запущенный Worker. Эти переключатели не отправляют тестовые сообщения.">Opt in for the current company. This saves only your preference; actual delivery requires a verified email or linked Telegram chat, configured sender, and a scheduled Worker. No test email or Telegram message is sent by these controls.</p></div>
    <div class="vq-delivery-prefs-controls">
      <label><input id="vqDeliveryEmailOptIn" type="checkbox" disabled><span data-ui-en="Email reminders" data-ui-ru="Напоминания по email">Email reminders</span></label>
      <label><input id="vqDeliveryTelegramOptIn" type="checkbox" disabled><span data-ui-en="Telegram reminders" data-ui-ru="Напоминания в Telegram">Telegram reminders</span></label>
      <button id="vqDeliverySavePrefs" type="button" disabled data-ui-en="Save my preferences" data-ui-ru="Сохранить согласие">Save my preferences</button>
    </div>
    <p id="vqDeliveryPrefsStatus" role="status" aria-live="polite" data-ui-en="Checking saved preferences…" data-ui-ru="Проверяем настройки…">Checking saved preferences…</p>
  </section>
  <p class="vq-delivery-disclaimer" data-ui-en="“Sent” means the configured sender returned successfully. It does not verify inbox delivery, receipt, reading or Telegram reachability. A pending attempt is not guaranteed to be retried. Only records stored by the worker appear here." data-ui-ru="«Отправлено» означает успешное завершение вызова отправителя. Это не подтверждает доставку, получение, прочтение письма или доступность Telegram. Повтор ожидающей попытки не гарантируется. Показываются только записи, сохранённые обработчиком.">“Sent” means the configured sender returned successfully. It does not verify inbox delivery, receipt, reading or Telegram reachability. A pending attempt is not guaranteed to be retried. Only records stored by the worker appear here.</p>
</section>
"""
