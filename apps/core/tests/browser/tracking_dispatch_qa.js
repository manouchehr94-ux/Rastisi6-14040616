/* Browser test (Chromium via Playwright) for the e-commerce dispatch half of apps/core/static/core/consent.js, with MOCKED providers:
   every request to a tracker host is intercepted and answered with an inert stub — nothing reaches Google or Meta. The real htmx build is loaded so the HX-Trigger → «rsTrack» DOM event
   contract is exercised for real. Run:  node apps/core/tests/browser/tracking_dispatch_qa.js   (needs `playwright`; DJANGO_SETTINGS_MODULE + a python with the project deps in $VPY) */
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path'), { execFileSync } = require('child_process');
const root = path.resolve(__dirname, '../../../..');
const consentJs = fs.readFileSync(path.join(root, 'apps/core/static/core/consent.js'), 'utf8');
const htmxJs = fs.readFileSync(path.join(root, 'apps/core/static/js/htmx.min.js'), 'utf8');
const PY = process.env.VPY || 'python3';
const config = ids => JSON.parse(execFileSync(PY, ['-c', 'import django,json,sys;django.setup();from apps.core import consent;print(json.dumps(consent.build_config(json.loads(sys.argv[1]))))', JSON.stringify(ids)],
  { cwd: root, env: { ...process.env, DJANGO_SETTINGS_MODULE: process.env.DJANGO_SETTINGS_MODULE || 'shop_core.settings' } }).toString());
const ALL = { ga4: 'G-AAAA1111', gtm: 'GTM-AAA111', meta_pixel: '1111111111111111' };
const GA4_ONLY = { ga4: 'G-AAAA1111' };
const META_ONLY = { meta_pixel: '1111111111111111' };
const ev = (name, id, extra = {}) => ({ name, id, currency: 'IRR', value: 2500000, items: [{ item_id: 'SKU-1', item_name: 'کالا', price: 1250000, quantity: 2 }], ...extra });
const results = []; const ok = (n, c, x = '') => { results.push(c); console.log((c ? 'PASS ' : 'FAIL ') + n + (x ? '  ' + x : '')); };
const URL_ = 'http://shop.test/';
const page_html = (cfg, events) => `<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><title>t</title></head><body><button id="b">x</button><div id="out"></div>
<script id="rs-consent-config" type="application/json">${JSON.stringify(cfg)}</script>${events ? `<script id="rs-track-events" type="application/json">${JSON.stringify(events)}</script>` : ''}
<script src="/htmx.min.js"></script><script src="/consent.js" defer></script></body></html>`;

