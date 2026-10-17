"""Static discovery workspace markup; fetched data is escaped by the browser renderer."""
DISCOVERY_HTML = '''<section id="discoveryWorkspace" class="p" data-page="discover" hidden>
<h2>Discover opportunities</h2><p>Search enabled procurement sources against your active shared-company profile. Repeat searches do not mark notices as seen.</p>
<div class="toolbar"><button id="discoverButton" class="primary" disabled>Find opportunities</button><span id="discoverContext" class="muted">Loading workspace…</span></div>
<p class="fine">Filters below apply only to fetched results, not to the source search. Missing values are excluded when a corresponding filter is set.</p>
<section class="discovery-journey" aria-label="Customer discovery journey">
<h3 data-ui-en="Your next decision" data-ui-ru="Ваш следующий шаг">Your next decision</h3>
<p id="discoveryGuide" role="status" aria-live="polite"></p>
<div class="toolbar"><a href="#companies" data-ui-en="Review company / PDF profile" data-ui-ru="Проверить компанию / PDF-профиль">Review company / PDF profile</a><a href="#saved" data-ui-en="Review saved opportunities" data-ui-ru="Открыть сохранённые закупки">Review saved opportunities</a><a href="#monitoring" data-ui-en="Open monitoring controls" data-ui-ru="Открыть управление мониторингом">Open monitoring controls</a></div>
<p class="fine" data-ui-en="Saving retains an opportunity. Monitoring is a separate explicit action; this journey does not subscribe you or submit a bid." data-ui-ru="Сохранение удерживает закупку. Мониторинг запускается отдельно; этот маршрут не оформляет подписку и не подаёт заявку.">Saving retains an opportunity. Monitoring is a separate explicit action; this journey does not subscribe you or submit a bid.</p>
</section>
<div id="discoverySourceOutcomes" aria-label="Source outcomes"></div>
<div class="filter-grid">
<div><label for="filterKeyword">Title / category keyword</label><input id="filterKeyword" type="search"></div>
<div><label for="filterSource">Country / source</label><select id="filterSource"><option value="">All fetched sources</option></select></div>
<div><label for="filterBuyer">Buyer</label><input id="filterBuyer" type="search"></div>
<div><label for="filterCurrency">Currency</label><select id="filterCurrency"><option value="">All currencies</option></select></div>
<div><label for="filterValue">Minimum value (selected currency)</label><input id="filterValue" type="number" min="0" disabled><span class="fine">Values use normalized currency codes. No FX conversion is performed.</span></div>
<div><label for="filterFit" data-ui-en="Minimum displayed fit %" data-ui-ru="Минимальная показанная оценка %">Minimum displayed fit %</label><input id="filterFit" type="number" min="0" max="100"><span class="fine" data-ui-en="Uses document fit after analysis; otherwise preliminary metadata fit." data-ui-ru="После анализа используется оценка документа; иначе — предварительная оценка метаданных.">Uses document fit after analysis; otherwise preliminary metadata fit.</span></div>
<div><label for="filterDeadline">Deadline on or before</label><input id="filterDeadline" type="date"></div>
<div><label for="filterPublished">Published on or after</label><input id="filterPublished" type="date"></div>
<div><button id="resetFilters">Reset filters</button></div></div>
<section id="discoveryPresets" class="p" aria-label="Saved filter views">
<h3>My saved filters</h3>
<p class="fine">Presets only filter tenders already fetched. They do not schedule a search or send daily notifications. Run Find opportunities before applying a preset.</p>
<div class="toolbar">
<label for="savedSearchName">Name</label>
<input id="savedSearchName" maxlength="80" placeholder="Construction · region · price">
<button id="saveSearchPreset" type="button" disabled>Save current filters</button>
<label for="savedSearchSelect">Saved view</label>
<select id="savedSearchSelect"><option value="">Select saved view</option></select>
<button id="applySearchPreset" type="button" disabled>Apply to fetched results</button>
<button id="deleteSearchPreset" type="button" disabled>Delete view</button>
</div><p id="savedSearchStatus" role="status" aria-live="polite">Sign in and activate a company to manage saved filters.</p>
</section>
<p id="discoveryMessage" role="status" aria-live="polite">Run discovery to find opportunities.</p><p id="sourceHealth" class="fine"></p><div id="discoveryResults" aria-label="Discovered opportunities"></div>
</section><dialog id="tenderDetail" aria-labelledby="detailTitle"><div class="toolbar"><h2 id="detailTitle">Tender workspace</h2><button id="closeDetail" autofocus>Close detail</button></div><div id="detailBody"></div></dialog>'''
