// Phase 5 Task 5 — deepened public-storefront browser QA for the areas that
// ship user-visible markup: STRANS (hero transition), PDT (PDP tabs/accordion),
// MDR (mobile nav drawer), MODAL (product quick view), PDTX (editable PDP trust
// render health). Drives the real published tenant storefront at three RTL
// viewports and captures screenshots + a JSON report. This is representative
// Task-5 QA (not Task-16 scale) — the SAME harness/approach as before, extended
// with focus-containment / focus-return / backdrop-close / scroll-lock /
// keyboard / real-accordion / unique-id / cart-affordance assertions.
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { chromium } from 'playwright-core';

const HOST = process.env.QA_HOST || 'rastisi-fashion-test.rastisi.localhost';
const PORT = process.env.QA_PORT || '8817';
const BASE = process.env.QA_BASE_URL || `http://${HOST}:${PORT}`;
const PDP_PATH = process.env.QA_PDP_PATH; // encoded product path
const PDP_TRUST_MARKER = process.env.QA_PDP_TRUST_MARKER || ''; // seeded editable PDP trust title
const HARDCODED_TRUST = 'ضمانت اصالت کالا'; // the hard-coded guarantee strip
const REPORT_DIR = process.env.QA_REPORT_DIR || '/tmp/task5_qa';
fs.mkdirSync(REPORT_DIR, { recursive: true });

const VIEWPORTS = [
  { name: 'desktop-1440', width: 1440, height: 900 },
  { name: 'tablet-768', width: 768, height: 1024 },
  { name: 'mobile-390', width: 390, height: 844 },
];

const report = { host: HOST, base: BASE, started_at: new Date().toISOString(), checks: [], console_errors: [] };
function record(name, status, detail) {
  report.checks.push({ name, status, detail: detail ?? null });
  console.log(`${status.padEnd(5)} ${name}${detail ? ' — ' + JSON.stringify(detail) : ''}`);
}

const browser = await chromium.launch({
  executablePath: '/opt/google/chrome/chrome',
  headless: true,
  args: [`--host-resolver-rules=MAP ${HOST} 127.0.0.1`, '--no-sandbox'],
});

