const assert = require('node:assert/strict');
const {scoredTop} = require('../../app/api/static/first_run.js');
const sample=[
 {source:'eis',external_id:'2',title:'Lower',preliminary_scoring:{fit_score:20}},
 {source:'ted',external_id:'1',title:'Higher',preliminary_scoring:{fit_score:89}},
 {source:'ted',external_id:'3',title:'Unknown',preliminary_scoring:{}},
 {title:'synthetic',preliminary_scoring:{fit_score:99}}
];
assert.deepEqual(scoredTop(sample).map(row=>row.external_id),['1','2','3']);
assert.deepEqual(scoredTop([]),[]);
console.log('FIRST_RUN_RANKING=PASS');
