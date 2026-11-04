const { chromium } = require('playwright'); const { execSync } = require('child_process');
const SP = '/tmp/claude-0/-home-user-Rastisi6-14040616/9464551a-7c83-50df-b657-f00f736fb713/scratchpad'; const out = `${SP}/shots`;
const sleep = ms => new Promise(r => setTimeout(r, ms)); const HOST = 'rastisi-fashion-test.rastisi.localhost:8009';
const box = async (p, sel) => p.evaluate(s => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)]; }, sel);
const overlap = (a, b) => a && b && !(a[2] <= b[0] || b[2] <= a[0] || a[3] <= b[1] || b[3] <= a[1]);
(async () => {
  const sid = execSync(`/home/user/ADMIN_QA_DATA_20261031/venv/bin/python /home/user/ADMIN_QA_DATA_20261031/mksession.py 09120000002`, {cwd: '/home/user/Rastisi6-14040616'}).toString().trim();
  const b = await chromium.launch(); const res = [];
  for (const w of [1440, 1024, 768, 390, 320]) {
    const ctx = await b.newContext({ viewport: { width: w, height: 900 }, locale: 'fa-IR', reducedMotion: 'reduce' });
    await ctx.addCookies([{ name: 'sessionid', value: sid, domain: 'rastisi-fashion-test.rastisi.localhost', path: '/' }]);
    const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(String(e)));
    await p.goto(`http://${HOST}/admin-portal/settings/?section=integrations`, { waitUntil: 'networkidle' });
    const header = await box(p, '.admin-header, header'); const subtabs = await box(p, '.admin-subtabs'); const ssearch = await box(p, '.settings-search'); const content = await box(p, '.int-page');
    const r = { w, hdr_sub: overlap(header, subtabs), sub_search: overlap(subtabs, ssearch), search_content: overlap(ssearch, content), sub_content: overlap(subtabs, content) };
    // keyboard: tab semantics — links in the bar are reachable and show a visible focus ring
    await p.focus('.admin-subtab.active'); await p.keyboard.press('Tab');
    r.focusedAfterTab = await p.evaluate(() => document.activeElement.textContent.trim().slice(0, 20));
    r.focusRing = await p.evaluate(() => getComputedStyle(document.activeElement).outlineStyle + ' ' + getComputedStyle(document.activeElement).outlineWidth);
    // touch target of tabs + primary buttons
    await p.goto(`http://${HOST}/admin-portal/settings/?section=integrations&view=analytics`, { waitUntil: 'networkidle' });
    r.tabHeight = await p.evaluate(() => Math.round(document.querySelector('.admin-subtab').getBoundingClientRect().height));
    r.manageBtn = await p.evaluate(() => { const e = document.querySelector('[data-testid=int-manage]').getBoundingClientRect(); return [Math.round(e.width), Math.round(e.height)]; });
    // settings search finds the new category and navigates to its view
    await p.fill('#settingsSearch', 'اینماد'); await sleep(500);
    r.searchHits = await p.$$eval('.settings-search-results a, [data-au-search] a', a => a.map(x => x.textContent.trim().replace(/\s+/g, ' ').slice(0, 40) + '→' + x.getAttribute('href')).slice(0, 4));
    // layout jump when opening the drawer: page scrollY/width unchanged
    const before = await p.evaluate(() => [document.documentElement.scrollWidth, window.scrollY]);
    await p.click('[data-drawer-open="drawer-google_analytics"]'); await sleep(250);
    const after = await p.evaluate(() => [document.documentElement.scrollWidth, window.scrollY]);
    r.jump = before[0] !== after[0] || before[1] !== after[1];
    // focus is inside the dialog; Tab cycles inside (modal trap)
    const inside = []; for (let i = 0; i < 6; i++) { await p.keyboard.press('Tab'); inside.push(await p.evaluate(() => !!document.activeElement.closest('dialog'))); }
    r.focusTrapped = inside.every(Boolean);
    r.dialogRole = await p.evaluate(() => { const d = document.getElementById('drawer-google_analytics'); return [d.getAttribute('aria-labelledby'), !!document.getElementById(d.getAttribute('aria-labelledby'))]; });
    r.drawerBtnH = await p.evaluate(() => Math.round(document.querySelector('#drawer-google_analytics [data-testid=int-save]').getBoundingClientRect().height));
    r.errs = errs.length; res.push(r);
    await ctx.close();
  }
  console.log(JSON.stringify(res, null, 1));
  await b.close();
})();
