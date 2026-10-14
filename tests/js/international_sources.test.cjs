const assert = require('node:assert/strict');
const discovery = require('../../app/api/static/discovery.js');
const item = {source:'world_bank',external_id:'100003',title:'Construction',
  url:'https://projects.worldbank.org/en/projects-operations/procurement-detail/OP00100003',
  deadline:'2026-11-01',published_at:'2026-10-14',preliminary_scoring:{fit_score:null}};
assert.equal(discovery.officialUrl(item),item.url);
assert.equal(discovery.officialUrl({...item,url:'https://projects.worldbank.org.evil.test/a'}),null);
assert.match(discovery.card(item,0),/Open official source/);
const health=discovery.sourceOutcomes({source_statuses:[{source:'world_bank',display_name:'World Bank Finances One',state:'healthy',notice_count:0,coverage:'Seven calendar days; local matching',last_successful_sync:'2026-10-14T12:00:00Z'}]});
assert.match(health,/World Bank Finances One/);
assert.match(health,/Seven calendar days/);
assert.match(health,/Last successful sync/);
assert.match(discovery.sourceMessage({items:[],attempted_sources:[]}),/No enabled source was checked/);
assert.match(discovery.sourceMessage({items:[],attempted_sources:['world_bank'],successful_sources:['world_bank']}),/bounded source coverage/);
console.log('International source rendering, health, official links and zero-checked distinction: PASS');
