const { chromium } = require('playwright'); const { execSync } = require('child_process');
const SP = '/tmp/claude-0/-home-user-Rastisi6-14040616/9464551a-7c83-50df-b657-f00f736fb713/scratchpad'; const out = `${SP}/nshots`;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const HOST = 'rastisi-fashion-test.rastisi.localhost:8014', PHOST = 'platformadmins.rastisi.localhost:8014';
const env = { ...process.env, PYTHONPATH: `${SP}/qa:/home/user/Rastisi6-14040616`, DJANGO_SETTINGS_MODULE: 'qa_settings' };
const sess = u => execSync(`/home/user/ADMIN_QA_DATA_20261031/venv/bin/python /home/user/ADMIN_QA_DATA_20261031/mksession.py ${u}`, { cwd: '/home/user/Rastisi6-14040616', env }).toString().trim();
const widths = (process.argv[2] || '1440').split(',').map(Number);
(async () => {
  const sid = sess('09120000002'), psid = sess('qa-platform-admin');
  const b = await chromium.launch(); const res = {};
  for (const w of widths) {
    const ctx = await b.newContext({ viewport: { width: w, height: 900 }, locale: 'fa-IR' });
    await ctx.addCookies([{ name: 'sessionid', value: sid, domain: 'rastisi-fashion-test.rastisi.localhost', path: '/' }]);
    const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(String(e)));
    await p.goto(`http://${HOST}/admin-portal/`, { waitUntil: 'networkidle' }); await sleep(900);
    await p.screenshot({ path: `${out}/bell_${w}.png` });
    const badge = await p.locator('[data-nt-badge]').textContent();
    await p.click('[data-nt-toggle]'); await sleep(700);
    await p.screenshot({ path: `${out}/dropdown_${w}.png` });
    const items = await p.locator('.nt-item').count(); const focusInPanel = await p.evaluate(() => !!document.activeElement.closest('#nt-panel'));
    await p.keyboard.press('Escape'); await sleep(200);
    const closedFocus = await p.evaluate(() => document.activeElement.hasAttribute('data-nt-toggle'));
    // page / inbox
    await p.goto(`http://${HOST}/admin-portal/inbox/`, { waitUntil: 'networkidle' }); await sleep(500);
    await p.screenshot({ path: `${out}/inbox_${w}.png`, fullPage: true });
    const ov = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    await p.goto(`http://${HOST}/admin-portal/inbox/?q=zzzz`, { waitUntil: 'networkidle' }); await p.screenshot({ path: `${out}/inbox_empty_${w}.png` });
    await p.goto(`http://${HOST}/admin-portal/inbox/preferences/`, { waitUntil: 'networkidle' }); await sleep(700);
    await p.screenshot({ path: `${out}/prefs_${w}.png`, fullPage: true });
    const ov2 = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    const pushStatus = await p.locator('[data-testid=push-status]').textContent();
    res[w] = { badge, items, focusInPanel, closedFocus, ovInbox: ov, ovPrefs: ov2, pushStatus: pushStatus.trim().slice(0, 90), errs: errs.length };
    await ctx.close();
  }
  console.log(JSON.stringify(res, null, 1));
  await b.close();
})();
