const { chromium } = require('playwright'); const fs = require('fs');
const V = JSON.parse(fs.readFileSync('/tmp/rs_reg/ux_vals.json')); const port = process.argv[2]; const out = process.argv[3]; const spec = process.argv.slice(4);
(async () => {
  const b = await chromium.launch(); fs.mkdirSync(out, { recursive: true });
  for (const s of spec) { const [path, w] = s.split('@'); const ctx = await b.newContext({ viewport: { width: +w, height: 900 }, locale: 'fa-IR' });
    await ctx.addCookies([{ name: 'sessionid', value: V.session, domain: 'platformadmins.rastisi.localhost', path: '/' }]);
    const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(String(e))); p.on('console', m => m.type() === 'error' && errs.push(m.text().slice(0, 120)));
    await p.goto(`http://platformadmins.rastisi.localhost:${port}${path}`, { waitUntil: 'networkidle' });
    const name = path.replace(/\W+/g, '_') + '_' + w; await p.screenshot({ path: `${out}/${name}.png`, fullPage: false });
    console.log(name, 'overflow', await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), errs.join('|')); await ctx.close(); }
  await b.close();
})();
