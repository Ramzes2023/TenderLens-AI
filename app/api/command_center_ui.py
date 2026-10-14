"""Presentation foundation only; verified analytics are a later phase."""

COMMAND_CENTER_HTML = '''
<section id="commandCenter" class="command-center" data-page="overview" aria-labelledby="commandCenterTitle" aria-busy="true">
<header class="command-heading">
<div>
<span class="eyebrow">PROCUREMENT INTELLIGENCE</span>
<h2 id="commandCenterTitle">Command Center</h2>
<p>One workspace. A clear view of your opportunity landscape.</p>
</div>
<span class="capability-pill">Analytics foundation &middot; 24P.2</span>
</header>
<div class="command-scope">
<p id="analyticsContext">Loading workspace&hellip;</p>
<p>Data scope: no verified analytics population connected.<br>Date range: unavailable &middot; no historical query selected.</p>
</div>
<p id="analyticsStatus" class="analytics-status" role="status">Loading workspace context&hellip;</p>
<section class="command-kpis" aria-label="Procurement analytics KPIs">
<article class="command-kpi" aria-labelledby="kpiTitle0">
<span class="kpi-index" aria-hidden="true">01</span>
<h3 id="kpiTitle0">Discovered</h3>
<strong class="kpi-value">Unavailable</strong>
<p>Unique eligible opportunities</p>
<small>Verified deduplication requires 24P.3.</small>
</article>
<article class="command-kpi" aria-labelledby="kpiTitle1">
<span class="kpi-index" aria-hidden="true">02</span>
<h3 id="kpiTitle1">Matched</h3>
<strong class="kpi-value">Unavailable</strong>
<p>Company-prefiltered opportunities</p>
<small>An audited eligibility contract is pending.</small>
</article>
<article class="command-kpi" aria-labelledby="kpiTitle2">
<span class="kpi-index" aria-hidden="true">03</span>
<h3 id="kpiTitle2">High Fit</h3>
<strong class="kpi-value">Unavailable</strong>
<p>Preliminary company fit only</p>
<small>No approved overall High Fit threshold exists.</small>
</article>
<article class="command-kpi" aria-labelledby="kpiTitle3">
<span class="kpi-index" aria-hidden="true">04</span>
<h3 id="kpiTitle3">Active Sources</h3>
<strong class="kpi-value">Unavailable</strong>
<p>Successfully reached sources</p>
<small>Verified population and source observations are pending.</small>
</article>
<article class="command-kpi" aria-labelledby="kpiTitle4">
<span class="kpi-index" aria-hidden="true">05</span>
<h3 id="kpiTitle4">Countries</h3>
<strong class="kpi-value">Unavailable</strong>
<p>Known tender countries</p>
<small>Tender-country enrichment is not available.</small>
</article>
<article class="command-kpi" aria-labelledby="kpiTitle5">
<span class="kpi-index" aria-hidden="true">06</span>
<h3 id="kpiTitle5">Closing Soon</h3>
<strong class="kpi-value">Unavailable</strong>
<p>Upcoming deadline window</p>
<small>Verified date normalization and timezone are pending.</small>
</article>
</section>
<div class="command-grid">
<section class="command-panel command-wide" aria-labelledby="panel-activity">
<header>
<div>
<span class="eyebrow">Search and publication history</span>
<h3 id="panel-activity">Tender Activity</h3>
</div>
<span class="capability-pill">Coming data</span>
</header>
<div class="command-empty">
<span class="empty-mark" aria-hidden="true">&#9671;</span>
<strong>Verified data unavailable</strong>
<p>No verified historical population is connected. Search receipt time is not a publication date.</p>
</div>
</section>
<section class="command-panel command-fit" aria-labelledby="panel-fit">
<header>
<div>
<span class="eyebrow">Preliminary scoring distribution</span>
<h3 id="panel-fit">Company Fit</h3>
</div>
<span class="capability-pill">Coming data</span>
</header>
<div class="command-empty">
<span class="empty-mark" aria-hidden="true">&#9671;</span>
<strong>Verified data unavailable</strong>
<p>Disjoint fit bands and their scored denominator require the verified 24P.3 contract. Full AI analysis is separate.</p>
</div>
</section>
<section class="command-panel command-geo" aria-labelledby="panel-geography">
<header>
<div>
<span class="eyebrow">Country coverage and distribution</span>
<h3 id="panel-geography">Global Geography</h3>
</div>
<span class="capability-pill">Coming data</span>
</header>
<div class="command-empty">
<span class="empty-mark" aria-hidden="true">&#9671;</span>
<strong>Verified data unavailable</strong>
<p>Verified tender countries, counts and known/unknown denominators are pending. Source coverage is not tender geography.</p>
</div>
</section>
<section class="command-panel command-calendar" aria-labelledby="panel-deadlines">
<header>
<div>
<span class="eyebrow">Upcoming calendar heatmap</span>
<h3 id="panel-deadlines">Deadline Calendar</h3>
</div>
<span class="capability-pill">Coming data</span>
</header>
<div class="command-empty">
<span class="empty-mark" aria-hidden="true">&#9671;</span>
<strong>Verified data unavailable</strong>
<p>No normalized deadline population or declared calendar timezone is connected. Missing dates are not empty days.</p>
</div>
</section>
<section class="command-panel command-small" aria-labelledby="panel-industry">
<header>
<div>
<span class="eyebrow">Verified industry classification</span>
<h3 id="panel-industry">Industry Intelligence</h3>
</div>
<span class="capability-pill">Coming data</span>
</header>
<div class="command-empty">
<span class="empty-mark" aria-hidden="true">&#9671;</span>
<strong>Verified data unavailable</strong>
<p>Industry enrichment and a versioned taxonomy are pending. Procurement text is not an industry label.</p>
</div>
</section>
<section class="command-panel command-small" aria-labelledby="panel-category">
<header>
<div>
<span class="eyebrow">Procurement taxonomy</span>
<h3 id="panel-category">Category Breakdown</h3>
</div>
<span class="capability-pill">Coming data</span>
</header>
<div class="command-empty">
<span class="empty-mark" aria-hidden="true">&#9671;</span>
<strong>Verified data unavailable</strong>
<p>Canonical categories and known/unknown coverage are pending.</p>
</div>
</section>
<section class="command-panel command-small" aria-labelledby="panel-sources">
<header>
<div>
<span class="eyebrow">Returned opportunities by source</span>
<h3 id="panel-sources">Source Distribution</h3>
</div>
<span class="capability-pill">Coming data</span>
</header>
<div class="command-empty">
<span class="empty-mark" aria-hidden="true">&#9671;</span>
<strong>Verified data unavailable</strong>
<p>A shared unique population and denominator are pending. Configured sources are not active sources.</p>
</div>
</section>
<section class="command-panel command-small" aria-labelledby="panel-health">
<header>
<div>
<span class="eyebrow">Observed search outcomes</span>
<h3 id="panel-health">Source Health</h3>
</div>
<span class="capability-pill">Coming data</span>
</header>
<div class="command-empty">
<span class="empty-mark" aria-hidden="true">&#9671;</span>
<strong>Verified data unavailable</strong>
<p>No dashboard observation sample is connected. Existing source reports remain available in Source Health.</p>
</div>
<a class="panel-link" href="#source-health">Open existing source reports &rarr;</a>
</section>
<section class="command-panel command-small" aria-labelledby="panel-completeness">
<header>
<div>
<span class="eyebrow">Metadata coverage, separate from fit</span>
<h3 id="panel-completeness">Data Completeness</h3>
</div>
<span class="capability-pill">Coming data</span>
</header>
<div class="command-empty">
<span class="empty-mark" aria-hidden="true">&#9671;</span>
<strong>Verified data unavailable</strong>
<p>Audited present/required counts and missing-analysis coverage require 24P.3. This does not imply full-document readiness.</p>
</div>
</section>
<section class="command-panel command-opportunities" aria-labelledby="panel-opportunities">
<header>
<div>
<span class="eyebrow">Company-scoped decision queue</span>
<h3 id="panel-opportunities">Top Opportunities</h3>
</div>
<a class="panel-link" href="#discover">Open Discover &rarr;</a>
</header>
<p>Verified ranking, sorting and analytics replay arrive in 24P.3&ndash;24P.5. Discover remains available now.</p>
<div class="opportunity-columns" aria-hidden="true">
<span>Opportunity / buyer</span>
<span>Source / country</span>
<span>Deadline / value</span>
<span>Fit / completeness</span>
</div>
<div class="command-empty">
<strong>No verified analytics rows connected</strong>
<p>This is a panel container. No opportunity ranking or sortable table is active.</p>
</div>
</section>
</div>
</section>'''
