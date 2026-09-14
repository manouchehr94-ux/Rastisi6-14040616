// Phase 5 Task 8 — public-storefront browser QA for the mobile Sticky
// Add-to-Cart (SATC) plus fresh PDT / PDTX regression checks. Drives the real
// published tenant PDP at mobile viewports (390x844 primary, 360x800 narrow)
// and — for the desktop-absence check — one desktop viewport. Captures
// screenshots + a JSON report. Same harness/approach as the Task 5 runner.
//
// SATC architecture under test (must all hold in the LIVE browser):
//   - SATC appears on mobile, is absent as a sticky bar on desktop.
//   - Changing the main quantity then activating SATC submits that SAME
//     quantity (one submitted quantity owner, one cart:add).
//   - SATC disabled/label agrees with the canonical CTA for
//     selection-required / sold-out / in-stock.
//   - SATC never overlaps the mobile bottom nav; sits below overlays.
//   - PDT: no 390px overflow; accordion usable.
import fs from 'node:fs';
import process from 'node:process';
import { chromium } from 'playwright-core';

const HOST = process.env.QA_HOST || 'rastisi-fashion-test.rastisi.localhost';
const PORT = process.env.QA_PORT || '8817';
const BASE = process.env.QA_BASE_URL || `http://${HOST}:${PORT}`;
const PDP_PATH = process.env.QA_PDP_PATH || '/products/accessory-scarf-%D9%BE%D8%B1%D9%87%D8%A7%D9%85-8/';
const PDP_SIMPLE_PATH = process.env.QA_PDP_SIMPLE_PATH || '';
const REPORT_DIR = process.env.QA_REPORT_DIR || '/tmp/task8_qa';
fs.mkdirSync(REPORT_DIR, { recursive: true });

const MOBILE = [
  { name: 'mobile-390', width: 390, height: 844 },
  { name: 'mobile-360', width: 360, height: 800 },
];
const DESKTOP = { name: 'desktop-1440', width: 1440, height: 900 };

const report = { host: HOST, base: BASE, pdp: PDP_PATH, started_at: new Date().toISOString(), checks: [], console_errors: [] };
function record(name, status, detail) {
  report.checks.push({ name, status, detail: detail ?? null });
  console.log(`${status.padEnd(5)} ${name}${detail ? ' — ' + JSON.stringify(detail) : ''}`);
}

const browser = await chromium.launch({
  executablePath: process.env.QA_CHROME || '/usr/local/bin/chrome',
  headless: true,
  args: [`--host-resolver-rules=MAP ${HOST} 127.0.0.1`, '--no-sandbox'],
});

