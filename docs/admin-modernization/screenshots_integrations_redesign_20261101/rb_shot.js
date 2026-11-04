const { chromium } = require('playwright'); const { execSync } = require('child_process');
const SP = '/tmp/claude-0/-home-user-Rastisi6-14040616/9464551a-7c83-50df-b657-f00f736fb713/scratchpad';
const out = `${SP}/shots`; const sleep = ms => new Promise(r => setTimeout(r, ms));
const HOST = 'rastisi-fashion-test.rastisi.localhost:8009';
const views = (process.argv[3] || 'overview,seo,analytics,torob,enamad,future').split(',');
(async () => {
  const sid = execSync(`/home/user/ADMIN_QA_DATA_20261031/venv/bin/python /home/user/ADMIN_QA_DATA_20261031/mksession.py 09120000002`, {cwd: '/home/user/Rastisi6-14040616'}).toString().trim();
  const b = await chromium.launch();
  for (const w of (process.argv[2] || '1440').split(',').map(Number)) {
    const ctx = await b.newContext({ viewport: { width: w, height: 900 }, locale: 'fa-IR' });
    await ctx.addCookies([{ name: 'sessionid', value: sid, domain: 'rastisi-fashion-test.rastisi.localhost', path: '/' }]);
    const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(String(e)));
    for (const v of views) {
      await p.goto(`http://${HOST}/admin-portal/settings/?section=integrations${v === 'overview' ? '' : '&view=' + v}`, { waitUntil: 'networkidle' }); await sleep(400);
      await p.screenshot({ path: `${out}/${v}_${w}.png`, fullPage: true });
      const ov = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      const tabs = await p.$$eval('.admin-subtab', a => a.map(x => x.textContent.trim() + (x.classList.contains('active') ? '*' : '')));
      console.log(w, v, 'overflowX', ov, 'tabs', tabs.join('|'));
    }
    console.log(w, 'pageerrors', errs.length, errs.slice(0, 2));
    await ctx.close();
  }
  await b.close();
})();
