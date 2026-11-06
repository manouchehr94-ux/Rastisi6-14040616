const { chromium } = require('playwright'); const fs = require('fs');
const V = JSON.parse(fs.readFileSync('/tmp/rs_reg/ux_vals.json')); const H = 'http://platformadmins.rastisi.localhost:8032';
const res = []; const ok = (name, cond, extra = '') => { res.push({ name, pass: !!cond, extra }); console.log((cond ? 'PASS ' : 'FAIL ') + name + (extra ? ' — ' + extra : '')); };
(async () => {
  const b = await chromium.launch();
  const mk = async (w) => { const c = await b.newContext({ viewport: { width: w, height: 900 }, locale: 'fa-IR' }); await c.addCookies([{ name: 'sessionid', value: V.session, domain: 'platformadmins.rastisi.localhost', path: '/' }]); const p = await c.newPage(); p.errs = []; p.on('pageerror', e => p.errs.push(String(e))); p.on('console', m => { if (m.type() === 'error' && !/404/.test(m.text())) p.errs.push(m.text()); }); return p; };
  // 1 mobile drawer
  let p = await mk(390); await p.goto(H + '/plans/');
  const hidden0 = await p.evaluate(() => { const r = document.querySelector('[data-pa-sidebar]').getBoundingClientRect(); return r.left >= window.innerWidth - 2 || r.right <= 2; });
  ok('mobile: sidebar off-canvas initially', hidden0);
  await p.click('[data-pa-nav-open]'); await p.waitForTimeout(350);
  const open1 = await p.evaluate(() => { const s = document.querySelector('[data-pa-sidebar]'); const r = s.getBoundingClientRect(); return { onscreen: r.left >= -1 && r.right <= window.innerWidth + 1, cls: s.classList.contains('open'), backdrop: !document.querySelector('[data-pa-backdrop]').hidden, expanded: document.querySelector('[data-pa-nav-open]').getAttribute('aria-expanded'), focusInside: s.contains(document.activeElement) }; });
  ok('mobile: hamburger opens drawer (onscreen, backdrop, aria-expanded, focus moved in)', open1.onscreen && open1.cls && open1.backdrop && open1.expanded === 'true' && open1.focusInside, JSON.stringify(open1));
  await p.keyboard.press('Escape'); await p.waitForTimeout(350);
  ok('mobile: Esc closes drawer and returns focus to hamburger', await p.evaluate(() => !document.querySelector('[data-pa-sidebar]').classList.contains('open') && document.activeElement === document.querySelector('[data-pa-nav-open]')));
  await p.click('[data-pa-nav-open]'); await p.waitForTimeout(300); await p.click('[data-pa-backdrop]', { position: { x: 10, y: 300 } }); await p.waitForTimeout(300);
  ok('mobile: backdrop click closes drawer', await p.evaluate(() => !document.querySelector('[data-pa-sidebar]').classList.contains('open')));
  await p.click('[data-pa-nav-open]'); await p.waitForTimeout(300);
  await p.click('summary:has-text("پیامک")'); const smsOpen = await p.evaluate(() => document.querySelector('details[data-group=sms]').open);
  ok('nav group expands on tap', smsOpen);
  await p.click('a.pa-nav-link:has-text("بسته‌هایِ پیامک")'); await p.waitForURL('**/sms/packages/'); 
  ok('nav: SMS packages page now reachable from sidebar and highlighted', await p.evaluate(() => document.querySelector('.pa-nav-link.active').textContent.includes('بسته')));
  ok('no JS errors (mobile flow)', p.errs.length === 0, p.errs.join('|'));
  // 2 desktop: single sidebar, confirm dialog on archive, restore
  p = await mk(1440); await p.goto(H + '/plans/');
  ok('desktop: exactly one sidebar and one nav', await p.evaluate(() => document.querySelectorAll('aside').length === 1 && document.querySelectorAll('nav.pa-nav').length === 1));
  ok('desktop: hamburger and close buttons hidden', await p.evaluate(() => getComputedStyle(document.querySelector('[data-pa-nav-open]')).display === 'none' && getComputedStyle(document.querySelector('.pa-nav-close')).display === 'none'));
  const archiveBtn = p.locator('section[data-plan="advanced"] form[action*="archive"] button');
  await archiveBtn.click();
  ok('confirm dialog appears before archive', await p.locator('.pa-modalbox[role=alertdialog]').isVisible());
  await p.click('.pa-modalbox >> text=انصراف'); await p.waitForTimeout(200);
  ok('cancel keeps the plan active (no request sent)', await p.locator('section[data-plan="advanced"] .pa-badge:has-text("بایگانی‌شده")').count() === 0);
  await archiveBtn.click(); await p.click('.pa-modalbox >> text=تأیید'); await p.waitForLoadState('networkidle');
  ok('confirm archives the plan (real POST) and shows success feedback', await p.locator('section[data-plan="advanced"] .pa-badge:has-text("بایگانی‌شده")').count() === 1);
  const toast = await p.locator('.pa-toast').count();
  ok('success message converted to a toast (once)', toast === 1 && await p.locator('.pa-alert[data-pa-message]').count() === 0, 'toasts=' + toast);
  await p.locator('section[data-plan="advanced"] form[action*="archive"] button').click(); await p.waitForLoadState('networkidle');
  ok('restore (unarchive) works without confirmation', await p.locator('section[data-plan="advanced"] .pa-badge:has-text("بایگانی‌شده")').count() === 0);
  // 3 number inputs
  await p.goto(H + `/plans/${V.vals.plan_id}/edit/`);
  const num = await p.evaluate(() => { const i = document.querySelector('input[type=number]'); const cs = getComputedStyle(i); const pse = getComputedStyle(i, '::-webkit-inner-spin-button'); return { n: document.querySelectorAll('input[type=number]').length, appearance: cs.appearance || cs.webkitAppearance, dir: cs.direction, spinDisplay: pse.display, min: i.getAttribute('min'), step: i.getAttribute('step') }; });
  ok('numeric inputs: spinners hidden, ltr digits, native min/step kept', num.appearance === 'textfield' && num.dir === 'ltr' && num.min !== null && num.step !== null, JSON.stringify(num));
  await p.fill('#f-order', '12'); await p.waitForTimeout(100);
  ok('dirty-form indicator appears after an edit', await p.locator('.pa-dirty-note').count() === 1);
  await p.fill('#f-name', ''); await p.click('.pa-formbar button[type=submit]');
  ok('inline validation message shown for an empty required field', await p.locator('.pa-field.has-error .pa-error').count() >= 1 && await p.locator('#f-name[aria-invalid=true]').count() === 1);
  // 4 dialogs (native)
  await p.goto(H + `/stores/${V.vals.store_public_id}/`);
  await p.click('button[data-pa-open=dlg-suspend]'); 
  ok('native dialog opens modally', await p.evaluate(() => document.getElementById('dlg-suspend').open));
  await p.keyboard.press('Escape'); await p.waitForTimeout(150);
  ok('Esc closes the dialog', await p.evaluate(() => !document.getElementById('dlg-suspend').open));
  await p.goto(H + `/stores/${V.vals.store_public_id}/?tab=subscription`); await p.click('button[data-pa-open=dlg-change-plan]');
  ok('change-plan dialog shows a plan-version select (no raw ID field)', await p.locator('#dlg-change-plan select[name=plan_version_id] option').count() > 2);
  // 5 htmx preview
  await p.goto(H + '/notifications/'); const href = await p.getAttribute('#event-catalog tbody tr:first-child a.pa-btn', 'href'); await p.goto(H + href);
  await p.click('button:has-text("پیش‌نمایش")'); await p.waitForTimeout(1200);
  ok('notification preview button now works (htmx loaded)', (await p.locator('#pv-email').innerText()).trim().length > 5);
  // 6 tabs + assignment
  await p.goto(H + '/plans/content/?tab=faq'); ok('pricing content tab shows only its section', await p.locator('text=پرسشِ تازه').count() >= 1 && await p.locator('h3:has-text("ردیف‌هایِ ماتریس (")').count() === 0);
  await p.goto(H + '/plans/assignments/'); ok('assignment matrix renders draft cells', await p.locator('input[name^="en_"]').count() > 5);
  ok('no JS errors (desktop flow)', p.errs.length === 0, p.errs.join('|'));
  fs.writeFileSync('/tmp/rs_reg/ux_behavior.json', JSON.stringify(res, null, 1));
  console.log(res.filter(r => !r.pass).length ? 'SOME FAILED' : 'ALL PASSED'); await b.close();
})();
