// Phase 5 Task 8 — public-storefront browser QA for the mobile Sticky
// Add-to-Cart (SATC) plus PDT / PDTX regression checks. Drives the real
// published tenant PDP at mobile viewports (390x844 primary, 360x800 narrow)
// and a desktop viewport (for the desktop-absence check). Records per-variant
// geometry, proves no content obscuration at max scroll, and writes a
// machine-readable JSON report + screenshots.
//
// One invocation tests ONE published bottom-nav variant (env QA_NAV_IDENTITY,
// purely for labelling the report — the runner reads whatever the live
// storefront currently publishes). The orchestrator (run_task8_all_variants.sh)
// republishes each registered variant, then runs this once per variant, so the
// committed evidence covers every nav presentation + the hidden/absent case.
import fs from 'node:fs';
import process from 'node:process';
import { chromium } from 'playwright-core';

const HOST = process.env.QA_HOST || 'rastisi-fashion-test.rastisi.localhost';
const PORT = process.env.QA_PORT || '8817';
const BASE = process.env.QA_BASE_URL || `http://${HOST}:${PORT}`;
const PDP_PATH = process.env.QA_PDP_PATH || '/products/accessory-scarf-%D8%A8%D8%B1%D8%AF%DB%8C%D8%A7-4/'; // in-stock simple
const NAV_LABEL = process.env.QA_NAV_IDENTITY || 'unknown';
const REPORT_DIR = process.env.QA_REPORT_DIR || '/tmp/task8_qa';
fs.mkdirSync(REPORT_DIR, { recursive: true });

const MOBILE = [
  { name: 'mobile-390', width: 390, height: 844 },
  { name: 'mobile-360', width: 360, height: 800 },
];
const DESKTOP = { name: 'desktop-1440', width: 1440, height: 900 };

