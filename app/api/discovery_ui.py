"""Static discovery workspace markup; fetched data is escaped by the browser renderer."""
DISCOVERY_HTML = '''<section id="discoveryWorkspace" class="p" data-page="discover" hidden>
<h2>Discover opportunities</h2><p>Search enabled procurement sources against your active shared-company profile. Repeat searches do not mark notices as seen.</p>
<div class="toolbar"><button id="discoverButton" class="primary" disabled>Find opportunities</button><span id="discoverContext" class="muted">Loading workspace…</span></div>
<p class="fine">Filters below apply only to fetched results, not to the source search. Missing values are excluded when a corresponding filter is set.</p>
<div class="filter-grid">
<div><label for="filterKeyword">Title / category keyword</label><input id="filterKeyword" type="search"></div>
<div><label for="filterSource">Country / source</label><select id="filterSource"><option value="">All fetched sources</option></select></div>
<div><label for="filterBuyer">Buyer</label><input id="filterBuyer" type="search"></div>
<div><label for="filterCurrency">Currency</label><select id="filterCurrency"><option value="">All currencies</option></select></div>
<div><label for="filterValue">Minimum value (selected currency)</label><input id="filterValue" type="number" min="0" disabled><span class="fine">Select a currency to compare amounts.</span></div>
<div><label for="filterFit">Minimum preliminary fit %</label><input id="filterFit" type="number" min="0" max="100"></div>
<div><label for="filterDeadline">Deadline on or before</label><input id="filterDeadline" type="date"></div>
<div><label for="filterPublished">Published on or after</label><input id="filterPublished" type="date"></div>
<div><button id="resetFilters">Reset filters</button></div></div>
<p id="discoveryMessage" role="status" aria-live="polite">Run discovery to find opportunities.</p><p id="sourceHealth" class="fine"></p><div id="discoveryResults" aria-label="Discovered opportunities"></div>
</section><dialog id="tenderDetail" aria-labelledby="detailTitle"><div class="toolbar"><h2 id="detailTitle">Tender workspace</h2><button id="closeDetail" autofocus>Close detail</button></div><div id="detailBody"></div></dialog>'''
