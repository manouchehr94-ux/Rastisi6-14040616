const { chromium } = require('playwright'); const { execSync } = require('child_process');
const SP = '/tmp/claude-0/-home-user-Rastisi6-14040616/9464551a-7c83-50df-b657-f00f736fb713/scratchpad'; const out = `${SP}/shots`;
const sleep = ms => new Promise(r => setTimeout(r, ms)); const HOST = 'rastisi-fashion-test.rastisi.localhost:8009';
(async () => {
  const sid = execSync(`/home/user/ADMIN_QA_DATA_20261031/venv/bin/python /home/user/ADMIN_QA_DATA_20261031/mksession.py 09120000002`, {cwd: '/home/user/Rastisi6-14040616'}).toString().trim();
  const b = await chromium.launch(); const res = {};
  for (const w of (process.argv[2] || '1440').split(',').map(Number)) {
    const ctx = await b.newContext({ viewport: { width: w, height: 900 }, locale: 'fa-IR' });
    await ctx.addCookies([{ name: 'sessionid', value: sid, domain: 'rastisi-fashion-test.rastisi.localhost', path: '/' }]);
    const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(String(e)));
    await p.goto(`http://${HOST}/admin-portal/settings/?section=integrations&view=analytics`, { waitUntil: 'networkidle' });
    const btn = p.locator('[data-drawer-open="drawer-google_analytics"]'); await btn.focus(); await btn.click(); await sleep(300);
    const open = await p.evaluate(() => document.getElementById('drawer-google_analytics').open);
    await p.screenshot({ path: `${out}/drawer_ga4_${w}.png` });
    const ov = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    const dw = await p.evaluate(() => { const d = document.getElementById('drawer-google_analytics'); return [d.scrollWidth - d.clientWidth, Math.round(d.getBoundingClientRect().width)]; });
    // Escape closes and focus returns
    await p.keyboard.press('Escape'); await sleep(250);
    const closed = await p.evaluate(() => !document.getElementById('drawer-google_analytics').open);
    const focusBack = await p.evaluate(() => document.activeElement && document.activeElement.getAttribute('data-drawer-open'));
    // invalid submit shows the field error and keeps the saved value
    await btn.click(); await sleep(200);
    const before = await p.inputValue('#int-google_analytics-measurement_id');
    await p.fill('#int-google_analytics-measurement_id', '<script>alert(1)</script>');
    p.once('dialog', d => d.accept());
    await Promise.all([p.waitForNavigation(), p.click('#drawer-google_analytics [data-testid=int-save]')]);
    await sleep(500);
    const autoOpen = await p.evaluate(() => document.getElementById('drawer-google_analytics').open);
    const errText = await p.locator('[data-testid=int-field-error]').first().textContent().catch(() => '');
    const invalid = await p.getAttribute('#int-google_analytics-measurement_id', 'aria-invalid');
    await p.screenshot({ path: `${out}/drawer_ga4_error_${w}.png` });
    await p.keyboard.press('Escape'); p.once('dialog', d => d.accept()); await sleep(300);
    // stored value unchanged
    await p.goto(`http://${HOST}/admin-portal/settings/?section=integrations&view=analytics`, { waitUntil: 'networkidle' });
    await p.locator('[data-drawer-open="drawer-google_analytics"]').click(); await sleep(200);
    const after = await p.inputValue('#int-google_analytics-measurement_id');
    console.log(JSON.stringify({ w, open, ov, dw, closed, focusBack, before, after, autoOpen, invalid, errText: errText.trim().slice(0, 80), errs }));
    await ctx.close();
  }
  await b.close();
})();
