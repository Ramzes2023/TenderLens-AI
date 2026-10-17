"""Billing section for verified first-party usage and honest payment readiness."""
BILLING_HTML = """
<section id="billingWorkspace" class="p" data-page="billing" hidden>
  <span class="eyebrow">COMPANY ACCOUNT</span>
  <h2>Billing &amp; subscription</h2>
  <p>No commercial checkout is enabled in this pilot. This view shows
     recorded workspace usage, not an active paid subscription or invoice.</p>
  <button id="refreshBilling" type="button">Refresh account overview</button>
  <p id="billingMessage" role="status">Select a shared organization to view its billing readiness.</p>
  <div class="overview-metrics">
    <article><small>Subscription</small><strong id="billingPlan">Not enabled</strong><span id="billingNextCharge">No scheduled charge</span></article>
    <article><small>Recorded searches</small><strong id="billingSearches">—</strong><span>Not a billed amount</span></article>
    <article><small>Saved opportunities</small><strong id="billingSaved">—</strong><span>Organization total</span></article>
    <article><small>Team seats</small><strong id="billingSeats">—</strong><span>Organization members</span></article>
  </div>
  <h3>Payments and accounting documents</h3>
  <p>Payment history: <strong id="billingPayments">No verified transactions available</strong></p>
  <p>Invoices/closing documents: <strong id="billingInvoices">Not available until a merchant and invoicing integration is verified</strong></p>
  <button type="button" id="upgradeBilling" disabled>Upgrade plan — unavailable</button>
  <p>Automatic invoices, VAT/accounting details and legally valid closing documents
     require approved company details and a live payment/invoice provider.
     No fictitious transactions are shown.</p>
</section>
"""
