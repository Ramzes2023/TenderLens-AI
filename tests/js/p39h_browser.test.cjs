'use strict';
// Optional real-browser acceptance. Uses installed Playwright/browser only; no downloads or server.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {pathToFileURL}=require('node:url'),{chromium}=require('playwright');
(async()=>{
 const file=pathToFileURL(path.resolve(process.argv[2])).href;
 const executablePath=process.env.P39H_BROWSER;
 assert.ok(executablePath,'Set P39H_BROWSER to an already installed Chromium browser');
 const browser=await chromium.launch({executablePath,headless:true,args:['--disable-background-networking','--disable-component-update','--disable-sync','--disable-extensions','--disable-domain-reliability','--no-first-run','--no-proxy-server','--host-resolver-rules=MAP * ~NOTFOUND']});
 const errors=[],requests=[],output=fs.mkdtempSync(path.join(os.tmpdir(),'valyqon-p39h-'));
 try{
  const context=await browser.newContext();
  await context.route('**/*',route=>{if(route.request().url().startsWith('file:'))return route.continue();requests.push(route.request().url());return route.abort();});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto(file);assert.equal(await page.locator('html').getAttribute('lang'),'en');
  const fixture=await page.locator('#fixture').textContent();
  for(const viewport of [{width:1440,height:1000},{width:360,height:800}]){
   await page.setViewportSize(viewport);
   for(const locale of ['en','ru']){
    await page.locator('#lang-'+locale).click();
    assert.equal(await page.locator('html').getAttribute('lang'),locale);
    for(const scenario of ['normal','empty','unknown','legacy','foreign','future','filtered']){
     await page.locator('#scenario').selectOption(scenario);assert.equal(await page.locator('#cards button').count(),6);
     await page.locator('#cards button').nth(2).click();assert.ok((await page.locator('#detail').textContent()).length>0);
     await page.locator('#reset').click();
    }
    await page.locator('#scenario').selectOption('normal');
    assert.deepEqual(await page.locator('#cards strong').allTextContents(),['4','2','2','1','1','1']);
    await page.locator('#search').fill('zero');assert.equal(await page.locator('#records button').count(),1);
    await page.locator('#lang-'+(locale==='en'?'ru':'en')).click();assert.equal(await page.locator('#search').inputValue(),'zero');assert.equal(await page.locator('#records button').count(),1);
    await page.locator('#lang-'+locale).click();await page.locator('#reset').click();
    await page.locator('#fit-filter').selectOption('high');assert.equal(await page.locator('#records button').count(),2);await page.locator('#reset').click();
    await page.locator('#deadline-filter').selectOption('instant / future');assert.equal(await page.locator('#records button').count(),1);await page.locator('#reset').click();
    await page.locator('#sort').selectOption('identity-desc');assert.equal(await page.locator('#records strong').first().textContent(),'ted / zero');await page.locator('#reset').click();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true,'No horizontal page overflow');
    await page.locator('#lang-'+locale).focus();await page.keyboard.press('Enter');assert.equal(await page.locator('html').getAttribute('lang'),locale);
    await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(output,`${viewport.width}-${locale}.png`),fullPage:true});
   }
  }
  await page.locator('#lang-ru').click();await page.reload();assert.equal(await page.locator('html').getAttribute('lang'),'ru');
  assert.equal(await page.locator('#fixture').textContent(),fixture);assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
  console.log('P39H BROWSER PASS: real file:// Chromium; EN/RU × 1440/360; seven scenarios, keyboard, filters, reload persistence, CSP execution, no external requests/page errors; screenshots='+output);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});