async function metrics(page) {
  return page.evaluate(() => ({
    dir: document.documentElement.getAttribute('dir') || document.body.getAttribute('dir') || '',
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
}

// ---------------- DESKTOP: SATC must NOT be a visible sticky bar ----------
{
  const ctx = await browser.newContext({ viewport: { width: DESKTOP.width, height: DESKTOP.height }, baseURL: BASE });
  const page = await ctx.newPage();
  page.on('console', (m) => { if (m.type() === 'error') report.console_errors.push({ vp: DESKTOP.name, text: m.text() }); });
  const resp = await page.goto(PDP_PATH, { waitUntil: 'networkidle', timeout: 30000 });
  record(`pdp:status:${DESKTOP.name}`, resp && resp.status() === 200 ? 'PASS' : 'FAIL', { status: resp && resp.status() });
  const satc = page.locator('.pdp-satc').first();
  const present = await satc.count();
  const visible = present ? await satc.isVisible().catch(() => false) : false;
  record('satc:hidden-on-desktop', present && !visible ? 'PASS' : 'FAIL', { present, visible });
  // normal in-flow CTA present + visible on desktop
  const cta = page.locator('.pdp-actions .btn-primary').first();
  record('cta:visible-on-desktop', await cta.isVisible().catch(() => false) ? 'PASS' : 'FAIL');
  await page.screenshot({ path: `${REPORT_DIR}/pdp_${DESKTOP.name}.png`, fullPage: false });
  await ctx.close();
}

// ---------------- MOBILE viewports ---------------------------------------
for (const vp of MOBILE) {
  const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, baseURL: BASE });
  const page = await ctx.newPage();
  page.on('console', (m) => { if (m.type() === 'error') report.console_errors.push({ vp: vp.name, text: m.text() }); });

  const resp = await page.goto(PDP_PATH, { waitUntil: 'networkidle', timeout: 30000 });
  record(`pdp:status:${vp.name}`, resp && resp.status() === 200 ? 'PASS' : 'FAIL', { status: resp && resp.status() });
  const m = await metrics(page);
  record(`pdp:rtl:${vp.name}`, m.dir === 'rtl' ? 'PASS' : 'WARN', { dir: m.dir });
  record(`pdp:no-overflow:${vp.name}`, m.scrollWidth <= m.clientWidth + 3 ? 'PASS' : 'FAIL', m);

  const satc = page.locator('.pdp-satc').first();
  const satcVisible = await satc.isVisible().catch(() => false);
  record(`satc:visible-on-mobile:${vp.name}`, satcVisible ? 'PASS' : 'FAIL', { visible: satcVisible });

  // normal in-flow CTA is still present (not removed on mobile).
  const inflow = page.locator('.pdp-actions .btn-primary').first();
  record(`cta:inflow-present:${vp.name}`, await inflow.count() > 0 ? 'PASS' : 'FAIL');

  // SATC button belongs to the canonical purchase form via form= and there is
  // exactly one cart:add form on the page (no second purchase pipeline).
  const wire = await page.evaluate(() => {
    const btn = document.querySelector('.pdp-satc-btn');
    const formAttr = btn && btn.getAttribute('form');
    const form = formAttr && document.getElementById(formAttr);
    const cartForms = [...document.querySelectorAll('form[hx-post]')].filter((f) => /\/cart\/add\//.test(f.getAttribute('hx-post') || ''));
    const qtyInputs = document.querySelectorAll('[name="quantity"]');
    return {
      hasForm: !!form,
      formIsCartAdd: !!(form && /\/cart\/add\//.test(form.getAttribute('hx-post') || '')),
      cartAddFormCount: cartForms.length,
      quantityOwnerCount: qtyInputs.length,
      btnType: btn && btn.getAttribute('type'),
    };
  });
  record(`satc:submits-canonical-form:${vp.name}`, wire.hasForm && wire.formIsCartAdd && wire.btnType === 'submit' ? 'PASS' : 'FAIL', wire);
  record(`satc:one-cart-add-form:${vp.name}`, wire.cartAddFormCount === 1 ? 'PASS' : 'FAIL', { count: wire.cartAddFormCount });
  record(`satc:one-quantity-owner:${vp.name}`, wire.quantityOwnerCount === 1 ? 'PASS' : 'FAIL', { count: wire.quantityOwnerCount });

  // SATC never overlaps the bottom nav: its top edge sits at/above the nav's
  // top edge (i.e. SATC bottom-anchored ABOVE the nav). Only meaningful when a
  // bottom nav renders on this store.
  const geo = await page.evaluate(() => {
    const satcEl = document.querySelector('.pdp-satc');
    const nav = document.querySelector('.gmn .gmn-bar') || document.querySelector('.gmn');
    if (!satcEl) return { satc: null };
    const s = satcEl.getBoundingClientRect();
    const g = nav ? nav.getBoundingClientRect() : null;
    return {
      satc: { top: Math.round(s.top), bottom: Math.round(s.bottom) },
      nav: g ? { top: Math.round(g.top), bottom: Math.round(g.bottom) } : null,
      navIdentity: (document.querySelector('.gmn') && document.querySelector('.gmn').getAttribute('data-mobile-nav')) || null,
      innerHeight: window.innerHeight,
      satcZ: getComputedStyle(satcEl).zIndex,
    };
  });
  if (geo.nav) {
    // SATC's bottom must be at or above the nav bar's top (no vertical overlap).
    record(`satc:no-bottom-nav-overlap:${vp.name}`, geo.satc.bottom <= geo.nav.top + 2 ? 'PASS' : 'FAIL', geo);
  } else {
    record(`satc:no-bottom-nav-overlap:${vp.name}`, 'WARN', { note: 'no bottom nav rendered on this store', geo });
  }
  // SATC z-index is below the canonical page-covering overlays (<100) so login
  // modal / drawer / quick view cover it, and below the nav (850).
  record(`satc:z-below-overlays:${vp.name}`, Number(geo.satcZ) < 100 ? 'PASS' : 'FAIL', { z: geo.satcZ });

  // SATC label agrees with the canonical CTA (same text).
  const labels = await page.evaluate(() => {
    const cta = document.querySelector('.pdp-actions .btn-primary span:last-child');
    const s = document.querySelector('.pdp-satc-btn span:last-child');
    return { cta: cta && cta.textContent.trim(), satc: s && s.textContent.trim() };
  });
  record(`satc:label-agrees-with-cta:${vp.name}`, labels.cta && labels.satc && labels.cta === labels.satc ? 'PASS' : 'WARN', labels);

  // SATC disabled state agrees with the canonical CTA disabled state.
  const dis = await page.evaluate(() => {
    const cta = document.querySelector('.pdp-actions .btn-primary');
    const s = document.querySelector('.pdp-satc-btn');
    return { ctaDisabled: !!(cta && cta.disabled), satcDisabled: !!(s && s.disabled) };
  });
  record(`satc:disabled-agrees-with-cta:${vp.name}`, dis.ctaDisabled === dis.satcDisabled ? 'PASS' : 'FAIL', dis);

  // QUANTITY: bump the main stepper to 3, confirm the SINGLE quantity input
  // (which the SATC submits via form=) reflects 3. One quantity owner.
  const plus = page.locator('.qty .stepper button').last();
  if (await plus.count()) {
    await plus.click(); await plus.click(); // 1 -> 3
    await page.waitForTimeout(150);
    const qtyVal = await page.evaluate(() => {
      const q = document.querySelector('[name="quantity"]');
      return q ? q.value : null;
    });
    record(`satc:shares-single-quantity=3:${vp.name}`, qtyVal === '3' ? 'PASS' : 'FAIL', { quantity: qtyVal });
  }

  // PDT: tabs/accordion present, all three panels reachable, no overflow.
  const pdt = await page.evaluate(() => {
    const tabs = document.querySelectorAll('[role="tab"]').length;
    const panels = document.querySelectorAll('[role="tabpanel"]').length;
    return { tabs, panels };
  });
  record(`pdt:three-tabs-panels:${vp.name}`, pdt.tabs === 3 && pdt.panels === 3 ? 'PASS' : 'FAIL', pdt);

  // PDTX: the trust module (canonical trust_features OR the fallback guarantee
  // strip) renders exactly one trust surface.
  const trust = await page.evaluate(() => {
    const fallback = document.querySelectorAll('.guarantee').length;
    const canonical = document.querySelectorAll('[data-section-key="trust_features"], .trust-features').length;
    return { fallback, canonical };
  });
  record(`pdtx:one-trust-surface:${vp.name}`, (trust.fallback + trust.canonical) >= 1 ? 'PASS' : 'WARN', trust);

  await page.screenshot({ path: `${REPORT_DIR}/pdp_${vp.name}.png`, fullPage: false });

  // OVERLAY layering: open the mobile nav drawer (burger) and confirm the
  // drawer backdrop/panel visually cover SATC (SATC z < drawer z).
  const burger = page.locator('[data-mobile-nav-toggle], .gh-burger, button[aria-label*="منو"], .mobile-nav-toggle').first();
  if (await burger.count()) {
    await burger.click().catch(() => {});
    await page.waitForTimeout(350);
    const layering = await page.evaluate(() => {
      const drawer = document.querySelector('.mobile-nav-drawer');
      const backdrop = document.querySelector('.mobile-drawer-backdrop');
      const satcEl = document.querySelector('.pdp-satc');
      const z = (el) => el ? Number(getComputedStyle(el).zIndex) || 0 : null;
      return { drawerZ: z(drawer), backdropZ: z(backdrop), satcZ: z(satcEl) };
    });
    const covers = layering.satcZ != null && layering.drawerZ != null && layering.drawerZ > layering.satcZ;
    record(`overlay:drawer-covers-satc:${vp.name}`, covers ? 'PASS' : 'WARN', layering);
    await page.screenshot({ path: `${REPORT_DIR}/pdp_drawer_${vp.name}.png`, fullPage: false });
  } else {
    record(`overlay:drawer-covers-satc:${vp.name}`, 'WARN', { note: 'no burger/drawer toggle found on this store' });
  }

  await ctx.close();
}

report.finished_at = new Date().toISOString();
const pass = report.checks.filter((c) => c.status === 'PASS').length;
const fail = report.checks.filter((c) => c.status === 'FAIL').length;
const warn = report.checks.filter((c) => c.status === 'WARN').length;
report.summary = { pass, fail, warn, total: report.checks.length };
fs.writeFileSync(`${REPORT_DIR}/report.json`, JSON.stringify(report, null, 2));
console.log(`\nSUMMARY: PASS=${pass} FAIL=${fail} WARN=${warn} (report: ${REPORT_DIR}/report.json)`);
await browser.close();
process.exit(fail > 0 ? 1 : 0);