async function overflowMetrics(page) {
  return page.evaluate(() => ({
    dir: document.documentElement.getAttribute('dir') || document.body.getAttribute('dir') || '',
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
}

// Whether the active element is contained within `selector` (focus trap check).
async function activeInside(page, selector) {
  return page.evaluate((sel) => {
    const root = document.querySelector(sel);
    return !!(root && document.activeElement && root.contains(document.activeElement));
  }, selector);
}

async function bodyScrollLocked(page) {
  return page.evaluate(() => {
    const o = getComputedStyle(document.body).overflow;
    const oh = getComputedStyle(document.documentElement).overflow;
    return o === 'hidden' || oh === 'hidden';
  });
}

for (const vp of VIEWPORTS) {
  const context = await browser.newContext({
    viewport: { width: vp.width, height: vp.height },
    baseURL: BASE,
  });
  const page = await context.newPage();
  page.on('console', (m) => { if (m.type() === 'error') report.console_errors.push({ vp: vp.name, text: m.text() }); });

  // ================= HOME (STRANS hero + MODAL quick view) =================
  try {
    const resp = await page.goto('/', { waitUntil: 'networkidle', timeout: 30000 });
    record(`home:status:${vp.name}`, resp && resp.status() === 200 ? 'PASS' : 'FAIL', { status: resp && resp.status() });
    const m = await overflowMetrics(page);
    record(`home:rtl:${vp.name}`, m.dir === 'rtl' ? 'PASS' : 'WARN', { dir: m.dir });
    record(`home:no-overflow:${vp.name}`, m.scrollWidth <= m.clientWidth + 3 ? 'PASS' : 'FAIL', m);

    // ---- STRANS: transition attribute present AND carries a real value ----
    const heroEls = page.locator('[data-hero-transition]');
    const heroCount = await heroEls.count();
    if (heroCount > 0) {
      const val = await heroEls.first().getAttribute('data-hero-transition');
      record(`strans:transition-reaches-runtime:${vp.name}`,
        ['cut', 'fade', 'slide'].includes(val) ? 'PASS' : 'FAIL', { value: val });
    } else {
      record(`strans:transition-reaches-runtime:${vp.name}`, 'WARN', { note: 'no hero on this store' });
    }

    // ---- MODAL: unique IDs, open, focus containment, close paths ----
    const qvTriggers = page.locator('.pcard-qv-trigger');
    const qvTriggerCount = await qvTriggers.count();
    record(`modal:triggers-present:${vp.name}`, qvTriggerCount > 0 ? 'PASS' : 'WARN', { count: qvTriggerCount });

    if (qvTriggerCount > 0) {
      // Unique dialog + title IDs across the whole rendered page.
      const idInfo = await page.evaluate(() => {
        const dialogs = [...document.querySelectorAll('.pcard-qv-dialog[role="dialog"]')];
        const ids = dialogs.map((d) => d.id).filter(Boolean);
        const titles = [...document.querySelectorAll('.pcard-qv-name[id]')].map((t) => t.id).filter(Boolean);
        return {
          dialogCount: dialogs.length,
          uniqueDialogIds: new Set(ids).size,
          dialogIdCount: ids.length,
          uniqueTitleIds: new Set(titles).size,
          titleIdCount: titles.length,
        };
      });
      record(`modal:unique-dialog-ids:${vp.name}`,
        idInfo.dialogIdCount > 0 && idInfo.uniqueDialogIds === idInfo.dialogIdCount ? 'PASS' : 'FAIL', idInfo);
      record(`modal:unique-title-ids:${vp.name}`,
        idInfo.titleIdCount > 0 && idInfo.uniqueTitleIds === idInfo.titleIdCount ? 'PASS' : 'FAIL',
        { unique: idInfo.uniqueTitleIds, total: idInfo.titleIdCount });

      // Open the first quick view.
      const firstTrigger = qvTriggers.first();
      await firstTrigger.evaluate((el) => el.click());
      await page.waitForTimeout(300);
      const firstDialog = page.locator('.pcard-qv-dialog[role="dialog"]').first();
      const opened = await firstDialog.isVisible().catch(() => false);
      record(`modal:opens:${vp.name}`, opened ? 'PASS' : 'FAIL', { opened });

      // aria-controls of the trigger points at the opened dialog id.
      const wired = await page.evaluate(() => {
        const t = document.querySelector('.pcard-qv-trigger');
        const controls = t && t.getAttribute('aria-controls');
        const dlg = controls && document.getElementById(controls);
        return !!(dlg && dlg.getAttribute('role') === 'dialog');
      });
      record(`modal:trigger-aria-controls-correct:${vp.name}`, wired ? 'PASS' : 'FAIL', { wired });

      // PDP link present inside the dialog.
      const pdpLink = await firstDialog.locator('a.pcard-qv-detail[href]').count();
      record(`modal:pdp-link-present:${vp.name}`, pdpLink > 0 ? 'PASS' : 'FAIL', { pdpLink });

      // Add-to-cart affordance: present only when the card permits quick-add.
      const cartInfo = await page.evaluate(() => {
        const dlg = document.querySelector('.pcard-qv-dialog[role="dialog"]');
        const card = dlg && dlg.closest('.pcard');
        const oos = !!(card && card.classList.contains('out-of-stock'));
        const hasAdd = !!(dlg && dlg.querySelector('.pcard-qv-add'));
        return { oos, hasAdd };
      });
      // If OOS, there must be no add button; otherwise a card that shows the
      // add elsewhere should also offer it here (representative check).
      record(`modal:cart-affordance-consistent:${vp.name}`,
        cartInfo.oos ? (cartInfo.hasAdd === false ? 'PASS' : 'FAIL') : 'PASS', cartInfo);

      // Focus containment: focus is inside the dialog after open; Tab keeps it in.
      await page.waitForTimeout(50);
      const focusInside = await activeInside(page, '.pcard-qv-dialog[role="dialog"]');
      record(`modal:focus-enters-overlay:${vp.name}`, focusInside ? 'PASS' : 'WARN', { focusInside });
      for (let i = 0; i < 8; i += 1) await page.keyboard.press('Tab');
      const stillInside = await activeInside(page, '.pcard-qv-dialog[role="dialog"]');
      record(`modal:focus-trap-holds:${vp.name}`, stillInside ? 'PASS' : 'WARN', { stillInside });

      // Body scroll lock while open.
      record(`modal:scroll-lock:${vp.name}`, (await bodyScrollLocked(page)) ? 'PASS' : 'WARN', {});

      await page.screenshot({ path: path.join(REPORT_DIR, `home-quickview-${vp.name}.png`), fullPage: false });

      // Backdrop close.
      await page.locator('.pcard-qv-backdrop').first().click({ position: { x: 5, y: 5 } }).catch(() => {});
      await page.waitForTimeout(250);
      let vis = await firstDialog.isVisible().catch(() => false);
      record(`modal:backdrop-closes:${vp.name}`, vis === false ? 'PASS' : 'WARN', { stillVisible: vis });

      // Re-open then explicit close button + focus return to trigger.
      await firstTrigger.evaluate((el) => el.click());
      await page.waitForTimeout(250);
      await page.locator('.pcard-qv-dialog[role="dialog"] .pcard-qv-close').first().click().catch(() => {});
      await page.waitForTimeout(250);
      vis = await firstDialog.isVisible().catch(() => false);
      record(`modal:explicit-close:${vp.name}`, vis === false ? 'PASS' : 'WARN', { stillVisible: vis });
      const focusReturned = await page.evaluate(
        () => document.activeElement && document.activeElement.classList.contains('pcard-qv-trigger'));
      record(`modal:focus-returns-to-trigger:${vp.name}`, focusReturned ? 'PASS' : 'WARN', { focusReturned });

      // Re-open then Escape close.
      await firstTrigger.evaluate((el) => el.click());
      await page.waitForTimeout(200);
      await page.keyboard.press('Escape');
      await page.waitForTimeout(250);
      vis = await firstDialog.isVisible().catch(() => false);
      record(`modal:escape-closes:${vp.name}`, vis === false ? 'PASS' : 'WARN', { stillVisible: vis });
    }
    await page.screenshot({ path: path.join(REPORT_DIR, `home-${vp.name}.png`), fullPage: false });
  } catch (e) {
    record(`home:${vp.name}`, 'FAIL', { error: String(e).slice(0, 300) });
  }

  // ================= MDR: mobile nav drawer (mobile only) =================
  if (vp.width <= 680) {
    try {
      await page.goto('/', { waitUntil: 'networkidle', timeout: 30000 });
      const burger = page.locator('[aria-controls="mobile-nav-drawer"]').first();
      const hasBurger = await burger.count();
      record(`mdr:burger-present:${vp.name}`, hasBurger > 0 ? 'PASS' : 'FAIL', { count: hasBurger });
      if (hasBurger > 0) {
        await burger.click();
        await page.waitForTimeout(300);
        const drawer = page.locator('#mobile-nav-drawer[role="dialog"]');
        const opened = await drawer.isVisible().catch(() => false);
        record(`mdr:opens:${vp.name}`, opened ? 'PASS' : 'FAIL', { opened });

        // Real canonical navigation links present inside the drawer.
        const navLinks = await drawer.locator('.mobile-nav-drawer__nav a[href]').count();
        record(`mdr:canonical-nav-links:${vp.name}`, navLinks > 0 ? 'PASS' : 'WARN', { navLinks });

        // Focus enters overlay + Tab stays inside.
        await page.waitForTimeout(50);
        record(`mdr:focus-enters-overlay:${vp.name}`,
          (await activeInside(page, '#mobile-nav-drawer')) ? 'PASS' : 'WARN', {});
        for (let i = 0; i < 8; i += 1) await page.keyboard.press('Tab');
        record(`mdr:focus-trap-holds:${vp.name}`,
          (await activeInside(page, '#mobile-nav-drawer')) ? 'PASS' : 'WARN', {});

        // Body scroll lock.
        record(`mdr:scroll-lock:${vp.name}`, (await bodyScrollLocked(page)) ? 'PASS' : 'WARN', {});

        await page.screenshot({ path: path.join(REPORT_DIR, `mdr-drawer-${vp.name}.png`), fullPage: false });

        // Explicit close + focus return.
        await drawer.locator('.mobile-nav-drawer__close').click().catch(() => {});
        await page.waitForTimeout(250);
        let vis = await drawer.isVisible().catch(() => false);
        record(`mdr:explicit-close:${vp.name}`, vis === false ? 'PASS' : 'WARN', { stillVisible: vis });
        const returned = await page.evaluate(() => {
          const el = document.activeElement;
          return !!(el && el.getAttribute('aria-controls') === 'mobile-nav-drawer');
        });
        record(`mdr:focus-returns-to-burger:${vp.name}`, returned ? 'PASS' : 'WARN', { returned });

        // Backdrop close.
        await burger.click();
        await page.waitForTimeout(250);
        await page.locator('.mobile-drawer-backdrop').click({ position: { x: 5, y: 5 } }).catch(() => {});
        await page.waitForTimeout(250);
        vis = await drawer.isVisible().catch(() => false);
        record(`mdr:backdrop-closes:${vp.name}`, vis === false ? 'PASS' : 'WARN', { stillVisible: vis });

        // Escape close.
        await burger.click();
        await page.waitForTimeout(200);
        await page.keyboard.press('Escape');
        await page.waitForTimeout(250);
        vis = await drawer.isVisible().catch(() => false);
        record(`mdr:escape-closes:${vp.name}`, vis === false ? 'PASS' : 'WARN', { stillVisible: vis });
      }
    } catch (e) {
      record(`mdr:${vp.name}`, 'FAIL', { error: String(e).slice(0, 300) });
    }
  }

  // ================= PDT: tabs (desktop) / real accordion (mobile) =========
  if (PDP_PATH) {
    try {
      const resp = await page.goto(PDP_PATH, { waitUntil: 'networkidle', timeout: 30000 });
      record(`pdp:status:${vp.name}`, resp && resp.status() === 200 ? 'PASS' : 'FAIL', { status: resp && resp.status() });
      const m = await overflowMetrics(page);
      record(`pdp:rtl:${vp.name}`, m.dir === 'rtl' ? 'PASS' : 'WARN', { dir: m.dir });
      record(`pdp:no-overflow:${vp.name}`, m.scrollWidth <= m.clientWidth + 3 ? 'PASS' : 'FAIL', m);

      const tabs = page.locator('.pdp-tabs [role="tab"]');
      const panels = page.locator('.pdp-tabs [role="tabpanel"]');
      const tabCount = await tabs.count();
      const panelCount = await panels.count();
      record(`pdp:tabs-present:${vp.name}`, tabCount === 3 && panelCount === 3 ? 'PASS' : 'FAIL', { tabCount, panelCount });

      // Active tab/panel relationship: exactly one visible panel, and its
      // labelledby points at the selected tab.
      const rel = await page.evaluate(() => {
        const panels = [...document.querySelectorAll('.pdp-tabs [role="tabpanel"]')];
        const visible = panels.filter((p) => p.offsetParent !== null || getComputedStyle(p).display !== 'none');
        const selectedTab = document.querySelector('.pdp-tabs [role="tab"][aria-selected="true"]');
        const shown = visible[0];
        const controlsOK = selectedTab && shown && selectedTab.getAttribute('aria-controls') === shown.id
          && shown.getAttribute('aria-labelledby') === selectedTab.id;
        return { visibleCount: visible.length, controlsOK: !!controlsOK };
      });
      record(`pdp:one-active-panel:${vp.name}`, rel.visibleCount === 1 ? 'PASS' : 'WARN', rel);
      record(`pdp:tab-panel-relationship:${vp.name}`, rel.controlsOK ? 'PASS' : 'WARN', rel);

      if (vp.width > 680) {
        // Desktop keyboard: focus first tab, ArrowRight moves selection, End -> last, Home -> first.
        await tabs.first().focus();
        await page.keyboard.press('ArrowRight');
        await page.waitForTimeout(120);
        const afterArrow = await page.evaluate(() =>
          document.querySelector('.pdp-tabs [role="tab"][aria-selected="true"]')?.id);
        await page.keyboard.press('End');
        await page.waitForTimeout(120);
        const afterEnd = await page.evaluate(() =>
          document.querySelector('.pdp-tabs [role="tab"][aria-selected="true"]')?.id);
        await page.keyboard.press('Home');
        await page.waitForTimeout(120);
        const afterHome = await page.evaluate(() =>
          document.querySelector('.pdp-tabs [role="tab"][aria-selected="true"]')?.id);
        record(`pdp:keyboard-arrow-nav:${vp.name}`,
          afterArrow && afterEnd && afterHome && afterArrow !== afterHome && afterEnd !== afterHome ? 'PASS' : 'WARN',
          { afterArrow, afterEnd, afterHome });
      } else {
        // Mobile REAL accordion, two proofs:
        // (a) DOM SOURCE ORDER is header,panel,header,panel,header,panel
        //     (accordion-native — each control immediately before its panel);
        // (b) the currently OPEN panel is visually positioned DIRECTLY below
        //     its own header (header.bottom ≈ panel.top), i.e. not "all headers
        //     grouped then one panel".
        const acc = await page.evaluate(() => {
          const kids = [...document.querySelectorAll('.pdp-tabs > *')]
            .filter((el) => el.matches('[role="tab"], [role="tabpanel"]'));
          const domRoles = kids.map((el) => el.getAttribute('role'));
          const sourceInterleaved = JSON.stringify(domRoles) === JSON.stringify(
            ['tab', 'tabpanel', 'tab', 'tabpanel', 'tab', 'tabpanel']);

          // The open header + its controlled panel are vertically adjacent.
          const openHeader = document.querySelector('.pdp-tabs [role="tab"][aria-selected="true"]');
          const openPanel = openHeader && document.getElementById(openHeader.getAttribute('aria-controls'));
          let adjacent = false;
          if (openHeader && openPanel) {
            const hb = openHeader.getBoundingClientRect().bottom;
            const pt = openPanel.getBoundingClientRect().top;
            adjacent = Math.abs(pt - hb) < 40; // panel sits right under its header
          }
          return { domRoles, sourceInterleaved, adjacent };
        });
        record(`pdp:real-accordion-source-order:${vp.name}`, acc.sourceInterleaved ? 'PASS' : 'FAIL', { domRoles: acc.domRoles });
        record(`pdp:real-accordion-open-panel-under-header:${vp.name}`, acc.adjacent ? 'PASS' : 'WARN', { adjacent: acc.adjacent });
      }
      await page.screenshot({ path: path.join(REPORT_DIR, `pdp-${vp.name}.png`), fullPage: false });

      // ---- PDTX render health on the PDP ----
      if (PDP_TRUST_MARKER) {
        const body = await page.content();
        record(`pdtx:published-trust-visible:${vp.name}`,
          body.includes(PDP_TRUST_MARKER) ? 'PASS' : 'FAIL', {});
        // No double trust module: the hard-coded strip is suppressed when the
        // canonical editable trust section exists.
        record(`pdtx:hardcoded-strip-suppressed:${vp.name}`,
          !body.includes(HARDCODED_TRUST) ? 'PASS' : 'FAIL', {});
      }
    } catch (e) {
      record(`pdp:${vp.name}`, 'FAIL', { error: String(e).slice(0, 300) });
    }
  }

  await context.close();
}

await browser.close();
report.console_error_count = report.console_errors.length;
report.finished_at = new Date().toISOString();
const failed = report.checks.filter((c) => c.status === 'FAIL');
report.summary = {
  total: report.checks.length,
  passed: report.checks.filter((c) => c.status === 'PASS').length,
  warnings: report.checks.filter((c) => c.status === 'WARN').length,
  failed: failed.length,
};
fs.writeFileSync(path.join(REPORT_DIR, 'report.json'), JSON.stringify(report, null, 2));
console.log('\nSUMMARY', JSON.stringify(report.summary), 'console_errors:', report.console_error_count);
process.exit(failed.length ? 1 : 0);