(async () => {
  const browser = await chromium.launch();
  async function open({ ids, events = null, cookie = null, gpc = false, htmxTrigger = null }) {
    const ctx = await browser.newContext({ locale: 'fa-IR' });
    if (gpc) await ctx.addInitScript(() => Object.defineProperty(navigator, 'globalPrivacyControl', { value: true }));
    if (cookie) await ctx.addCookies([{ name: 'rs_consent', value: encodeURIComponent(JSON.stringify({ v: 1, a: cookie.a, m: cookie.m, t: 1 })), url: URL_ }]);
    const external = [];
    await ctx.route('**/*', route => {
      const u = new URL(route.request().url());
      if (u.hostname === 'shop.test') {
        if (u.pathname === '/consent.js') return route.fulfill({ contentType: 'text/javascript', body: consentJs });
        if (u.pathname === '/htmx.min.js') return route.fulfill({ contentType: 'text/javascript', body: htmxJs });
        if (u.pathname === '/cart/add/x/') return route.fulfill({ status: 200, contentType: 'text/html', headers: { 'HX-Trigger': JSON.stringify({ toast: { message: 'ok', type: 'ok' }, rsTrack: htmxTrigger || ev('add_to_cart', 'atc-1') }) }, body: '<span></span>' });
        return route.fulfill({ contentType: 'text/html; charset=utf-8', body: page_html(config(ids), events) });
      }
      external.push(u.href);                                    // mocked: inert stub, never the real provider
      route.fulfill({ contentType: 'text/javascript', body: '/* stub */' });
    });
    const page = await ctx.newPage(); const errors = []; page.on('pageerror', e => errors.push(String(e)));
    await page.goto(URL_, { waitUntil: 'networkidle' });
    return { ctx, page, external, errors };
  }
  const dl = page => page.evaluate(() => (window.dataLayer || []).map(a => Object.prototype.toString.call(a) === '[object Arguments]' ? Array.prototype.slice.call(a) : a));
  const dlEvents = async page => (await dl(page)).filter(e => e && !Array.isArray(e) && e.event && !String(e.event).startsWith('gtm.')).map(e => e.event);
  const gtagEvents = async page => (await dl(page)).filter(e => Array.isArray(e) && e[0] === 'event').map(e => e[1]);
  const fbq = page => page.evaluate(() => ((window.fbq && window.fbq.queue) || []).map(a => Array.prototype.slice.call(a)).filter(a => a[0] === 'track'));
  const addToCart = page => page.evaluate(() => new Promise(res => { document.body.addEventListener('htmx:afterRequest', () => setTimeout(res, 50), { once: true }); htmx.ajax('POST', '/cart/add/x/', { target: '#out' }); }));
  const accept = page => page.locator('[data-testid="consent-accept"]').click().then(() => page.waitForTimeout(150));
  const reject = page => page.locator('[data-testid="consent-reject"]').click().then(() => page.waitForTimeout(150));

  // 1. no choice yet: page events are dropped, and NEVER replayed after a later accept
  { const { page, external } = await open({ ids: ALL, events: [ev('view_item', 'vi-1')] });
    ok('no choice: no tracker request and no dispatch', external.length === 0 && (await dlEvents(page)).length === 0 && (await fbq(page)).length === 0);
    await accept(page);
    ok('accept does NOT replay the dropped page event (GTM)', !(await dlEvents(page)).includes('view_item'));
    ok('accept does NOT replay the dropped page event (Meta: only PageView)', JSON.stringify((await fbq(page)).map(a => a[1])) === '["PageView"]');
    await addToCart(page);
    ok('after accept an htmx add_to_cart goes to GTM dataLayer once', (await dlEvents(page)).filter(e => e === 'add_to_cart').length === 1);
    const t = (await fbq(page)).filter(a => a[1] === 'AddToCart');
    ok('…and to Meta as the standard AddToCart with eventID', t.length === 1 && t[0][3].eventID === 'atc-1' && t[0][2].currency === 'IRR' && t[0][2].value === 2500000 && t[0][2].contents[0].id === 'SKU-1', JSON.stringify(t[0]));
    await addToCart(page);
    ok('the same event id is never dispatched twice (htmx repeat)', (await dlEvents(page)).filter(e => e === 'add_to_cart').length === 1 && (await fbq(page)).filter(a => a[1] === 'AddToCart').length === 1);
  }
  // 2. reject: nothing at all
  { const { page, external } = await open({ ids: ALL, events: [ev('view_item', 'vi-2')] });
    await reject(page); await addToCart(page);
    ok('reject: no tracker request, no dispatch (page or htmx)', external.length === 0 && (await dlEvents(page)).length === 0 && (await fbq(page)).length === 0);
  }
  // 3. stored consent + page event: dispatched once to GTM and Meta; the GTM push is the validated ecommerce object
  { const { page } = await open({ ids: ALL, events: [ev('view_item', 'vi-3')], cookie: { a: 1, m: 1 } });
    const d = (await dl(page)).filter(e => !Array.isArray(e) && e.event === 'view_item');
    ok('stored consent: view_item reaches GTM exactly once with ecommerce items', d.length === 1 && d[0].ecommerce.items[0].price === 1250000 && d[0].event_id === 'vi-3');
    ok('stored consent: Meta ViewContent with eventID', (await fbq(page)).some(a => a[1] === 'ViewContent' && a[3].eventID === 'vi-3'));
    ok('the events script node is consumed', await page.evaluate(() => !document.getElementById('rs-track-events')));
    ok('GA4 via GTM is NOT also sent directly', (await gtagEvents(page)).length === 0);
  }
  // 4. analytics only (no marketing): GA4 direct only; Meta absent
  { const { page, external } = await open({ ids: { ...GA4_ONLY, ...META_ONLY }, events: [ev('begin_checkout', 'bc-9-1-0', { once: true })], cookie: { a: 1, m: 0 } });
    ok('analytics only: GA4 direct begin_checkout, no Meta request/dispatch', (await gtagEvents(page)).includes('begin_checkout') && !external.some(u => /facebook/.test(u)) && (await fbq(page)).length === 0);
    await page.reload({ waitUntil: 'networkidle' });
    ok('begin_checkout (once) is not repeated on reload within the dedupe window', (await gtagEvents(page)).filter(e => e === 'begin_checkout').length === 0);
  }
  // 5. marketing only: Meta yes, GA4 no
  { const { page } = await open({ ids: { ...GA4_ONLY, ...META_ONLY }, events: [ev('view_item', 'vi-5')], cookie: { a: 0, m: 1 } });
    ok('marketing only: Meta ViewContent, no GA4 event', (await fbq(page)).some(a => a[1] === 'ViewContent') && (await gtagEvents(page)).length === 0);
  }
  // 6. GPC wins over a stored marketing grant
  { const { page, external } = await open({ ids: META_ONLY, events: [ev('view_item', 'vi-6')], cookie: { a: 1, m: 1 }, gpc: true });
    ok('GPC: marketing grant ignored — no Meta request, no dispatch', !external.some(u => /facebook/.test(u)) && (await fbq(page)).length === 0);
  }
  // 7. withdrawal after accept: page reloads without the tags and later events are dropped
  { const { page } = await open({ ids: ALL, cookie: { a: 1, m: 1 } });
    await page.evaluate(() => document.querySelector('[data-rs-consent-open]').click());
    await page.locator('[data-testid="consent-reject"]').click();
    await page.waitForLoadState('networkidle'); await page.waitForTimeout(200);
    await addToCart(page);
    ok('withdrawal: later events are not dispatched', (await dlEvents(page)).length === 0 && (await fbq(page)).length === 0);
  }
  // 8. validation: bad shape / currency / PII keys never reach a provider
  { const bad = [ev('purchase', 'p-1'), ev('add_to_cart', 'a-bad', { currency: 'USD' }), ev('add_to_cart', 'a-bad2', { value: '10' }), ev('add_to_cart', 'a bad id'),
                 { ...ev('add_to_cart', 'a-bad3'), items: [] }, ev('add_to_cart', 'a-bad4', { items: [{ item_id: 'x', item_name: 'n', price: 1.5, quantity: 1 }] })];
    const { page } = await open({ ids: ALL, cookie: { a: 1, m: 1 } });
    await page.evaluate(b => b.forEach(e => document.dispatchEvent(new CustomEvent('rsTrack', { detail: e }))), bad);
    ok('invalid events (purchase, USD, string value, bad id, empty items, fractional price) are all dropped', (await dlEvents(page)).length === 0 && (await fbq(page)).filter(a => a[1] !== 'PageView').length === 0);
    await page.evaluate(e => document.dispatchEvent(new CustomEvent('rsTrack', { detail: e })), { ...ev('add_to_cart', 'a-pii'), email: 'a@b.c', phone: '0912', items: [{ item_id: 'x', item_name: 'n', price: 1, quantity: 1, email: 'a@b.c' }] });
    const pushed = JSON.stringify((await dl(page)).filter(e => !Array.isArray(e) && e.event === 'add_to_cart'));
    ok('unknown keys (PII) are stripped before dispatch', pushed.includes('a-pii') && !/email|phone|0912/.test(pushed));
  }
  // 8b. failures of storage or of a provider call never break the page (cart / checkout scripts keep running) and never lose the NEXT event
  { const { page, errors } = await open({ ids: ALL, cookie: { a: 1, m: 1 } });
    await page.evaluate(() => { Storage.prototype.getItem = () => { throw new Error('storage blocked'); }; Storage.prototype.setItem = () => { throw new Error('storage blocked'); };
                                const real = window.fbq; window.fbq = function () { throw new Error('provider exploded'); }; window.__real = real; });
    await page.evaluate(e => document.dispatchEvent(new CustomEvent('rsTrack', { detail: e })), ev('begin_checkout', 'bc-1-1-0', { once: true }));
    ok('storage + provider exceptions are swallowed (no page error) and GTM still received the event', errors.length === 0 && (await dlEvents(page)).includes('begin_checkout'), errors.join('|'));
    await page.evaluate(() => { window.__other = 0; setTimeout(() => { window.__other = 1; }, 10); });
    await page.waitForTimeout(60);
    ok('other page scripts keep running afterwards', await page.evaluate(() => window.__other === 1));
  }
  // 8c. two tabs of one browser profile: the same checkout identity is dispatched once; a NEW cycle identity is always dispatched
  { const ctx = await browser.newContext({ locale: 'fa-IR' });
    await ctx.addCookies([{ name: 'rs_consent', value: encodeURIComponent(JSON.stringify({ v: 1, a: 1, m: 1, t: 1 })), url: URL_ }]);
    await ctx.route('**/*', route => { const u = new URL(route.request().url());
      if (u.hostname !== 'shop.test') return route.fulfill({ contentType: 'text/javascript', body: '/* stub */' });
      if (u.pathname === '/consent.js') return route.fulfill({ contentType: 'text/javascript', body: consentJs });
      if (u.pathname === '/htmx.min.js') return route.fulfill({ contentType: 'text/javascript', body: htmxJs });
      const id = u.searchParams.get('id');
      return route.fulfill({ contentType: 'text/html; charset=utf-8', body: page_html(config(ALL), [ev('begin_checkout', id, { once: true })]) }); });
    const count = async (p) => (await dlEvents(p)).filter(e => e === 'begin_checkout').length;
    const t1 = await ctx.newPage(); await t1.goto(URL_ + '?id=bc-1-5-0', { waitUntil: 'networkidle' });
    const t2 = await ctx.newPage(); await t2.goto(URL_ + '?id=bc-1-5-0', { waitUntil: 'networkidle' });
    ok('same cycle identity in a second tab: dispatched once in total', (await count(t1)) === 1 && (await count(t2)) === 0, `${await count(t1)}/${await count(t2)}`);
    const t3 = await ctx.newPage(); await t3.goto(URL_ + '?id=bc-1-5-1', { waitUntil: 'networkidle' });
    ok('a new checkout cycle (new identity) within 24 h is NOT suppressed', (await count(t3)) === 1);
    await ctx.close();
  }
  // 8d. purchase: validated, order identity required, dispatched once to GTM + Meta (eventID), direct GA4 only without GTM, never replayed
  { const pur = (id, extra = {}) => ev('purchase', `purchase:${id}`, { transaction_id: id, shipping: 450000, tax: 0, coupon: 'WELCOME', once: true, ...extra });
    const a = await open({ ids: ALL, events: [pur('ORD-1')], cookie: { a: 1, m: 1 } });
    const d = (await dl(a.page)).filter(e => !Array.isArray(e) && e.event === 'purchase');
    ok('purchase: GTM dataLayer gets ecommerce.transaction_id / value / items once', d.length === 1 && d[0].ecommerce.transaction_id === 'ORD-1' && d[0].ecommerce.value === 2500000 && d[0].event_id === 'purchase:ORD-1');
    const t = (await fbq(a.page)).filter(x => x[1] === 'Purchase');
    ok('purchase: Meta standard Purchase with eventID, IRR value and contents', t.length === 1 && t[0][3].eventID === 'purchase:ORD-1' && t[0][2].currency === 'IRR' && t[0][2].value === 2500000 && t[0][2].contents[0].id === 'SKU-1');
    ok('purchase: GA4 is not also sent directly when GTM serves it', (await gtagEvents(a.page)).length === 0);
    const g = await open({ ids: GA4_ONLY, events: [pur('ORD-2')], cookie: { a: 1, m: 0 } });
    const ge = (await dl(g.page)).filter(e => Array.isArray(e) && e[0] === 'event' && e[1] === 'purchase');
    ok('purchase: GA4-only store sends gtag purchase with transaction_id', ge.length === 1 && ge[0][2].transaction_id === 'ORD-2' && ge[0][2].shipping === 450000);
    const n = await open({ ids: ALL, events: [pur('ORD-3')] });
    await accept(n.page);
    ok('purchase: an event that arrived before consent is NEVER replayed after the grant', !(await dlEvents(n.page)).includes('purchase') && (await fbq(n.page)).every(x => x[1] !== 'Purchase'));
    const bad = await open({ ids: ALL, events: [ev('purchase', 'purchase:ORD-4'), pur('ORD 5'), pur('ORD-6', { tax: -1 }), pur('ORD-7', { coupon: 'x'.repeat(41) })], cookie: { a: 1, m: 1 } });
    ok('purchase: without a valid transaction_id / with bad tax or coupon it is dropped', !(await dlEvents(bad.page)).includes('purchase') && (await fbq(bad.page)).every(x => x[1] !== 'Purchase'));
    await a.page.reload({ waitUntil: 'networkidle' });
    ok('purchase: the same order identity is not dispatched again after a reload (best-effort browser dedupe)', (await dlEvents(a.page)).filter(e => e === 'purchase').length === 0);
  }
  // 9. no unhandled exceptions anywhere on the harness page
  { const { errors } = await open({ ids: ALL, events: [ev('view_item', 'vi-x')], cookie: { a: 1, m: 1 } });
    ok('no page errors', errors.length === 0, errors.join(' | '));
  }
  await browser.close();
  const failed = results.filter(r => !r).length;
  console.log(`\n${results.length - failed}/${results.length} passed`);
  process.exit(failed ? 1 : 0);
})();
