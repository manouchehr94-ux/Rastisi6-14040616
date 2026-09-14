// Phase 5 Task 5 — public-storefront browser QA for the six areas that ship
// user-visible markup: STRANS (hero transition), PDT (PDP tabs/accordion),
// MDR (mobile nav drawer), MODAL (product quick view), plus HDR/PDTX render
// health. Drives the real published tenant storefront at three RTL viewports
// and captures screenshots + a JSON report. Not the editor harness — this
// verifies the PUBLIC rendering contract of Task 5.
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { chromium } from 'playwright-core';

const HOST = process.env.QA_HOST || 'rastisi-fashion-test.rastisi.localhost';
const PORT = process.env.QA_PORT || '8817';
const BASE = process.env.QA_BASE_URL || `http://${HOST}:${PORT}`;
const PDP_PATH = process.env.QA_PDP_PATH; // encoded product path
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

for (const vp of VIEWPORTS) {
  const context = await browser.newContext({
    viewport: { width: vp.width, height: vp.height },
    baseURL: BASE,
  });
  const page = await context.newPage();
  page.on('console', (m) => { if (m.type() === 'error') report.console_errors.push({ vp: vp.name, text: m.text() }); });

  // ---- HOME (STRANS hero + MODAL quick view triggers on product cards) ----
  try {
    const resp = await page.goto('/', { waitUntil: 'networkidle', timeout: 30000 });
    record(`home:status:${vp.name}`, resp && resp.status() === 200 ? 'PASS' : 'FAIL', { status: resp && resp.status() });
    const m = await overflowMetrics(page);
    record(`home:no-overflow:${vp.name}`, m.scrollWidth <= m.clientWidth + 3 ? 'PASS' : 'FAIL', m);

    // STRANS: hero transition attribute present on any hero slider body.
    const heroTransition = await page.locator('[data-hero-transition]').count();
    record(`home:hero-transition-attr:${vp.name}`, heroTransition > 0 ? 'PASS' : 'WARN', { count: heroTransition });

    // MODAL: quick view trigger + dialog rendered server-side inside cards.
    const qvTriggers = await page.locator('.pcard-qv-trigger, [aria-haspopup="dialog"]').count();
    const qvDialogs = await page.locator('.pcard-qv-dialog[role="dialog"]').count();
    record(`home:quickview-present:${vp.name}`, qvTriggers > 0 && qvDialogs > 0 ? 'PASS' : 'WARN', { triggers: qvTriggers, dialogs: qvDialogs });

    // Open the first quick view and verify the dialog becomes visible + traps within viewport.
    if (qvTriggers > 0) {
      const trigger = page.locator('.pcard-qv-trigger').first();
      await trigger.evaluate((el) => el.click());
      await page.waitForTimeout(300);
      const dialogVisible = await page.locator('.pcard-qv-dialog[role="dialog"]').first().isVisible().catch(() => false);
      record(`home:quickview-opens:${vp.name}`, dialogVisible ? 'PASS' : 'WARN', { dialogVisible });
      await page.screenshot({ path: path.join(REPORT_DIR, `home-quickview-${vp.name}.png`), fullPage: false });
      // Escape closes it (shared overlay primitive contract).
      await page.keyboard.press('Escape');
      await page.waitForTimeout(250);
      const afterEsc = await page.locator('.pcard-qv-dialog[role="dialog"]').first().isVisible().catch(() => false);
      record(`home:quickview-escape-closes:${vp.name}`, afterEsc === false ? 'PASS' : 'WARN', { stillVisible: afterEsc });
    }
    await page.screenshot({ path: path.join(REPORT_DIR, `home-${vp.name}.png`), fullPage: false });
  } catch (e) {
    record(`home:${vp.name}`, 'FAIL', { error: String(e).slice(0, 300) });
  }

  // ---- MDR: mobile nav drawer (mobile viewport only) ----
  if (vp.width <= 680) {
    try {
      await page.goto('/', { waitUntil: 'networkidle', timeout: 30000 });
      const burger = page.locator('[aria-controls="mobile-nav-drawer"]').first();
      const hasBurger = await burger.count();
      record(`mdr:burger-present:${vp.name}`, hasBurger > 0 ? 'PASS' : 'WARN', { count: hasBurger });
      if (hasBurger > 0) {
        await burger.click();
        await page.waitForTimeout(300);
        const drawerVisible = await page.locator('#mobile-nav-drawer[role="dialog"]').isVisible().catch(() => false);
        record(`mdr:drawer-opens:${vp.name}`, drawerVisible ? 'PASS' : 'WARN', { drawerVisible });
        await page.screenshot({ path: path.join(REPORT_DIR, `mdr-drawer-${vp.name}.png`), fullPage: false });
        await page.keyboard.press('Escape');
        await page.waitForTimeout(250);
        const afterEsc = await page.locator('#mobile-nav-drawer[role="dialog"]').isVisible().catch(() => false);
        record(`mdr:drawer-escape-closes:${vp.name}`, afterEsc === false ? 'PASS' : 'WARN', { stillVisible: afterEsc });
      }
    } catch (e) {
      record(`mdr:${vp.name}`, 'FAIL', { error: String(e).slice(0, 300) });
    }
  }

  // ---- PDT: PDP tabs (desktop) / accordion (mobile) ----
  if (PDP_PATH) {
    try {
      const resp = await page.goto(PDP_PATH, { waitUntil: 'networkidle', timeout: 30000 });
      record(`pdp:status:${vp.name}`, resp && resp.status() === 200 ? 'PASS' : 'FAIL', { status: resp && resp.status() });
      const m = await overflowMetrics(page);
      record(`pdp:no-overflow:${vp.name}`, m.scrollWidth <= m.clientWidth + 3 ? 'PASS' : 'FAIL', m);
      const tabs = await page.locator('[role="tablist"] [role="tab"]').count();
      const panels = await page.locator('[role="tabpanel"]').count();
      record(`pdp:tabs-present:${vp.name}`, tabs > 0 && panels > 0 ? 'PASS' : 'WARN', { tabs, panels });
      await page.screenshot({ path: path.join(REPORT_DIR, `pdp-${vp.name}.png`), fullPage: false });
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
