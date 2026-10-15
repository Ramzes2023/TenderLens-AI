'use strict';
// Source audit is intentionally separate from generated HTML/browser acceptance.
const assert=require('node:assert/strict'),fs=require('node:fs');
const api=require('../../scripts/p39e_preview/view.js');
const page=fs.readFileSync('scripts/p39e_preview/page.html','utf8');
const js=fs.readFileSync('scripts/p39e_preview/view.js','utf8');
const css=fs.readFileSync('scripts/p39e_preview/style.css','utf8');
for(const match of page.matchAll(/data-i18n(?:-aria|-placeholder|-loading)?="([^"]+)"/g))
 for(const locale of ['en','ru'])assert.ok(api.translate(locale,match[1]));
assert.match(page,/data-i18n-loading="loading"/);
assert.match(js,/\['data-i18n-loading',null\]/);
assert.doesNotMatch(page+js+css,/fetch\s*\(|XMLHttpRequest|WebSocket|EventSource|navigator\.sendBeacon|innerHTML|<script\s+src=|<link\b|@import|url\s*\(/i);
assert.doesNotMatch((page+js+css).replaceAll('http://www.w3.org/2000/svg',''),/https?:\/\//);
assert.match(css,/color-scheme:dark/);
assert.match(css,/:focus-visible/);
assert.match(css,/prefers-reduced-motion/);
assert.match(js,/textContent=String\(text\)/);
assert.match(js,/data-record-id/);
for(const locale of ['en','ru']){
 assert.ok(api.translate(locale,'badge'));
 assert.ok(api.translate(locale,'fitCopy'));
 assert.ok(api.translate(locale,'storageDenied'));
}
console.log('P39H OFFLINE SOURCE CONTRACT PASS: translation keys/loading, dark/accessibility hooks, textContent, no external resources/network code. Generated HTML and real browser acceptance remain separate.');