const report = {
  host: HOST, base: BASE, pdp: PDP_PATH, nav_identity_expected: NAV_LABEL,
  started_at: new Date().toISOString(), checks: [], geometry: [], console_errors: [],
};
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
  const cta = page.locator('.pdp-actions .btn-primary').first();
  record('cta:visible-on-desktop', await cta.isVisible().catch(() => false) ? 'PASS' : 'FAIL');
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

  const inflow = page.locator('.pdp-actions .btn-primary').first();
  record(`cta:inflow-present:${vp.name}`, await inflow.count() > 0 ? 'PASS' : 'FAIL');

  // Canonical form wiring: SATC button is a plain submit INSIDE the one
  // cart:add form; no form= coupling; one cart:add form; one quantity owner.
  const wire = await page.evaluate(() => {
    const btn = document.querySelector('.pdp-satc-btn');
    const cartForms = [...document.querySelectorAll('form[hx-post]')].filter((f) => /\/cart\/add\//.test(f.getAttribute('hx-post') || ''));
    const insideForm = !!(btn && btn.closest('form') && cartForms.includes(btn.closest('form')));
    const qtyInputs = document.querySelectorAll('[name="quantity"]');
    return {
      insideCartForm: insideForm,
      hasFormAttr: !!(btn && btn.getAttribute('form')),
      cartAddFormCount: cartForms.length,
      quantityOwnerCount: qtyInputs.length,
      btnType: btn && btn.getAttribute('type'),
    };
  });
  record(`satc:inside-canonical-form:${vp.name}`, wire.insideCartForm && wire.btnType === 'submit' && !wire.hasFormAttr ? 'PASS' : 'FAIL', wire);
  record(`satc:one-cart-add-form:${vp.name}`, wire.cartAddFormCount === 1 ? 'PASS' : 'FAIL', { count: wire.cartAddFormCount });
  record(`satc:one-quantity-owner:${vp.name}`, wire.quantityOwnerCount === 1 ? 'PASS' : 'FAIL', { count: wire.quantityOwnerCount });

  // ---- GEOMETRY: SATC vs the active bottom nav (no overlap) ----
  const geo = await page.evaluate(() => {
    const satcEl = document.querySelector('.pdp-satc');
    const nav = document.querySelector('.gmn .gmn-bar') || document.querySelector('.gmn');
    const cartOrb = document.querySelector('.gmn .gmn-cart-orb'); // raised/luxury cart extends up
    const round = (n) => Math.round(n);
    const s = satcEl ? satcEl.getBoundingClientRect() : null;
    const g = nav ? nav.getBoundingClientRect() : null;
    const orb = cartOrb ? cartOrb.getBoundingClientRect() : null;
    const gmn = document.querySelector('.gmn');
    return {
      satc: s ? { top: round(s.top), bottom: round(s.bottom), height: round(s.height) } : null,
      nav: g ? { top: round(g.top), bottom: round(g.bottom), height: round(g.height) } : null,
      navOrbTop: orb ? round(orb.top) : null,
      navIdentity: gmn ? gmn.getAttribute('data-mobile-nav') : null,
      innerHeight: window.innerHeight,
      satcZ: satcEl ? getComputedStyle(satcEl).zIndex : null,
      clearance: getComputedStyle(document.documentElement).getPropertyValue('--gmn-clearance').trim(),
    };
  });
  report.geometry.push({ viewport: vp.name, ...geo });

  if (geo.nav) {
    // The highest painted top of the nav stack (bar OR the raised cart orb).
    const navTop = geo.navOrbTop != null ? Math.min(geo.nav.top, geo.navOrbTop) : geo.nav.top;
    record(`satc:no-bottom-nav-overlap:${vp.name}`, geo.satc.bottom <= navTop + 2 ? 'PASS' : 'FAIL',
      { satcBottom: geo.satc.bottom, navTop, navIdentity: geo.navIdentity });
  } else {
    // No nav rendered: SATC must hug the safe area, NOT float ~88px up.
    record(`satc:no-bottom-nav-overlap:${vp.name}`, 'PASS', { note: 'no bottom nav rendered', geo });
    record(`satc:hugs-bottom-when-nav-absent:${vp.name}`,
      geo.satc && (geo.innerHeight - geo.satc.bottom) <= 24 ? 'PASS' : 'FAIL',
      { gapFromBottom: geo.satc ? geo.innerHeight - geo.satc.bottom : null });
  }
  record(`satc:z-below-overlays:${vp.name}`, Number(geo.satcZ) < 100 ? 'PASS' : 'FAIL', { z: geo.satcZ });

  // Label + disabled agree with the canonical CTA.
  const labels = await page.evaluate(() => {
    const cta = document.querySelector('.pdp-actions .btn-primary span:last-child');
    const s = document.querySelector('.pdp-satc-btn span:last-child');
    return { cta: cta && cta.textContent.trim(), satc: s && s.textContent.trim() };
  });
  record(`satc:label-agrees-with-cta:${vp.name}`, labels.cta && labels.satc && labels.cta === labels.satc ? 'PASS' : 'WARN', labels);
  const dis = await page.evaluate(() => {
    const cta = document.querySelector('.pdp-actions .btn-primary');
    const s = document.querySelector('.pdp-satc-btn');
    return { ctaDisabled: !!(cta && cta.disabled), satcDisabled: !!(s && s.disabled) };
  });
  record(`satc:disabled-agrees-with-cta:${vp.name}`, dis.ctaDisabled === dis.satcDisabled ? 'PASS' : 'FAIL', dis);

  // QUANTITY: bump main stepper to 3 → the single quantity input reads 3.
  const plus = page.locator('.qty .stepper button').last();
  if (await plus.count()) {
    await plus.click(); await plus.click();
    await page.waitForTimeout(150);
    const qtyVal = await page.evaluate(() => { const q = document.querySelector('[name="quantity"]'); return q ? q.value : null; });
    record(`satc:shares-single-quantity=3:${vp.name}`, qtyVal === '3' ? 'PASS' : 'FAIL', { quantity: qtyVal });
  }

  // ---- NO CONTENT OBSCURATION at max scroll (IMPORTANT-3) ----
  // Scroll to the very bottom and prove the LAST meaningful PDP content (the
  // review form / last accordion panel) can be brought fully above the fixed
  // SATC top edge — i.e. it is reachable, not permanently hidden behind SATC.
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(400);
  const obsc = await page.evaluate(() => {
    const round = (n) => Math.round(n);
    const satcEl = document.querySelector('.pdp-satc');
    const satcTop = satcEl ? satcEl.getBoundingClientRect().top : window.innerHeight;
    // Candidate "final content" anchors present on a PDP.
    const anchors = [
      '#review-form-container', '.review-form', '.pdp-tabs',
      '.related-products', '.guarantee',
    ];
    let last = null;
    for (const sel of anchors) {
      const el = document.querySelector(sel);
      if (el) { const r = el.getBoundingClientRect(); last = { sel, top: round(r.top), bottom: round(r.bottom) }; }
    }
    return {
      satcTop: round(satcTop),
      innerHeight: window.innerHeight,
      finalContent: last,
      docScrollTop: round(window.scrollY),
      maxScroll: round(document.body.scrollHeight - window.innerHeight),
    };
  });
  report.geometry.push({ viewport: vp.name, obscuration: obsc });
  // Proof: at max scroll the final content's TOP is above the SATC top edge
  // (i.e. its beginning is reachable in the viewport, not stuck under SATC).
  const finalReachable = obsc.finalContent && obsc.finalContent.top < obsc.satcTop;
  record(`content:final-reachable-above-satc:${vp.name}`, finalReachable ? 'PASS' : 'FAIL',
    { finalContent: obsc.finalContent, satcTop: obsc.satcTop });

  await page.screenshot({ path: `${REPORT_DIR}/pdp_${NAV_LABEL}_${vp.name}.png`, fullPage: false });

  // OVERLAY layering: open the mobile nav drawer; drawer must cover SATC.
  const burger = page.locator('[data-mobile-nav-toggle], .gh-burger, button[aria-label*="منو"], .mobile-nav-toggle').first();
  if (await burger.count()) {
    await page.evaluate(() => window.scrollTo(0, 0));
    await burger.click().catch(() => {});
    await page.waitForTimeout(350);
    const layering = await page.evaluate(() => {
      const z = (sel) => { const el = document.querySelector(sel); return el ? Number(getComputedStyle(el).zIndex) || 0 : null; };
      return { drawerZ: z('.mobile-nav-drawer'), backdropZ: z('.mobile-drawer-backdrop'), satcZ: z('.pdp-satc') };
    });
    const covers = layering.satcZ != null && layering.drawerZ != null && layering.drawerZ > layering.satcZ;
    record(`overlay:drawer-covers-satc:${vp.name}`, covers ? 'PASS' : 'WARN', layering);
  } else {
    record(`overlay:drawer-covers-satc:${vp.name}`, 'WARN', { note: 'no burger/drawer toggle on this store' });
  }

  await ctx.close();
}

report.finished_at = new Date().toISOString();
const pass = report.checks.filter((c) => c.status === 'PASS').length;
const fail = report.checks.filter((c) => c.status === 'FAIL').length;
const warn = report.checks.filter((c) => c.status === 'WARN').length;
report.summary = { pass, fail, warn, total: report.checks.length };
const out = `${REPORT_DIR}/report_${NAV_LABEL}.json`;
fs.writeFileSync(out, JSON.stringify(report, null, 2));
console.log(`\n[${NAV_LABEL}] SUMMARY: PASS=${pass} FAIL=${fail} WARN=${warn} (report: ${out})`);
await browser.close();
process.exit(fail > 0 ? 1 : 0);
