"""Premium public landing product demonstration and honest market-pulse copy.

No fabricated tender cards, amounts, customers, AI win forecasts or source names:
the hero is a clearly marked illustrative workflow; the separate market pulse
fetches anonymized, database-backed aggregate counts.
"""

HERO_SCENE_HTML = """<aside class="vq-stage" aria-label="Interactive product preview">
  <div class="vq-stage-head">
    <span class="vq-stage-brand"><span class="vq-mark" aria-hidden="true">V</span> VALYQON <b>AI</b></span>
    <span class="vq-stage-proof">INTERACTIVE DEMO · NO LIVE TENDERS</span>
  </div>
  <div class="vq-stage-main">
    <div class="vq-stage-nav" role="group" aria-label="Explore the workflow">
      <button type="button" class="vq-step-button is-active" data-vq-step="discover" aria-pressed="true"><span>01</span> Discover</button>
      <button type="button" class="vq-step-button" data-vq-step="assess" aria-pressed="false"><span>02</span> Assess</button>
      <button type="button" class="vq-step-button" data-vq-step="coordinate" aria-pressed="false"><span>03</span> Coordinate</button>
    </div>
    <div class="vq-stage-content">
      <div class="vq-stage-label"><span class="vq-live-dot" aria-hidden="true"></span> WORKFLOW PREVIEW</div>
      <h3 id="vqStageTitle" aria-live="polite">Find opportunities that match your focus</h3>
      <p id="vqStageDescription">Search persisted procurement notices, then open a qualified workspace for the evidence.</p>
      <div class="vq-stage-visual" aria-hidden="true">
        <div class="vq-stage-skeleton"><i></i><i></i><i></i></div>
        <div class="vq-stage-orb">✦</div>
        <div class="vq-stage-doc vq-stage-doc-left"><span>01</span><i></i><i></i></div>
        <div class="vq-stage-doc vq-stage-doc-right"><span>02</span><i></i><i></i></div>
        <div class="vq-stage-trail"></div>
      </div>
      <div class="vq-stage-footer"><span><span aria-hidden="true">✓</span> Real connector data in search</span><span>Source details remain protected</span></div>
    </div>
  </div>
  <div class="vq-stage-footnote">No search has been run here. Illustrative interface only; search results are loaded separately from the real database below.</div>
</aside>"""

MARKET_PULSE_HTML = """<section class="vq-pulse-section" id="market-pulse" aria-labelledby="vqPulseHeading">
  <div class="vq-pulse-head">
    <div>
      <span class="vq-section-eyebrow">PUBLIC DATA INSIGHT</span>
      <h2 id="vqPulseHeading">A clearer view of activity. <span>No invented statistics.</span></h2>
      <p>See how many previously unseen source notices entered the VALYQON database over the last 14 UTC days. This is a limited stored-data sample, not the entire tender market.</p>
    </div>
    <a class="vq-pulse-link" href="#guest-search">Try your own search ↗</a>
  </div>
  <div class="vq-pulse-board">
    <div class="vq-pulse-topline">
      <div class="vq-pulse-metric"><span>New notices in sampled data · 14 days</span><strong id="vqPulseTotal">—</strong></div>
      <div class="vq-pulse-metric"><span>Saved rows checked</span><strong id="vqPulseSample">—</strong></div>
      <span class="vq-pulse-verified">Database-backed, not illustrated</span>
    </div>
    <div class="vq-pulse-chart-head"><h3>Daily first observations</h3><span id="vqPulseRange">Last 14 UTC days</span></div>
    <div id="vqPulseChart" class="vq-pulse-chart" role="img" aria-label="Daily newly stored notices; awaiting data"></div>
    <p class="vq-pulse-status" id="vqPulseStatus" role="status" aria-live="polite">Loading actual database observations…</p>
    <p class="vq-pulse-note">A graph of stored notices, not a forecast or proof that every procurement platform is operating. Connector outages and late collection can change these figures.</p>
  </div>
</section>"""

PUBLIC_SUPPORT_HTML = """<section class="vq-support-strip" aria-labelledby="vqSupportHeading">
  <div class="vq-support-icon" aria-hidden="true">✦</div>
  <div><span class="vq-section-eyebrow">PRODUCT GUIDANCE</span><h2 id="vqSupportHeading">Questions about finding tenders?</h2><p>Explore quick product answers or open your authenticated Support Center to send a request. Human availability is not implied.</p></div>
  <button type="button" id="vqOpenHelp" class="vq-support-button" aria-expanded="false" aria-controls="vqHelpDrawer">Ask a question ↗</button>
</section>
<div id="vqHelpDrawer" class="vq-help-drawer" hidden role="region" aria-label="Product information assistant">
  <div class="vq-help-header"><div><span class="vq-help-avatar" aria-hidden="true">✦</span><strong>VALYQON product guide</strong><small>Quick answers · AI when configured</small></div><button id="vqCloseHelp" type="button" aria-label="Close help">×</button></div>
  <div id="vqHelpContent" class="vq-help-content" role="status" aria-live="polite">Choose a topic to see a reliable answer about VALYQON AI.</div>
  <div class="vq-help-topics" role="group" aria-label="Common questions">
    <button type="button" data-vq-help="search">How does guest search work?</button>
    <button type="button" data-vq-help="source">Where are the source links?</button>
    <button type="button" data-vq-help="payment">How do subscriptions work?</button>
    <button type="button" data-vq-help="privacy">Is my company data public?</button>
  </div>
  <form id="vqAskAIForm" class="vq-help-ai-form">
    <label for="vqAIQuestion">Ask the AI about VALYQON AI</label>
    <textarea id="vqAIQuestion" name="question" rows="2" minlength="3" maxlength="450" placeholder="For example: how does tender search work?" required></textarea>
    <button type="submit" id="vqAISend">Ask AI ↗</button>
    <p id="vqAIStatus" role="status" aria-live="polite">AI answers are available only when the provider is configured. Do not share private information.</p>
  </form>
  <a class="vq-help-contact" href="/dashboard#support">Open Support Center to send a message →</a>
  <p>Sign-in is required to create a support request. The authenticated workspace includes AI support where configured.</p>
</div>
<button type="button" class="vq-help-bubble" id="vqFloatingHelp" aria-label="Open product help" aria-controls="vqHelpDrawer" aria-expanded="false" title="Product help">✦</button>"""
