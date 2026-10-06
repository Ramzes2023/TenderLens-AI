const assert = require("node:assert/strict");

const {
  card,
  detail,
} = require("../../app/api/static/discovery.js");

const item = {
  source: "eis",
  external_id: "notice-123",
  title: "Industrial pump supply",
  customer: "Test Buyer",
  tender_number: "T-123",
  initial_price: 100000,
  currency: "RUB",
  region: "Test Region",
  deadline: "2026-11-01",
  published_at: "2026-10-01",
  summary: "Supply of industrial pumps.",
  full_ai_analyzed: false,
  metadata_analysis: {
    procurement_object: "Industrial pumps",
    participant_requirements: [],
    technical_requirements: [],
    required_documents: [],
  },
  preliminary_scoring: {
    fit_score: 70,
    completeness_percent: 60,
    criteria: [],
    missing_information: [],
    document_risks: [],
    stop_factors: [],
  },
};

const unsavedCard = card(
  item,
  4,
  null,
);

assert.match(
  unsavedCard,
  /data-save="4">Save opportunity/,
);

const savedCard = card(
  item,
  4,
  {
    id: 91,
  },
);

assert.match(
  savedCard,
  />Saved<\/button>/,
);

assert.doesNotMatch(
  savedCard,
  /data-save="4"/,
);

const unsavedDetail = detail(
  item,
  null,
  4,
);

assert.match(
  unsavedDetail,
  /data-save="4">Save opportunity/,
);

const savedDetail = detail(
  item,
  {
    id: 91,
  },
  4,
);

assert.match(
  savedDetail,
  /data-remove="4">Remove from saved/,
);

const legacyCard = card(
  item,
  4,
);

assert.doesNotMatch(
  legacyCard,
  /Save opportunity|>Saved<\/button>/,
);

const legacyDetail = detail(
  item,
);

assert.doesNotMatch(
  legacyDetail,
  /Save opportunity|Remove from saved/,
);

console.log(
  "SHORTLIST_UI_RENDER_TEST=PASS"
);
