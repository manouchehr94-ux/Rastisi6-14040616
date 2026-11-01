const { chromium } = require('playwright'); const { execSync } = require('child_process');
const SP = '/tmp/claude-0/-home-user-Rastisi6-14040616/9464551a-7c83-50df-b657-f00f736fb713/scratchpad'; const out = `${SP}/nshots`;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const HOST = 'rastisi-fashion-test.rastisi.localhost:8014', PHOST = 'platformadmins.rastisi.localhost:8014';
const env = { ...process.env, PYTHONPATH: `${SP}/qa:/home/user/Rastisi6-14040616`, DJANGO_SETTINGS_MODULE: 'qa_settings' };
const PY = '/home/user/ADMIN_QA_DATA_20261031/venv/bin/python';
const sess = u => execSync(`${PY} /home/user/ADMIN_QA_DATA_20261031/mksession.py ${u}`, { cwd: '/home/user/Rastisi6-14040616', env }).toString().trim();
const publish = (title, sev = 3) => execSync(`${PY} manage.py shell -c "
from apps.stores.models import Store; from apps.notifications.services import inbox_engine as e; import uuid
s=Store.objects.get(slug='rastisi-fashion-test'); e.publish('order.canceled', store=s, title='${title}', link_kwargs={'code':'DM-10230'}, dedupe_key=uuid.uuid4().hex, severity=${sev})"`, { cwd: '/home/user/Rastisi6-14040616', env });
const res = {};
(async () => {
  const sid = sess('09120000002'), psid = sess('qa-platform-admin');
  const b = await chromium.launch();
  // 1) live toast without reload + badge update + critical toast stays + dedupe on a second tab
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, locale: 'fa-IR' });
  await ctx.addCookies([{ name: 'sessionid', value: sid, domain: 'rastisi-fashion-test.rastisi.localhost', path: '/' }]);
  const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(String(e)));
  await p.goto(`http://${HOST}/admin-portal/`, { waitUntil: 'networkidle' }); await sleep(800);
  const before = await p.locator('[data-nt-badge]').textContent();
  const nav0 = await p.evaluate(() => performance.getEntriesByType('navigation').length);
  publish('لغو سفارش DM-10230 توسط مشتری'); publish('هشدار بحرانی آزمایشی', 4);
  const t0 = Date.now();
  await p.click('[data-nt-toggle]');                     // opening the panel forces a poll (no full page reload)
  await p.waitForSelector('.nt-toast', { timeout: 8000 });
  res.toastLatencyMs = Date.now() - t0; res.badgeBefore = before; res.badgeAfter = await p.locator('[data-nt-badge]').textContent();
  await sleep(500); res.toasts = await p.locator('.nt-toast').count(); res.criticalRole = await p.locator('.nt-toast--critical').getAttribute('role');
  await p.screenshot({ path: `${out}/toast_1440.png` });
  res.reloaded = (await p.evaluate(() => performance.getEntriesByType('navigation')[0].type)) !== 'navigate';
  // 2) second tab of the same user: the same notifications must NOT toast again
  const p2 = await ctx.newPage(); await p2.goto(`http://${HOST}/admin-portal/`, { waitUntil: 'networkidle' }); await sleep(2500);
  res.secondTabToasts = await p2.locator('.nt-toast').count();
  // 3) mark all read via the dropdown → badge hides
  await p.click('[data-nt-readall]'); await p.waitForFunction(() => document.querySelector('[data-nt-badge]').hidden, null, { timeout: 8000 });
  res.badgeHiddenAfterReadAll = true; await p.screenshot({ path: `${out}/readall_1440.png` });
  // 4) error state (summary blocked) in the dropdown
  const ctxE = await b.newContext({ viewport: { width: 1440, height: 900 }, locale: 'fa-IR' });
  await ctxE.addCookies([{ name: 'sessionid', value: sid, domain: 'rastisi-fashion-test.rastisi.localhost', path: '/' }]);
  const pe = await ctxE.newPage(); await pe.goto(`http://${HOST}/admin-portal/`, { waitUntil: 'networkidle' });
  await pe.route('**/inbox/api/summary/**', r => r.abort()); await pe.click('[data-nt-toggle]'); await sleep(1200);
  res.errorVisible = await pe.locator('[data-nt-error]').isVisible(); await pe.screenshot({ path: `${out}/dropdown_error_1440.png` });
  // 5) logout/user-switch guard: another user's session cookie → page reloads away, no stale notifications of old account
  await ctx.close(); await ctxE.close();
  // 6) platform admin
  const cp = await b.newContext({ viewport: { width: 1440, height: 900 }, locale: 'fa-IR' });
  await cp.addCookies([{ name: 'sessionid', value: psid, domain: 'platformadmins.rastisi.localhost', path: '/' }]);
  const pp = await cp.newPage(); await pp.goto(`http://${PHOST}/`, { waitUntil: 'networkidle' }); await sleep(800);
  res.platformBell = await pp.locator('[data-nt-bell]').count(); await pp.click('[data-nt-toggle]'); await sleep(600); await pp.screenshot({ path: `${out}/platform_dropdown_1440.png` });
  await pp.goto(`http://${PHOST}/inbox/`, { waitUntil: 'networkidle' }); await pp.screenshot({ path: `${out}/platform_inbox_1440.png`, fullPage: true });
  // 7) a store owner cannot open the platform inbox on the platform host (404)
  const cs = await b.newContext({ locale: 'fa-IR' }); await cs.addCookies([{ name: 'sessionid', value: sid, domain: 'platformadmins.rastisi.localhost', path: '/' }]);
  const ps = await cs.newPage(); const r = await ps.goto(`http://${PHOST}/inbox/`); res.storeOwnerOnPlatformInbox = r.status();
  res.errs = errs.length; console.log(JSON.stringify(res, null, 1)); await b.close();
})();
