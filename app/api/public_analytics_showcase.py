"""Visual landing components for a full procurement intelligence SaaS.

No fake tenders, financial projections, source health or competitor figures.
All KPI values start as dashes until the real anonymized DB API responds.
"""
HERO_DASHBOARD_HTML = """<aside class="vqx-product" aria-label="Live-data product showcase">
 <div class="vqx-product-toolbar"><div class="vqx-window-controls" aria-hidden="true"><i></i><i></i><i></i></div><b>VALYQON <em>AI</em></b><span>PRODUCT TOUR <span aria-hidden="true">✦</span></span></div>
 <div class="vqx-product-frame">
  <div class="vqx-rail">
   <span class="vqx-rail-caption">INTELLIGENCE</span>
   <button type="button" class="vq-step-button is-active" data-vq-step="discover" aria-pressed="true"><span>◉</span> Search</button>
   <button type="button" class="vq-step-button" data-vq-step="assess" aria-pressed="false"><span>▥</span> Analytics</button>
   <button type="button" class="vq-step-button" data-vq-step="coordinate" aria-pressed="false"><span>◇</span> Workspace</button>
   <div class="vqx-rail-line"></div><span class="vqx-rail-caption">EXPLORE</span>
   <span class="vqx-rail-link">▦ Reports</span><span class="vqx-rail-link">♧ Team</span>
  </div>
  <div class="vqx-product-body">
   <div class="vqx-preview-heading"><div><small>PRODUCT WORKFLOW</small><h3 id="vqStageTitle" aria-live="polite">Find opportunities that match your focus</h3></div><span class="vqx-active-dot">● Overview</span></div>
   <p id="vqStageDescription">Search persisted procurement notices, then open a qualified workspace for the evidence.</p>
   <div class="vqx-search-faux"><span aria-hidden="true">⌕</span><span>Search tenders, markets and requirements</span><a href="#guest-search">Search →</a></div>
   <div class="vqx-hero-kpis">
    <div><span>Saved records sampled</span><strong id="vqxHeroTotal">—</strong><small>Recorded notices, not total market</small></div>
    <div><span>New observations · 14d</span><strong id="vqxHeroFresh">—</strong><small>From saved connector data</small></div>
    <div><span>With starting prices</span><strong id="vqxHeroPriced">—</strong><small>Field availability only</small></div>
   </div>
   <div class="vqx-hero-chart"><div class="vqx-panel-title"><span>Daily procurement observations</span><small>LAST 14 UTC DAYS</small></div>
    <svg id="vqxHeroLine" viewBox="0 0 450 124" role="img" aria-label="Graph waiting for observed procurement records"></svg>
    <div class="vqx-axis-note">Live from stored records · Not a simulated market trend</div>
   </div>
   <div class="vqx-hero-bottom"><span>◈ Source data protected</span><span>◉ Transparent sample scope</span></div>
  </div>
 </div>
 <div class="vqx-tour-foot">INTERACTIVE DEMO · NO LIVE TENDERS IN THE ILLUSTRATION. No search has been run here. Metrics come from stored data unless the optional local illustrative-chart mode is visibly enabled.</div>
</aside>"""

