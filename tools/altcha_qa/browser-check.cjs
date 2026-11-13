/* Optional QA runner: npm install playwright, then node this file.
 * Never use a production URL. Blocks non-loopback traffic, including CDNs.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = new URL(process.env.ALTCHA_QA_URL || 'http://rastisi.localhost:8013');
if (!['localhost', '127.0.0.1', 'rastisi.localhost'].includes(base.hostname)) throw Error('Loopback preview only');
const out = process.env.ALTCHA_QA_OUTPUT || path.join(__dirname, '../../.altcha-qa/browser');
fs.mkdirSync(out, { recursive: true });
const stats = values => {
  const a = [...values].sort((x,y)=>x-y);
  return { n:a.length, min:Math.round(a[0]), median:Math.round(a[Math.floor(a.length/2)]), p95:Math.round(a[Math.ceil(a.length*.95)-1]), max:Math.round(a.at(-1)) };
};
(async()=>{
  const browser = await chromium.launch({headless:true, args:['--no-sandbox']});
  const results = { browser: browser.version(), date: new Date().toISOString(), profiles: [], checks: [], externalRequestsBlocked: [], errors: [] };
  try {
    for (const profile of [
      {name:'desktop', viewport:{width:1440,height:1000}, isMobile:false, hasTouch:false, rate:1},
      {name:'mobile', viewport:{width:390,height:844}, isMobile:true, hasTouch:true, rate:1},
      {name:'mobile-cdp-6x', viewport:{width:390,height:844}, isMobile:true, hasTouch:true, rate:6},
    ].filter(p=>!process.env.ALTCHA_QA_PROFILE || p.name===process.env.ALTCHA_QA_PROFILE)) {
      const context = await browser.newContext({viewport:profile.viewport,isMobile:profile.isMobile,hasTouch:profile.hasTouch,deviceScaleFactor:profile.isMobile?2:1});
      await context.route('**/*', route => {
        const u = new URL(route.request().url());
        if (['blob:','data:'].includes(u.protocol) || u.hostname === base.hostname) return route.continue();
        results.externalRequestsBlocked.push(u.origin+u.pathname); return route.abort();
      });
      const page = await context.newPage();
      page.on('pageerror', e => results.errors.push(e.message));
      const cdp = await context.newCDPSession(page);
      await cdp.send('Emulation.setCPUThrottlingRate',{rate:profile.rate});
      const ready=[], verify=[], challenge=[];
      for(let n=0;n<10;n++) {
        const start=Date.now();
        await page.goto(new URL('/contact/',base).href,{waitUntil:'domcontentloaded'});
        const widget = page.locator('#captcha-contact');
        const checkbox = widget.locator('input[type="checkbox"]');
        await checkbox.waitFor({state:'visible'});
        const appearedMs = Date.now()-start;
        assert.equal(await widget.evaluate(w=>getComputedStyle(w).direction),'rtl');
        assert.match(await widget.innerText(),/من ربات نیستم/);
        const box = await checkbox.boundingBox();
        assert.ok(box.width>=20 && box.width<=30 && box.height>=20 && box.height<=30, JSON.stringify(box));
        if(n===0)await page.locator('.rasti-altcha').screenshot({path:path.join(out,profile.name+'-unverified.png')});
        ready.push(appearedMs);
        const response = page.waitForResponse(r=>r.url().includes('/security/altcha/contact/'));
        response.catch(()=>{});
        const clicked=Date.now();
        await checkbox.click();
        const fetched = await response;
        assert.equal(fetched.status(),200);
        challenge.push(Date.now()-clicked);
        await page.waitForFunction(()=>document.querySelector('#captcha-contact').getState()==='verified',null,{timeout:15000});
        verify.push(Date.now()-clicked);
        assert.ok(await widget.evaluate(w=>w.closest('form').querySelector('input[name="altcha"]').value.length>100));
        if(n===0){
          await page.waitForTimeout(750); // finish the official checkmark animation for evidence only
          await page.locator('.rasti-altcha').screenshot({path:path.join(out,profile.name+'-verified.png')});
        }
      }
      results.profiles.push({name:profile.name,viewport:profile.viewport,cdpCpuRate:profile.rate,widgetReadyMs:stats(ready),clickToVerifiedMs:stats(verify),challengeResponseMs:stats(challenge),samples:{ready,verify,challenge}});
      if(profile.name==='desktop'){
        for(const [url,actions] of [['/login/',['login_password','login_otp']],['/register/',['register']],['/reset-password/',['password_reset']]]){
          await page.goto(new URL(url,base).href);
          for(const action of actions){
            const w=page.locator('#captcha-'+action);
            // OTP lives in the alternative login panel.
            if(!(await w.isVisible())){
              await page.locator('[data-auth-tab="otp"], [data-login-tab="otp"]').first().click();
            }
            await w.locator('input[type="checkbox"]').click();
            await page.waitForFunction(a=>document.querySelector('#captcha-'+a).getState()==='verified',action,{timeout:15000});
            results.checks.push(action+': real widget proof solved');
          }
        }
        await page.goto(new URL('/contact/',base).href);
        const form = page.locator('#captcha-contact').locator('xpath=ancestor::form');
        await form.evaluate(f=>f.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
        assert.match(await page.locator('.rasti-altcha-status').innerText(),/ابتدا/);
        assert.equal(await form.locator('[type="submit"]').isDisabled(),false);
        results.checks.push('unverified submit blocked without locking submit button');
        await page.locator('#id_full_name').fill('ALTCHA local browser QA');
        await page.locator('#id_email').fill('altcha-qa@example.com');
        await page.locator('#id_subject').fill('Local proof verification');
        await page.locator('#id_message').fill('Disposable local browser proof-of-work integration test.');
        await page.locator('#captcha-contact input[type="checkbox"]').click();
        await page.waitForFunction(()=>document.querySelector('#captcha-contact').getState()==='verified');
        const submitted = await form.evaluate(f=>Object.fromEntries(new FormData(f)));
        const [accepted] = await Promise.all([
          page.waitForResponse(r=>r.request().method()==='POST' && new URL(r.url()).pathname==='/contact/'),
          form.locator('[type="submit"]').click(),
        ]);
        assert.equal(accepted.status(),302);
        const replay = await context.request.post(new URL('/contact/',base).href,{form:submitted});
        assert.match(await replay.text(),/تأیید امنیتی معتبر نیست/);
        results.checks.push('browser-generated PoW accepted by Django; replay rejected');

      }
      await context.close();
    }
    assert.deepEqual(results.errors,[]);
    fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify(results,null,2));
    console.log(JSON.stringify(results,null,2));
  } finally { await browser.close(); }
})().catch(e=>{console.error(e.stack);process.exitCode=1});
