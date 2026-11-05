const { chromium } = require('playwright'); const fs = require('fs');
const V = JSON.parse(fs.readFileSync('/tmp/rs_reg/ux_vals.json')); const H = 'http://platformadmins.rastisi.localhost:8033';
const res = []; const ok = (n, c, x = '') => { res.push({ name: n, pass: !!c, extra: x }); console.log((c ? 'PASS ' : 'FAIL ') + n + (x ? ' — ' + x : '')); };
(async () => {
  const b = await chromium.launch();
  const mk = async (w) => { const c = await b.newContext({ viewport: { width: w, height: 900 }, locale: 'fa-IR' }); await c.addCookies([{ name: 'sessionid', value: V.session, domain: 'platformadmins.rastisi.localhost', path: '/' }]); const p = await c.newPage(); p.errs = []; p.on('pageerror', e => p.errs.push(String(e))); p.on('console', m => { if (m.type() === 'error' && !/404/.test(m.text())) p.errs.push(m.text()); }); return p; };
  let p = await mk(1440);
  // nav + shell on every finance page
  for (const [path, label] of [['/payments/gateways/', 'درگاه‌هایِ پرداختِ پلتفرم'], ['/payments/transactions/', 'تراکنش‌هایِ پلتفرم'], ['/payments/reconciliation/', 'تطبیقِ پرداخت‌ها'], ['/payments/card-claims/', 'ادعایِ پرداختِ دستی'], ['/payments/sms-purchases/', 'خریدِ بسته‌یِ پیامک'], [`/payments/card-claims/${V.vals.claim_id}/`, 'ادعایِ پرداختِ دستی']]) {
    await p.goto(H + path);
    const r = await p.evaluate(() => ({ aside: document.querySelectorAll('aside').length, active: (document.querySelector('.pa-nav-link.active') || {}).textContent, open: !!document.querySelector('details[data-group=finance][open]'), h1: document.querySelectorAll('h1').length }));
    ok(`finance page ${path}: one sidebar, finance group open, "${label}" active, one h1`, r.aside === 1 && r.open && (r.active || '').includes(label.slice(0, 8)) && r.h1 === 1, JSON.stringify(r));
  }
  // gateways: masked secrets, shared form pieces
  await p.goto(H + '/payments/gateways/');
  const g = await p.evaluate(() => ({ pw: [...document.querySelectorAll('input[type=password]')].every(i => i.value === '' && i.autocomplete === 'new-password'), pwCount: document.querySelectorAll('input[type=password]').length, fieldsets: document.querySelectorAll('.pa-fieldset').length, formbars: document.querySelectorAll('.pa-formbar').length, spinners: [...document.querySelectorAll('input[type=number]')].filter(i => getComputedStyle(i).appearance !== 'textfield').length, nums: document.querySelectorAll('input[type=number]').length }));
  ok('gateways: every secret input empty + new-password; shared fieldsets/formbars; numeric inputs without spinners', g.pw && g.fieldsets > 3 && g.formbars > 1 && g.spinners === 0, JSON.stringify(g));
  // claim detail approve/reject UX
  await p.goto(H + `/payments/card-claims/${V.vals.claim_id}/`);
  const hasApprove = await p.locator('input[name=bank_reference]').count();
  ok('claim detail: approve form present for a different reviewer (conflict-of-interest guard handled server-side)', hasApprove === 1 || (await p.locator('text=تضادِ منافع').count()) === 1);
  if (hasApprove) {
    await p.fill('#cl-bank', 'BANK-QA-123456'); await p.fill('#cl-amount', '1490000');
    await p.click('button:has-text("تأییدِ مالی و اعمال")'); 
    ok('claim approve asks for confirmation (alertdialog) before any POST', await p.locator('.pa-modalbox[role=alertdialog]').isVisible());
    await p.click('.pa-modalbox >> text=انصراف'); await p.waitForTimeout(150);
    const before = p.url(); await p.waitForTimeout(300);
    ok('cancelling the confirmation sends nothing (dialog closed, same URL, no navigation)', await p.locator('.pa-modalbox').count() === 0 && p.url() === before);
    await p.click('button:has-text("رد (مالک")'); ok('reject without a reason is blocked by inline validation', await p.locator('#cl-reason[aria-invalid=true]').count() === 1 || await p.locator('.pa-field.has-error').count() >= 1);
  }
  // sms purchases confirm
  await p.goto(H + '/payments/sms-purchases/');
  await p.locator('form[action*="/cancel/"] button').first().click();
  ok('sms purchase cancel asks for confirmation', await p.locator('.pa-modalbox[role=alertdialog]').isVisible());
  await p.click('.pa-modalbox >> text=انصراف');
  // invoice refund
  await p.goto(H + `/payments/invoice/${V.vals.invoice_id}/`);
  ok('invoice detail: refund card uses shared form (labels, no inline style)', await p.locator('#rf-amount').count() === 1 && await p.locator('[style]').count() === 0);
  // reconciliation verify button is a POST form with CSRF
  await p.goto(H + '/payments/reconciliation/');
  ok('reconciliation: verify-now actions are POST forms with csrf', await p.locator('form[method=post] input[name=csrfmiddlewaretoken]').count() >= 1);
  // inbox review
  await p.goto(H + '/inbox/');
  const ib = await p.evaluate(() => { const b = document.querySelector('.nt-btn'); const cs = getComputedStyle(b); const prim = getComputedStyle(document.querySelector('.nt-btn--primary')); return { h: Math.round(b.getBoundingClientRect().height), primary: prim.backgroundColor, headingRole: document.querySelector('.nt-head h2').getAttribute('aria-level') }; });
  ok('inbox: buttons 38px, brand-green primary (not the old purple fallback), heading exposed as level 1', ib.h === 38 && ib.primary === 'rgb(15, 107, 82)' && ib.headingRole === '1', JSON.stringify(ib));
  ok('no JS errors (finance flow)', p.errs.length === 0, p.errs.join('|'));
  // mobile finance
  p = await mk(390); await p.goto(H + '/payments/gateways/');
  ok('mobile: gateways page has no horizontal overflow', await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth) === 0);
  fs.writeFileSync('/tmp/rs_reg/ux_behavior_finance.json', JSON.stringify(res, null, 1));
  console.log(res.filter(r => !r.pass).length ? 'SOME FAILED' : 'ALL PASSED'); await b.close();
})();
