const { chromium } = require('playwright'); const fs = require('fs'); const V = JSON.parse(fs.readFileSync('/tmp/rs_reg/ux_vals.json')); const PORT = process.env.PORT || 8032;
(async () => { const b = await chromium.launch(); let allOk = true;
  for (const w of [390, 320]) { const c = await b.newContext({ viewport: { width: w, height: 800 }, locale: 'fa-IR' }); await c.addCookies([{ name: 'sessionid', value: V.session, domain: 'platformadmins.rastisi.localhost', path: '/' }]); const p = await c.newPage();
    await p.goto(`http://platformadmins.rastisi.localhost:${PORT}/plans/`, { waitUntil: 'networkidle' });
    // reproduce the defect shape: a wide table whose LAST cell holds an absolutely-positioned sr-only label
    await p.evaluate(() => { const card = document.createElement('div'); card.className = 'pa-card'; card.id = 'sr-probe'; const wrap = document.createElement('div'); wrap.className = 'pa-tablewrap';
      wrap.innerHTML = '<table><thead><tr><th>#</th><th>فروشگاه</th><th>بسته</th><th>اعتبار</th><th>قیمت</th><th>وضعیت</th><th>پرداختِ آنلاین</th><th>اقدام</th></tr></thead><tbody><tr><td>1</td><td>فروشگاه</td><td>بسته</td><td>500</td><td>90000</td><td>تکمیل</td><td>zibal · succeeded</td><td><div class="pa-row-actions"><form class="pa-inline-form"><label class="pa-sr" for="probe-in">دلیلِ بازپرداخت</label><input id="probe-in" class="pa-w-sm" name="reason" required placeholder="دلیلِ بازپرداخت"><button class="pa-btn" type="button">بازپرداخت</button></form></div></td></tr></tbody></table>'; card.appendChild(wrap); document.querySelector('main').appendChild(card); });
    const ovf = async () => p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    const withFix = await ovf();
    await p.addStyleTag({ content: '.pa-tablewrap,.pa-card{position:static!important}' });   // neutralise the fix → reproduces the original defect
    const withoutFix = await ovf();
    await p.reload({ waitUntil: 'networkidle' });
    // accessibility: the sr-only label still names its control and is not display:none
    const a11y = await p.evaluate(() => { const l = document.querySelector('.pa-sr'); const cs = getComputedStyle(l); return { display: cs.display, visibility: cs.visibility, clip: cs.clip, pos: cs.position, w: cs.width, labelFor: !!document.querySelector('label.pa-sr[for]') }; });
    const named = await p.getByLabel('جستجو در فروشگاه‌ها').count();
    const ok = withFix === 0 && a11y.display !== 'none' && a11y.visibility !== 'hidden' && named >= 1;
    allOk = allOk && ok;
    console.log(`${w}px: overflow with fix=${withFix}, with fix neutralised=${withoutFix} (defect reproduced=${withoutFix > 0}); sr-only: ${JSON.stringify(a11y)}; getByLabel finds search input=${named >= 1}`); await c.close(); }
  console.log(allOk ? 'SR CHECK PASSED' : 'SR CHECK FAILED'); await b.close(); })();
