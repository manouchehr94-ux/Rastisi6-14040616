// P5-W1 — Free-Shipping Goal browser QA on the real storefront cart.
// Adds items to the real session cart via the canonical cart:add endpoint
// (CSRF-cookie aware, cookies shared with the page), then loads /cart/ and
// captures the goal states at RTL desktop/tablet/mobile. No HTML is patched in
// the browser — every state is real server-rendered output.
import fs from 'node:fs';
import process from 'node:process';
import { chromium } from 'playwright-core';

const HOST = process.env.QA_HOST || 'rastisi-fashion-test.rastisi.localhost';
const PORT = process.env.QA_PORT || '8817';
const BASE = `http://${HOST}:${PORT}`;
const REPORT_DIR = process.env.QA_REPORT_DIR || '/tmp/w1_qa';
fs.mkdirSync(REPORT_DIR, { recursive: true });

// slug -> add. Physical cheap (350k, below 500k threshold), physical expensive
// (1,337k, above), digital (giftcard, requires_shipping=False).
const PHYS_CHEAP = process.env.QA_PHYS_CHEAP || 'shirt-casual-نیکا-5';
const PHYS_EXPENSIVE = process.env.QA_PHYS_EXPENSIVE || 'shirt-formal-بردیا-4';
const DIGITAL = process.env.QA_DIGITAL || 'qa-digital-giftcard';

const VIEWPORTS = [
  { name: 'desktop-1440', width: 1440, height: 900 },
  { name: 'tablet-768', width: 768, height: 1024 },
  { name: 'mobile-390', width: 390, height: 844 },
];

const report = { host: HOST, base: BASE, started_at: new Date().toISOString(), checks: [], console_errors: [], failed_requests: [] };
function record(name, status, detail) {
  report.checks.push({ name, status, detail: detail ?? null });
  console.log(`${status.padEnd(5)} ${name}${detail ? ' — ' + JSON.stringify(detail) : ''}`);
}

const browser = await chromium.launch({
  executablePath: process.env.QA_CHROME || '/usr/local/bin/chrome',
  headless: true,
  args: [`--host-resolver-rules=MAP ${HOST} 127.0.0.1`, '--no-sandbox'],
});

function cookie(name, cookies) {
  const c = cookies.find((x) => x.name === name);
  return c ? c.value : '';
}

async function freshContext(vp) {
  const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, baseURL: BASE });
  return ctx;
}

// Add a product to the session cart via the canonical cart:add endpoint,
// using the CSRF cookie that Django set on the first GET.
async function addToCart(ctx, slug) {
  // ensure a csrftoken cookie exists
  await ctx.request.get('/cart/');
  const cookies = await ctx.cookies();
  const csrf = cookie('csrftoken', cookies);
  const resp = await ctx.request.post(`/cart/add/${encodeURIComponent(slug)}/`, {
    headers: { 'X-CSRFToken': csrf, 'Referer': BASE + '/cart/', 'HX-Request': 'true' },
    form: { quantity: '1', variant_id: '' },
  });
  return resp.status();
}

async function goalState(page) {
  return page.evaluate(() => {
    const fsg = document.querySelector('.fsg');
    const fill = document.querySelector('.fsg-fill');
    const goalMsg = document.querySelector('.fsg--goal .fsg-msg');
    const successMsg = document.querySelector('.fsg--success .fsg-msg');
    const doc = document.documentElement;
    return {
      present: !!fsg,
      kind: fsg ? (fsg.classList.contains('fsg--success') ? 'success' : (fsg.classList.contains('fsg--goal') ? 'goal' : 'other')) : null,
      goalText: goalMsg ? goalMsg.textContent.trim() : null,
      successText: successMsg ? successMsg.textContent.trim() : null,
      fillWidthPx: fill ? Math.round(fill.getBoundingClientRect().width) : null,
      trackWidthPx: fill && fill.parentElement ? Math.round(fill.parentElement.getBoundingClientRect().width) : null,
      dir: doc.getAttribute('dir') || document.body.getAttribute('dir') || '',
      scrollWidth: doc.scrollWidth,
      clientWidth: doc.clientWidth,
      checkoutPresent: !!document.querySelector("a[href*='checkout']"),
    };
  });
}

