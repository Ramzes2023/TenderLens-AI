"""Public guest search markup. Results are populated only by the real DB API."""

GUEST_SEARCH_HTML = """<section id="guest-search" class="guest-search-zone" aria-labelledby="guest-title">
<div class="guest-search-panel">
  <div class="guest-search-head">
    <span class="guest-label">VALYQON AI · GUEST SEARCH</span>
    <h2 id="guest-title">Search real procurement notices <span>without signing in</span></h2>
    <p>Search notices already stored by connected VALYQON AI source adapters. No fabricated results.</p>
  </div>
  <form id="guestSearchForm" class="guest-search-form" role="search" autocomplete="off">
    <label class="guest-sr-only" for="guestSearchInput">What would you like to find?</label>
    <input id="guestSearchInput" name="q" type="search" maxlength="120"
      placeholder="For example: medical equipment, construction, fuel" />
    <button type="submit" id="guestSearchButton">Search tenders ↗</button>
  </form>
  <div class="guest-popular" aria-label="Sample search keywords">
    <span>Explore topics:</span>
    <button type="button" data-guest-term="строительство">Construction</button>
    <button type="button" data-guest-term="медицинское">Medical</button>
    <button type="button" data-guest-term="оборудование">Equipment</button>
    <button type="button" data-guest-term="услуги">Services</button>
  </div>
</div>
<div class="guest-results-layout">
 <div class="guest-results-main">
  <div class="guest-results-heading">
    <div><span class="guest-kicker">RESULTS FROM OUR DATABASE</span>
      <h3>Limited tender previews</h3>
      <p id="guestSearchStatus" role="status" aria-live="polite">Loading recently stored notices…</p>
    </div>
    <span class="guest-no-demo">● Only stored connector notices</span>
  </div>
  <div id="guestSearchResults" class="guest-result-list" aria-label="Guest search results"></div>
  <p class="guest-reality-note">This is a limited selection of stored notices, not a live query to upstream procurement portals. Verify the official notice and any deadline before making decisions.</p>
 </div>
 <aside class="guest-unlock">
  <span class="guest-unlock-icon" aria-hidden="true">✦</span>
  <span class="guest-kicker">FULL ACCESS</span>
  <h3>All details in your workspace</h3>
  <p>Guest access includes notice titles, available prices and submission deadlines only.</p>
  <ul>
    <li>Buyer identity and contacts</li>
    <li>Source platform and original notice URL</li>
    <li>Requirements and documents</li>
    <li>Participation terms and full analysis</li>
  </ul>
  <a class="guest-register-cta" href="/register">Create account →</a>
  <p class="guest-pay-note">Full commercial access will require an active subscription. Payment collection is not enabled yet.</p>
 </aside>
</div>
</section>"""
