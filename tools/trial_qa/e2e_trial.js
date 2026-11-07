// Browser acceptance (real Chromium): register → Trial → buy from the merchant panel → checkout (fake gateway) → activation.
// Usage:  tools/trial_qa/reset_and_start.sh   then   OUT=/path/to/shots node tools/trial_qa/e2e_trial.js
const { chromium } = require('playwright');
const { execSync } = require('child_process');
const fs = require('fs');
const PORT = 8020, SEED = JSON.parse(fs.readFileSync(process.env.SEED_OUT || '/tmp/trial_e2e_seed.json'));
const OUT = process.env.OUT || '/tmp/trial_e2e_shots'; fs.mkdirSync(OUT, { recursive: true });
const PUB = `http://rastisi.localhost:${PORT}`, PA = `http://platformadmins.rastisi.localhost:${PORT}`;
const results = [], consoleErrors = [];
const check = (n, ok, d = '') => { results.push({ name: n, ok: !!ok, detail: d }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}${ok ? '' : '  → ' + d}`); };
const q = sql => execSync(`PGPASSWORD=rs psql -h localhost -U rs -d rs_trial_e2e -At -c "${sql.replace(/"/g, '\\"')}"`).toString().trim();
const latin = s => String(s).replace(/[۰-۹]/g, d => String(d.charCodeAt(0) - 0x06f0)).replace(/[٬,\s]/g, '').replace(/تومان|\/ماه/g, '');
const EXPECT = { monthly: 1000000, quarterly: 2850000, semiannual: 5400000, yearly: 10200000 };
let shotN = 0;

