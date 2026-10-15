'use strict';
// Static acceptance contract, explicitly NOT authenticated browser evidence.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const harness = fs.readFileSync(path.join(root, 'scripts/phase24_v7_browser_postgres_acceptance.py'), 'utf8');
const ui = fs.readFileSync(path.join(root, 'app/api/static/discovery.js'), 'utf8');

test('Saved reload reselects the real shared workspace before checking persistence', () => {
  const organizationUi = fs.readFileSync(path.join(root, 'app/api/organization_ui.py'), 'utf8');
  // Actual initialization chooses defaultOrganization on a fresh page.
  assert.match(organizationUi, /state\.organizationId=\s*defaultOrganization\.id/);
  const reload = harness.slice(harness.indexOf('                page.reload()'));
  const selection = reload.indexOf("page.select_option('#organizationSelect', str(organizations[0]))");
  const saved = reload.indexOf('browser persisted Saved fixture after reload');
  assert.ok(selection > 0 && saved > selection);
  assert.ok(reload.includes('state.activeCompanyId===ids[1]'));
  assert.ok(reload.includes("page.locator('#savedResults .tender-card').count() == 1"));
  assert.ok(harness.includes('with page.expect_response('));
  assert.ok(harness.includes('saved_response.value.status == 200'));
});

test('unknowns render real not-scored criteria when extraction list is empty', () => {
  // Execute the shipped pure renderer; this is regression coverage, not browser acceptance.
  const start = ui.indexOf('function decisionHtml(item){');
  const end = ui.indexOf('\nfunction sourceOutcomes', start);
  const escape = value => String(value).replaceAll('<', '&lt;').replaceAll('>', '&gt;');
  const render = Function('escape', 'bilingual', 'list',
    ui.slice(start, end) + '\nreturn decisionHtml;')(escape, () => '',
      values => values.map(escape).join('|'));
  const html = render({preliminary_scoring:{missing_information:[], criteria:[
    {code:'documents',label:'Documents',status:'not_scored',earned_points:0,
     explanation:'No list of required documents was found <img>'},
    {code:'category',status:'matched',explanation:'Product match'}]}});
  const unknowns = html.split('Unknowns to verify</h4>')[1];
  assert.ok(unknowns.includes('Documents: No list of required documents was found &lt;img&gt;'));
  assert.ok(!unknowns.includes('Product match'));
  assert.ok(!unknowns.includes('<img>'));
});

test('V7 requires native Chromium form login, DOM and screenshot', () => {
  for (const marker of ['launch_persistent_context', "page.fill('#email'", "page.fill('#password'",
    "page.click('#submit')", "page.locator('#discoverButton').click()", 'page.screenshot(',
    'context.close()', 'temporary_profile_removed']) assert.ok(harness.includes(marker), marker);
  assert.ok(!harness.includes('TestClient'));
});
test('runtime gates follow execution and distinct persistence assertions', () => {
  assert.ok(harness.indexOf("report['authenticated_browser'] = 'VERIFIED'") > harness.indexOf('no stale discovery after switch'));
  assert.ok(harness.indexOf("report['authenticated_api'] = report['postgres_saved_persistence']") > harness.indexOf('saved survives company switch'));
  for (const marker of ['database initially empty', 'independent PostgreSQL saved row read',
    'browser save persisted in PostgreSQL', 'company saved isolation', 'tenant saved isolation']) assert.ok(harness.includes(marker));
});
test('bounded resources and source-only offline transport', () => {
  for (const marker of ['--pull=never', '--cpus=1', '--memory=512m', '--pids-limit=128',
    '--tmpfs', '127.0.0.1:', 'OFFLINE_FIXTURE', 'process.terminate()', "'--volumes'",
    'dotenv.load_dotenv =', 'os.environ.clear()']) assert.ok(harness.includes(marker), marker);
  assert.ok(!harness.includes('pip install'));
  assert.ok(!harness.includes('docker ps'));
});
test('browser assertions target current UI controls and escaped cards', () => {
  for (const marker of ['discoverButton', 'discoveryResults', 'data-save', 'workspace-context']) assert.ok(ui.includes(marker));
  assert.ok(ui.includes('escape(item.title'));
  assert.ok(ui.includes('noopener noreferrer'));
});

test('host readiness and durable screenshot are independent runtime requirements', () => {
  for (const marker of ['host_tcp_ready(config[', "stages['host_authentication'] = 'VERIFIED'",
    "'-h', '127.0.0.1', '-p', '5432'", 'child_environment(config)',
    "retained['DATABASE_URL'] = config['url']", 'enable_ip_masquerade=false',
    'screenshot_survived(report)', 'screenshot_exists_after_cleanup', 'page.reload()']) {
    assert.ok(harness.includes(marker), marker);
  }
  assert.ok(harness.indexOf("stages['host_authentication'] = 'VERIFIED'") < harness.indexOf('process.start()'));
  assert.ok(harness.indexOf('survived = screenshot_survived(report)') > harness.indexOf('temp.cleanup()'));
  assert.ok(!harness.includes('vm.run'));
});