ANALYTICS_WALL_HTML = """<section class="vqx-analytics" id="market-analytics" aria-labelledby="vqxAnalyticsHeading">
 <div class="vqx-section-bar"><div><span class="vqx-eyebrow">PROCUREMENT DATA STUDIO <i></i> DEMO OR VERIFIED SNAPSHOT</span>
  <h2 id="vqxAnalyticsHeading">Procurement intelligence, <span>clearly visualized.</span></h2>
  <p>Explore the procurement intelligence interface. Demonstration figures are clearly labelled; real-data mode reads only persisted connector observations.</p></div>
  <a class="vqx-text-cta" href="#guest-search">Search opportunities <span aria-hidden="true">↗</span></a></div>
 <div class="vqx-review-toggle" id="vqxReviewTools" hidden><div><strong>LOCAL DESIGN REVIEW ONLY</strong><span id="vqxReviewDisclosure">Illustrative charts can be enabled for layout inspection. They are not real procurement statistics, and guest search stays unchanged.</span></div><button type="button" id="vqxToggleDemo" aria-pressed="false">Show illustrative chart layout</button></div>
 <div class="vqx-stats-row">
  <article class="vqx-stat"><div class="vqx-stat-top"><span class="vqx-stat-icon">▣</span><small>Records scanned</small></div><strong id="vqxStatObserved">—</strong><p>Recently stored connector notices</p></article>
  <article class="vqx-stat"><div class="vqx-stat-top"><span class="vqx-stat-icon purple">⌁</span><small>New · 14 days</small></div><strong id="vqxStatNew">—</strong><p>First seen in UTC window</p></article>
  <article class="vqx-stat"><div class="vqx-stat-top"><span class="vqx-stat-icon cyan">◈</span><small>Prices specified</small></div><strong id="vqxStatPriced">—</strong><p>Valid starting amount recorded</p></article>
  <article class="vqx-stat"><div class="vqx-stat-top"><span class="vqx-stat-icon amber">◷</span><small>Deadline specified</small></div><strong id="vqxStatDeadline">—</strong><p>Parseable submission date recorded</p></article>
 </div>
 <div class="vqx-analysis-grid">
  <article class="vqx-data-card vqx-card-wide"><div class="vqx-card-top"><div><span class="vqx-card-kicker">OBSERVATIONS</span><h3>Daily procurement activity</h3></div><label class="vqx-range-label">Period <select id="vqxDaysRange" aria-label="Activity period"><option value="14">14 days</option><option value="7">7 days</option></select></label></div>
   <div class="vqx-legend"><span><i class="blue"></i> Notices</span><span><i class="violet"></i> With known price</span></div>
   <svg id="vqxDailyChart" class="vqx-main-svg" viewBox="0 0 720 238" role="img" aria-label="Daily saved procurement notices: awaiting live data"></svg>
   <div class="vqx-chart-foot" id="vqxDailyCaption">Waiting for recorded observations…</div>
  </article>
  <article class="vqx-data-card"><div class="vqx-card-top"><div><span class="vqx-card-kicker">FINANCIAL BANDS</span><h3>Starting price distribution</h3></div><span class="vqx-tiny-tag">RUB ONLY</span></div>
   <div class="vqx-donut-layout"><div id="vqxPriceDonut" class="vqx-donut" role="img" aria-label="Ruble price distribution waiting for data"><div class="vqx-donut-center"><strong id="vqxDonutTotal">—</strong><small>priced RUB records</small></div></div><div id="vqxPriceLegend" class="vqx-donut-legend"></div></div>
   <div class="vqx-chart-foot">Counts by starting-price band, never combined across currencies.</div>
  </article>
  <article class="vqx-data-card"><div class="vqx-card-top"><div><span class="vqx-card-kicker">TIME WINDOW</span><h3>Recent observation momentum</h3></div><span class="vqx-tiny-tag">TWO 7-DAY PERIODS</span></div>
   <div id="vqxWeeksBars" class="vqx-weeks-bars"></div>
   <div class="vqx-chart-foot">Not a forecast or official publishing rate.</div>
  </article>
  <article class="vqx-data-card"><div class="vqx-card-top"><div><span class="vqx-card-kicker">PROCUREMENT DEADLINES</span><h3>Submission horizon</h3></div><span class="vqx-tiny-tag">UTC DATES</span></div>
   <div id="vqxDeadlineBars" class="vqx-hbars"></div>
   <div class="vqx-chart-foot">Based only on available dates in this sample.</div>
  </article>
  <article class="vqx-data-card"><div class="vqx-card-top"><div><span class="vqx-card-kicker">BUDGET LANDSCAPE</span><h3>Ruble notice price bands</h3></div><span class="vqx-tiny-tag">COUNT</span></div>
   <div id="vqxPriceHistogram" class="vqx-histogram"></div>
   <div class="vqx-chart-foot">Starting prices only; not awarded contract values.</div>
  </article>
  <article class="vqx-data-card"><div class="vqx-card-top"><div><span class="vqx-card-kicker">CURRENCY COVERAGE</span><h3>Declared currencies</h3></div><span class="vqx-tiny-tag">NOTICE COUNT</span></div>
   <div id="vqxCurrencyBars" class="vqx-hbars"></div>
   <div class="vqx-chart-foot">Currency counts, not monetary value comparisons.</div>
  </article>
  <article class="vqx-data-card vqx-card-wide"><div class="vqx-card-top"><div><span class="vqx-card-kicker">DATA QUALITY</span><h3>How complete are stored opportunities?</h3></div><span class="vqx-tiny-tag">FIELD PRESENCE</span></div>
   <div id="vqxCoverageBars" class="vqx-completeness"></div>
   <div class="vqx-chart-foot">These bars reflect field availability, not source reliability or procurement outcome probability.</div>
  </article>
 </div>
 <div class="vqx-source-notice"><span class="vqx-source-led">◉</span><div><strong id="vqxIntelligenceStatus" role="status" aria-live="polite">Connecting to saved procurement observations…</strong><p>Public demonstration figures are illustrative, not actual market observations. Real-data mode uses a bounded aggregate sample, without customer identities or source links.</p></div><a href="#coverage">Source directory ↗</a></div>
</section>"""