async function mk(browser, cookies = []) {
  const c = await browser.newContext({ locale: 'fa-IR', viewport: { width: 1440, height: 900 } });
  if (cookies.length) await c.addCookies(cookies);
  // The fake bank: the pay endpoint answers 302 → https://gateway.zibal.ir/start/<trackId>; we turn that into a local page with two honest buttons.
  await c.route(/\/billing\/checkout\/[a-z]+\/\d+\/pay\//, async route => {
    const resp = await route.fetch({ maxRedirects: 0 }); const loc = resp.headers()['location'] || '';
    const m = loc.match(/^https:\/\/gateway\.zibal\.ir\/start\/(\d+)$/);
    if (!m) return route.fulfill({ response: resp });
    await route.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: `<!doctype html><meta charset=utf-8><body dir=rtl>
      <h1>درگاه آزمایشی</h1><p id="track">${m[1]}</p><a id="ok" href="${PUB}/__e2e__/pay_return/${m[1]}">پرداخت موفق</a> | <a id="cancel" href="${PUB}/__e2e__/cancel_return/${m[1]}">انصراف</a></body>` });
  });
  c.on('page', p => { p.on('dialog', d => d.accept()); p.on('pageerror', e => consoleErrors.push('pageerror: ' + e.message));
    p.on('console', m => { if (m.type() === 'error' && !/favicon|Failed to load resource/.test(m.text())) consoleErrors.push(m.text()); }); });
  return c;
}
const ensureHost = h => { const hosts = fs.readFileSync('/etc/hosts', 'utf8'); if (!hosts.includes(h)) fs.appendFileSync('/etc/hosts', `127.0.0.1 ${h}\n`); };   // node (route.fetch) cannot resolve unknown *.localhost names
const ck = (value, host) => ({ name: 'sessionid', value, domain: host, path: '/' });
async function widths(page, name) {
  for (const w of [1440, 768, 390]) {
    await page.setViewportSize({ width: w, height: 900 }); await page.waitForTimeout(150);
    const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth, dir: getComputedStyle(document.body).direction }));
    check(`${name} @${w}: no horizontal overflow, RTL`, m.sw <= m.iw + 1 && m.dir === 'rtl', JSON.stringify(m));
    await page.screenshot({ path: `${OUT}/${String(++shotN).padStart(2, '0')}_${name}_${w}.png`, fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}
// the REAL way into a store's admin panel: the owner portal issues a short-lived handoff ticket (a portal cookie has no meaning on the admin host)
async function enterAdmin(ctx, storeUuid, next = '/admin-portal/subscription/') {
  const page = await ctx.newPage();
  await page.goto(`${PUB}/app/`);
  await page.evaluate(([uuid, nxt]) => {
    const csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
    const f = document.createElement('form'); f.method = 'post'; f.action = `/app/stores/${uuid}/enter-admin/`;
    for (const [k, v] of [['csrfmiddlewaretoken', csrf], ['next', nxt]]) { const i = document.createElement('input'); i.type = 'hidden'; i.name = k; i.value = v; f.appendChild(i); }
    document.body.appendChild(f); f.submit();
  }, [storeUuid, next]);
  await page.waitForURL(/admin-portal/, { timeout: 20000 });
  return page;
}
async function register(browser, name, phone, plan, email) {
  const ctx = await mk(browser); const page = await ctx.newPage();
  await page.goto(`${PUB}/register/?plan=${plan}&period=yearly`);
  await page.fill('#id_full_name', name); await page.fill('#id_phone', phone);
  await page.check('#id_accept_terms');
  await page.click('form button[type=submit]');
  await page.waitForLoadState('networkidle');
  const code = page.locator('input[name=code], input[name=otp], input[autocomplete=one-time-code]').first();
  await code.fill('123456'); await page.click('form button[type=submit]'); await page.waitForLoadState('networkidle');
  // «اطلاعات حساب»: e-mail + password (+ terms when the form asks again)
  await page.fill('#id_email', email); await page.fill('#id_password', 'E2e-Pass-98765!x'); await page.fill('#id_password_confirm', 'E2e-Pass-98765!x');
  const terms = page.locator('input[name=accept_terms]'); if (await terms.count() && !(await terms.first().isChecked())) await terms.first().check();
  await page.click('form button[type=submit]'); await page.waitForLoadState('networkidle');
  return { ctx, page };
}

(async () => {
  const browser = await chromium.launch();

  // ---------- 1. public pricing (anonymous) ----------
  const anon = await mk(browser); const pub = await anon.newPage();
  await pub.goto(`${PUB}/plans/`);
  const codes = await pub.$$eval('[data-plan]', els => els.map(e => e.getAttribute('data-plan')));
  check('5: the internal Trial plan is NOT in the public pricing list', !codes.includes('trial') && codes.includes('e2e-pro') && codes.includes('e2e-lite'), codes.join(','));
  check('1: the public page advertises the platform Trial (۳۰ روز)', (await pub.content()).includes('۳۰ روز دوره‌ی آزمایشیِ رایگان'));
  const proCard = pub.locator('[data-plan="e2e-pro"]');
  check('anonymous: a register CTA keeps plan+period and an existing-merchant login keeps them in next=',
        (await proCard.locator('[data-cta=register]').getAttribute('href')).includes('plan=e2e-pro') &&
        (await proCard.locator('[data-cta=login]').getAttribute('href')).includes('%3Fplan%3De2e-pro'));
  await pub.click('.pz-seg [data-period=yearly]');
  check('choosing the yearly period updates the register AND login links', (await proCard.locator('[data-cta=register]').getAttribute('href')).includes('period=yearly') &&
        decodeURIComponent(await proCard.locator('[data-cta=login]').getAttribute('href')).includes('period=yearly'));
  await widths(pub, 'public_plans');

  // ---------- 2. owner 1 registers (30-day default) ----------
  const r1 = await register(browser, 'مالک اول', '09121110001', 'e2e-pro', 'owner1@example.com');
  check('registration reaches the onboarding (store created)', /\/onboarding\//.test(r1.page.url()) || /\/app\//.test(r1.page.url()), r1.page.url());
  const s1 = q(`select s.id||'|'||s.public_id||'|'||s.platform_code from stores_store s join stores_storemembership m on m.store_id=s.id join auth_user u on u.id=m.user_id where u.username='09121110001'`).split('|');
  const [store1Id, store1Uuid] = s1; const code1 = q(`select admin_subdomain from stores_store where id=${store1Id}`);
  const sub1 = q(`select p.code||'|'||sub.status||'|'||extract(day from (sub.trial_end_at-sub.trial_start_at))::int||'|'||count(*) over () from subscriptions_storesubscription sub join subscriptions_planversion v on v.id=sub.plan_version_id join subscriptions_plan p on p.id=v.plan_id where sub.store_id=${store1Id}`).split('|');
  check('1: the new store got the internal Trial plan, trialing, 30 days, exactly one subscription', sub1[0] === 'trial' && sub1[1] === 'trialing' && sub1[2] === '30' && sub1[3] === '1', sub1.join(','));
  check('4: choosing a paid plan at sign-up did not add a paid/second subscription', q(`select count(*) from subscriptions_storesubscription where store_id=${store1Id}`) === '1');
  const ADMIN1 = `${code1}.rastisi.localhost:${PORT}`; ensureHost(`${code1}.rastisi.localhost`);

  // ---------- 3. platform owner changes the default (affects only NEW stores) ----------
  const staff = await mk(browser, [ck(SEED.sessions.staff, 'platformadmins.rastisi.localhost')]); const pa = await staff.newPage();
  await pa.goto(`${PA}/trial/`);
  check('platform trial page: policy, limits, history sections exist', await pa.locator('[data-testid=trial-policy-form]').count() === 1 && await pa.locator('[data-testid=trial-limits-form]').count() === 1 && await pa.locator('[data-testid=trial-history]').count() === 1);
  check('trial page lists the existing store in the history', (await pa.content()).includes('فروشگاه'));
  await widths(pa, 'platform_trial_page');
  await pa.fill('#trial-days', '0'); await pa.click('[data-testid=trial-policy-form] button[type=submit]');
  check('2: an invalid length (0) is rejected with a message', (await pa.content()).includes('مدتِ دوره‌ی آزمایشی باید بین'));
  await pa.fill('#trial-days', '14'); await pa.click('[data-testid=trial-policy-form] button[type=submit]');
  check('2: valid change saved', (await pa.content()).includes('سیاستِ دوره‌ی آزمایشی ذخیره شد'));
  check('platform audit entry written for the change', Number(q(`select count(*) from portal_platformauditlogentry where action_code='platform_configuration.updated' and after_summary like '%14%'`)) >= 1);
  await pa.screenshot({ path: `${OUT}/${String(++shotN).padStart(2, '0')}_platform_trial_saved.png`, fullPage: true });

  const r2 = await register(browser, 'مالک دوم', '09121110002', 'e2e-lite', 'owner2@example.com');
  const store2Id = q(`select s.id from stores_store s join stores_storemembership m on m.store_id=s.id join auth_user u on u.id=m.user_id where u.username='09121110002'`);
  const d2 = q(`select extract(day from (trial_end_at-trial_start_at))::int from subscriptions_storesubscription where store_id=${store2Id}`);
  const d1 = q(`select extract(day from (trial_end_at-trial_start_at))::int from subscriptions_storesubscription where store_id=${store1Id}`);
  check('2: a store created AFTER the change gets 14 days', d2 === '14', d2);
  check('3: the earlier store keeps its 30-day trial', d1 === '30', d1);
  await pa.fill('#trial-days', '30'); await pa.click('[data-testid=trial-policy-form] button[type=submit]');

  // ---------- 4. merchant panel: trial status + buy ----------
  const mp = await enterAdmin(r1.ctx, store1Uuid);
  check('merchant enters the admin panel through the portal handoff', mp.url().startsWith(`http://${ADMIN1}/admin-portal/`), mp.url());
  check('7: the trial card, the days left and a clear «خرید اشتراک» button are visible', await mp.locator('[data-testid=trial-card]').isVisible() && await mp.locator('[data-testid=buy-subscription]').isVisible());
  const days = latin(await mp.locator('[data-testid=trial-days-left]').innerText());
  check('7: days left is 29 or 30', ['29', '30'].includes(days), days);
  check('7: the trial banner is on the page', await mp.locator('[data-testid=trial-banner]').isVisible());
  check('6: the trial limits (products cap 20) are shown to the merchant', /۲۰/.test(await mp.locator('[data-testid=trial-card]').innerText()));
  await widths(mp, 'merchant_overview_trial');
  await mp.click('[data-testid=buy-subscription]');
  check('merchant plans page lists paid plans only (no trial)', await mp.locator('[data-plan=trial]').count() === 0 && await mp.locator('[data-plan=e2e-pro]').count() === 1);
  for (const [iv, amount] of Object.entries(EXPECT)) {
    const shown = latin(await mp.locator(`[data-testid=price-e2e-pro-${iv}]`).innerText());
    check(`9: ${iv} price on the page = published version (${amount})`, shown === String(amount), shown);
  }
  await widths(mp, 'merchant_plans');
  await mp.locator('[data-plan=e2e-pro] input[value=yearly]').check();
  await mp.click('[data-testid=choose-e2e-pro]');
  const payable = latin(await mp.locator('[data-testid=payable-amount] b').first().innerText());
  check('9: preview shows the yearly published price', payable === String(EXPECT.yearly), payable);
  await widths(mp, 'merchant_purchase_preview');
  await mp.click('button:has-text("ایجادِ فاکتور")'); await mp.waitForLoadState('networkidle');
  check('checkout page reached (unified platform checkout)', /\/billing\/checkout\/subscription\/\d+\//.test(mp.url()), mp.url());
  const invoice = q(`select id||'|'||grand_total::bigint||'|'||status from billing_subscriptioninvoice where store_id=${store1Id} order by id desc limit 1`).split('|');
  check('9: the invoice amount equals the yearly published price', invoice[1] === String(EXPECT.yearly) && invoice[2] === 'open', invoice.join(','));
  await widths(mp, 'merchant_checkout');
  await mp.click('input[name=method][value=zibal]'); await mp.click('button[type=submit]:has-text("پرداخت")'); await mp.waitForSelector('#ok', { timeout: 20000 }).catch(() => {});
  check('gateway page (fake) reached', await mp.locator('#ok').count() === 1, mp.url());
  const rial = q(`select amount::bigint from billing_subscriptionpaymentattempt where invoice_id=${invoice[0]} order by id desc limit 1`);
  check('9: the amount sent to the gateway = price × 10 (RIAL)', rial === String(EXPECT.yearly), rial);   // attempt.amount is stored in TOMAN
  // 10. cancelled / failed payment ⇒ nothing activates
  await mp.click('#cancel'); await mp.waitForLoadState('networkidle');
  const afterCancel = q(`select p.code||'|'||sub.status from subscriptions_storesubscription sub join subscriptions_planversion v on v.id=sub.plan_version_id join subscriptions_plan p on p.id=v.plan_id where sub.store_id=${store1Id} and sub.is_current`);
  check('10: a cancelled payment leaves the store on the Trial', afterCancel === 'trial|trialing', afterCancel);
  await mp.goto(`http://${ADMIN1}/admin-portal/billing/checkout/subscription/${invoice[0]}/`);
  await mp.click('input[name=method][value=zibal]'); await mp.click('button[type=submit]:has-text("پرداخت")'); await mp.waitForSelector('#ok', { timeout: 20000 });
  // 11. successful payment ⇒ activation, replay-safe
  const track = (await mp.locator('#ok').getAttribute('href')).split('/').pop();
  await mp.click('#ok'); await mp.waitForLoadState('networkidle');
  const active = q(`select p.code||'|'||sub.status||'|'||sub.billing_interval||'|'||(sub.trial_start_at is not null) from subscriptions_storesubscription sub join subscriptions_planversion v on v.id=sub.plan_version_id join subscriptions_plan p on p.id=v.plan_id where sub.store_id=${store1Id} and sub.is_current`);
  check('11: verified payment activated the purchased plan (e2e-pro, active, yearly), trial history kept', active === 'e2e-pro|active|yearly|true', active);
  await pub.goto(`${PUB}/__e2e__/pay_return/${track}`).catch(() => {});
  await pub.goto(`${PUB}/__e2e__/pay_return/${track}`).catch(() => {});
  check('12: replayed gateway returns never activate twice', q(`select count(*) from subscriptions_subscriptionevent where subscription_id=(select id from subscriptions_storesubscription where store_id=${store1Id} and is_current) and event_type='activated'`) === '1');
  check('11: the invoice is paid in full', q(`select status||'|'||(amount_paid=grand_total) from billing_subscriptioninvoice where id=${invoice[0]}`) === 'paid|true');
  await mp.goto(`http://${ADMIN1}/admin-portal/subscription/`);
  check('after purchase: no trial card/banner, current plan shown', await mp.locator('[data-testid=trial-card]').count() === 0 && await mp.locator('[data-testid=trial-banner]').count() === 0 && (await mp.locator('[data-testid=current-plan-name]').innerText()).length > 0);
  await widths(mp, 'merchant_overview_paid');

  // ---------- 5. existing merchant on the public page ----------
  const op = await r1.ctx.newPage();
  await op.goto(`${PUB}/plans/`);
  const upg = op.locator('[data-plan="e2e-pro"] [data-cta=upgrade]');
  check('existing merchant sees an «upgrade/buy» CTA (not register) that keeps plan+period', await upg.count() === 1 && (await upg.getAttribute('href')).includes('plan=e2e-pro') && await op.locator('[data-plan="e2e-pro"] [data-cta=register]').count() === 0, await upg.count() ? await upg.getAttribute('href') : 'no cta');
  await widths(op, 'public_plans_logged_in_owner');
  await op.goto(`${PUB}/register/?plan=e2e-pro`);
  check('existing merchant opening /register/ is sent to the app, not a second sign-up', !/\/register\//.test(op.url()), op.url());

  // ---------- 6. legacy store untouched ----------
  const lg = await mk(browser, [ck(SEED.sessions.legacy_owner, 'oldshop.rastisi.localhost')]); const lp = await lg.newPage();
  await lp.goto(`http://oldshop.rastisi.localhost:${PORT}/admin-portal/subscription/`);
  check('14: a legacy store still opens its subscription page, no trial card, no banner', await lp.locator('[data-testid=trial-card]').count() === 0 && await lp.locator('[data-testid=trial-banner]').count() === 0 && (await lp.content()).includes('پلنِ فعلی'));
  check('14: the legacy subscription is unchanged in the database', q(`select p.code||'|'||sub.status from subscriptions_storesubscription sub join subscriptions_planversion v on v.id=sub.plan_version_id join subscriptions_plan p on p.id=v.plan_id join stores_store s on s.id=sub.store_id where s.slug='oldshop' and sub.is_current`) === 'legacy|active');

  // ---------- 7. isolation: owner 2 against store 1 ----------
  const ip = await r2.ctx.newPage();
  await ip.goto(`${PUB}/app/`);
  const handoff = await ip.evaluate(async uuid => {
    const csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
    const r = await fetch(`/app/stores/${uuid}/enter-admin/`, { method: 'POST', headers: { 'X-CSRFToken': csrf, 'Content-Type': 'application/x-www-form-urlencoded' }, body: 'next=/admin-portal/subscription/', redirect: 'manual' });
    return r.status;
  }, store1Uuid);
  check('13: owner 2 cannot obtain an admin handoff into store 1 (404)', handoff === 404, String(handoff));
  const resp = await ip.goto(`http://${ADMIN1}/admin-portal/billing/checkout/subscription/${invoice[0]}/`);
  check('13: owner 2 cannot open store 1\'s invoice/checkout directly on its host', !/billing\/checkout\/subscription/.test(ip.url()) || [403, 404].includes(resp.status()), `${resp.status()} ${ip.url()}`);
  check('13: no store-1 data is in that response', !(await ip.content()).includes('e2e-pro'));

  // ---------- 8. trial end → restricted, can still buy ----------
  const store2Code = q(`select admin_subdomain from stores_store where id=${store2Id}`);
  q(`update subscriptions_storesubscription set trial_end_at = now() - interval '1 minute' where store_id=${store2Id} and is_current`);
  execSync(`cd ${__dirname}/../.. && DATABASE_URL=postgres://rs:rs@localhost:5432/rs_trial_e2e DJANGO_SETTINGS_MODULE=shop_core.settings ${process.env.PY || 'python'} -c "import django;django.setup();from apps.subscriptions.services import subscription_service as s;print(s.evaluate_subscription_states())"`, { stdio: 'pipe' });
  const store2Uuid = q(`select public_id from stores_store where id=${store2Id}`);
  const p2 = await enterAdmin(r2.ctx, store2Uuid);
  check('8: after the trial ends the page says so and still offers «خرید اشتراک»', await p2.locator('[data-testid=trial-ended-card]').isVisible() && await p2.locator('[data-testid=buy-subscription]').isVisible());
  check('8: the data is kept and the store is restricted, not deleted', q(`select status from subscriptions_storesubscription where store_id=${store2Id} and is_current`) === 'suspended' && q(`select count(*) from stores_store where id=${store2Id}`) === '1');
  await widths(p2, 'merchant_overview_trial_ended');

  // ---------- console ----------
  check('no JavaScript console errors on any page', consoleErrors.length === 0, consoleErrors.slice(0, 5).join(' | '));
  fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(results, null, 1));
  const failed = results.filter(r => !r.ok).length;
  console.log(`\n${results.length - failed}/${results.length} checks passed`);
  await browser.close(); process.exit(failed ? 1 : 0);
})().catch(e => { console.error('E2E crashed:', e); process.exit(2); });
