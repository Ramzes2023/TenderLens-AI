const assert=require('node:assert/strict');

const discovery=require(
 '../../app/api/static/discovery.js'
);

const preliminary={
 profile_version:'1',
 profile_name:'Pump Company',
 fit_score:55,
 completeness_percent:35,
 recommendation:'review',
 criteria:[],
 missing_information:[
  'Required documents'
 ],
 document_risks:[],
 stop_factors:[]
};

const item={
 source:'ted',
 external_id:'24l-1',
 title:'Industrial pump tender',
 url:'https://example.test/tender',
 customer:'Buyer',
 currency:'EUR',
 initial_price:250000,
 full_ai_analyzed:false,
 analysis_stage:'metadata_preview',
 metadata_analysis:{
  title:'Industrial pump tender',
  procurement_object:'industrial pumps',
  participant_requirements:[],
  technical_requirements:[],
  required_documents:[]
 },
 preliminary_scoring:preliminary
};

const result={
 duplicate:false,
 record_id:77,
 pdf_sha256:'a'.repeat(64),
 source_filename:'official-tender.pdf',
 analysis_truncated:false,
 warnings:[],
 analysis:{
  title:'Industrial pump tender',
  tender_number:'T-2026-77',
  procurement_object:'centrifugal pumps',
  participant_requirements:[
   'Manufacturer authorization'
  ],
  technical_requirements:[
   '500 m3/h flow rate'
  ],
  required_documents:[
   'ISO 9001 certificate'
  ],
  risks:[
   'Short delivery period'
  ]
 },
 scoring:{
  ...preliminary,
  fit_score:91,
  completeness_percent:94,
  missing_information:[]
 }
};

const upgraded=
 discovery.applyFullAiResult(
  item,
  result
 );

assert.equal(
 upgraded.full_ai_analyzed,
 true
);

assert.equal(
 upgraded.analysis_stage,
 'full_ai_document'
);

assert.equal(
 upgraded.full_analysis_record_id,
 77
);

assert.equal(
 upgraded.full_scoring.fit_score,
 91
);

assert.deepEqual(
 upgraded.full_analysis.required_documents,
 ['ISO 9001 certificate']
);

const card=discovery.card(
 upgraded,
 0
);

assert.match(
 card,
 /Document analysis available/
);

assert.match(
 card,
 /Full Document Match: 91%/
);

const detail=discovery.detail(
 upgraded,
 null,
 0,
 true
);

assert.match(
 detail,
 /Full document analysis/
);

assert.match(
 detail,
 /official-tender\.pdf/
);

assert.match(
 detail,
 /ISO 9001 certificate/
);

assert.match(
 detail,
 /500 m3\/h flow rate/
);

assert.match(
 detail,
 /Full AI analysis has been completed/
);

assert.match(
 detail,
 /Analyze another PDF/
);

assert.match(
 detail,
 /accept="\.pdf,application\/pdf"/
);

const readOnlyDetail=discovery.detail(
 upgraded,
 null,
 0,
 false
);

assert.doesNotMatch(
 readOnlyDetail,
 /data-full-ai="0"/
);

console.log(
 'DISCOVERY_FULL_AI_RENDER_TEST=PASS'
);
