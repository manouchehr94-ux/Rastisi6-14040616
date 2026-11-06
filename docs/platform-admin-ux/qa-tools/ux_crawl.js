// usage: node ux_crawl.js <port> <outdir> <label> [fullshots=1]
const { chromium } = require('playwright'); const fs = require('fs');
const [port, OUT, label, keep] = [process.argv[2], process.argv[3], process.argv[4], process.argv[5] || 'all'];
const V = JSON.parse(fs.readFileSync('/tmp/rs_reg/ux_vals.json')); const R = JSON.parse(fs.readFileSync('/tmp/rs_reg/ux_routes.json'));
fs.mkdirSync(OUT, { recursive: true });
const HOST = `http://platformadmins.rastisi.localhost:${port}`;
const WIDTHS = [1440, 1280, 768, 390, 320];
const POST_ONLY = /(suspend|activate|extend|set-trial|end-trial|support-login|add-note|archive|publish|cancel|resume|adjust|check|set-primary|reset|switch|toggle|test|preview|logout|verify|refund|action|receipt|login)$/;
function fill(route) { let miss = false; const p = route.replace(/<(\w+):(\w+)>/g, (_, c, n) => { if (V.vals[n] === undefined || V.vals[n] === '') { miss = n; return ''; } return V.vals[n]; }); return miss ? null : '/' + p; }
(async () => {
  const b = await chromium.launch(); const report = [];
  const ctx0 = await b.newContext({ viewport: { width: 1440, height: 900 }, locale: 'fa-IR' });
  await ctx0.addCookies([{ name: 'sessionid', value: V.session, domain: 'platformadmins.rastisi.localhost', path: '/' }]);
  const p0 = await ctx0.newPage();
  // discover parameterised detail links from list pages
  const disc = {};
  for (const [key, list, prefix] of [['sms_event', '/sms/templates/', '/sms/templates/'], ['notif_event', '/notifications/', '/notifications/'], ['slot', '/public-photos/', '/public-photos/'], ['site_slug', '/public-site/', '/public-site/']]) {
    await p0.goto(HOST + list, { waitUntil: 'domcontentloaded' });
    disc[key] = await p0.$$eval('a[href]', (as, pre) => as.map(a => a.getAttribute('href')).filter(h => h && h.startsWith(pre) && h.length > pre.length && !h.includes('?') && !/(switch|reset|senders|delivery|audit)\/?$/.test(h) && h.endsWith('/')).slice(0, 1), prefix);
  }
  await ctx0.close();
  const targets = [];
  for (const r of R) {
    if (POST_ONLY.test(r.name) && !/-(add|edit)$/.test(r.name)) continue;
    let path = fill(r.route);
    if (!path) {
      if (r.route.startsWith('sms/templates/<str')) path = disc.sms_event[0];
      else if (r.route.startsWith('notifications/<str')) path = disc.notif_event[0];
      else if (r.route.startsWith('public-photos/<slug')) path = disc.slot[0];
      else if (r.route.startsWith('public-site/<slug')) path = disc.site_slug[0];
    }
    if (path) targets.push({ name: r.name, path });
  }
  for (const w of WIDTHS) {
    const ctx = await b.newContext({ viewport: { width: w, height: 900 }, locale: 'fa-IR' });
    await ctx.addCookies([{ name: 'sessionid', value: V.session, domain: 'platformadmins.rastisi.localhost', path: '/' }]);
    const page = await ctx.newPage(); let errs = [];
    page.on('pageerror', e => errs.push('pageerror: ' + String(e).slice(0, 160)));
    page.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text().slice(0, 160)); });
    for (const t of targets) {
      errs = [];
      let status = 0, final = '';
      try { const r = await page.goto(HOST + t.path, { waitUntil: 'networkidle', timeout: 30000 }); status = r ? r.status() : 0; final = page.url().replace(HOST, ''); } catch (e) { errs.push('nav: ' + String(e).slice(0, 100)); }
      let m = {};
      try { m = await page.evaluate(() => {
        const de = document.documentElement;
        const nums = [...document.querySelectorAll('input[type=number]')];
        const spin = nums.filter(i => { try { return getComputedStyle(i, '::-webkit-inner-spin-button').webkitAppearance !== 'none' && getComputedStyle(i).appearance !== 'textfield' && getComputedStyle(i).webkitAppearance !== 'textfield'; } catch (e) { return false; } }).length;
        const btns = [...document.querySelectorAll('main button, main .pa-btn, main a.pa-btn')].filter(x => x.offsetParent);
        const hs = {}; btns.forEach(x => { const h = Math.round(x.getBoundingClientRect().height); hs[h] = (hs[h] || 0) + 1; });
        return { overflow: de.scrollWidth - de.clientWidth, h1: (document.querySelector('h1') || {}).innerText || '', navs: document.querySelectorAll('aside, nav.pa-nav, [data-pa-sidebar]').length, numInputs: nums.length, spin, btnHeights: hs, inlineStyle: document.querySelectorAll('[style]').length, title: document.title };
      }); } catch (e) { errs.push('eval: ' + String(e).slice(0, 100)); }
      const rec = { w, name: t.name, path: t.path, status, final, errs: errs.slice(0, 3), ...m }; report.push(rec);
      if (keep === 'all' || (keep === 'key' && ['home', 'stores', 'store-detail', 'plan-edit', 'assignment-matrix', 'payments', 'sms-providers', 'configuration'].includes(t.name))) {
        await page.screenshot({ path: `${OUT}/${label}-${t.name}-${w}.jpg`, fullPage: true, type: 'jpeg', quality: 60 }).catch(() => {});
      }
    }
    await ctx.close();
  }
  fs.writeFileSync(`${OUT}/${label}-report.json`, JSON.stringify(report, null, 1));
  const bad = report.filter(r => r.status !== 200 || r.overflow > 0 || r.errs.length);
  console.log(JSON.stringify({ pages: targets.length, checks: report.length, bad: bad.slice(0, 40).map(r => `${r.w} ${r.name} ${r.status} ov=${r.overflow} ${r.errs.join('|')}`) }, null, 1));
  await b.close();
})();