// state = {name, adds:[slugs]} ; expectation checked by caller
async function runState(vp, name, adds, expect) {
  const ctx = await freshContext(vp); // fresh session per state (isolated cart)
  const page = await ctx.newPage();
  page.on('console', (m) => { if (m.type() === 'error') report.console_errors.push({ vp: vp.name, state: name, text: m.text() }); });
  page.on('requestfailed', (r) => report.failed_requests.push({ vp: vp.name, state: name, url: r.url() }));
  for (const slug of adds) {
    const st = await addToCart(ctx, slug);
    if (st >= 400) record(`add:${name}:${slug}:${vp.name}`, 'FAIL', { status: st });
  }
  const resp = await page.goto('/cart/', { waitUntil: 'networkidle', timeout: 30000 });
  const g = await goalState(page);
  // no horizontal overflow
  record(`overflow:${name}:${vp.name}`, g.scrollWidth <= g.clientWidth + 3 ? 'PASS' : 'FAIL', { sw: g.scrollWidth, cw: g.clientWidth });
  record(`rtl:${name}:${vp.name}`, g.dir === 'rtl' ? 'PASS' : 'WARN', { dir: g.dir });
  record(`checkout-usable:${name}:${vp.name}`, g.checkoutPresent ? 'PASS' : (name === 'empty' ? 'WARN' : 'FAIL'));
  // progress bar bounded (fill never wider than track)
  if (g.fillWidthPx != null && g.trackWidthPx != null) {
    record(`bar-bounded:${name}:${vp.name}`, g.fillWidthPx <= g.trackWidthPx + 1 ? 'PASS' : 'FAIL', { fill: g.fillWidthPx, track: g.trackWidthPx });
  }
  expect(g, name, vp);
  await page.screenshot({ path: `${REPORT_DIR}/cart_${name}_${vp.name}.png`, fullPage: false });
  await ctx.close();
  report.geometry = report.geometry || [];
  report.geometry.push({ vp: vp.name, state: name, ...g });
}

for (const vp of VIEWPORTS) {
  // B — below threshold (physical cheap 350k < 500k)
  await runState(vp, 'below', [PHYS_CHEAP], (g, name, v) => {
    record(`state-below:${v.name}`, g.present && g.kind === 'goal' && /تا ارسال رایگان/.test(g.goalText || '') ? 'PASS' : 'FAIL', { kind: g.kind, goalText: g.goalText });
  });
  // C — threshold reached (physical expensive 1,337k >= 500k)
  await runState(vp, 'reached', [PHYS_EXPENSIVE], (g, name, v) => {
    record(`state-reached:${v.name}`, g.present && g.kind === 'success' && /ارسال رایگان فعال شد/.test(g.successText || '') ? 'PASS' : 'FAIL', { kind: g.kind, successText: g.successText });
  });
  // A — all-digital (goal hidden)
  await runState(vp, 'digital', [DIGITAL], (g, name, v) => {
    record(`state-digital-hidden:${v.name}`, !g.present ? 'PASS' : 'FAIL', { present: g.present });
  });
  // empty cart (no goal, no error)
  await runState(vp, 'empty', [], (g, name, v) => {
    record(`state-empty-safe:${v.name}`, !g.present ? 'PASS' : 'FAIL', { present: g.present });
  });
}

report.finished_at = new Date().toISOString();
const pass = report.checks.filter((c) => c.status === 'PASS').length;
const fail = report.checks.filter((c) => c.status === 'FAIL').length;
const warn = report.checks.filter((c) => c.status === 'WARN').length;
report.summary = { pass, fail, warn, total: report.checks.length, console_errors: report.console_errors.length, failed_requests: report.failed_requests.length };
fs.writeFileSync(`${REPORT_DIR}/report.json`, JSON.stringify(report, null, 2));
console.log(`\nSUMMARY: PASS=${pass} FAIL=${fail} WARN=${warn} console_errors=${report.console_errors.length} failed_requests=${report.failed_requests.length}`);
await browser.close();
process.exit(fail > 0 ? 1 : 0);
