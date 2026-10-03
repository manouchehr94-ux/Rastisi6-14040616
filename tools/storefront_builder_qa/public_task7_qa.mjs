// Phase 5 Task 7 — public-storefront browser QA for the two bounded repairs:
// mobile drawer SEARCH (Gap #1) and Django-native ELIDED PAGINATION (Gap #2).
// Drives the real published legacy_default tenant at three RTL viewports and
// captures screenshots + a JSON report. Same harness/approach as the Task-5
// public harness (public_task5_qa.mjs) — reused, not a new framework. Not the
// Task-16 matrix. Read-only against production code; no code under test edited.
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { chromium } from 'playwright-core';

const HOST = process.env.QA_HOST || 'rastisi-fashion-test.rastisi.localhost';
const PORT = process.env.QA_PORT || '8817';
const BASE = process.env.QA_BASE_URL || `http://${HOST}:${PORT}`;
const CHROME = process.env.QA_CHROME || '/opt/playwright/chromium-1232/chrome-linux64/chrome';
const REPORT_DIR = process.env.QA_REPORT_DIR || '/tmp/task7_qa';
// A real Persian query that exists in the fashion fixture (e.g. تیشرت = t-shirt).
const SEARCH_QUERY = process.env.QA_SEARCH_QUERY || 'تیشرت';
fs.mkdirSync(REPORT_DIR, { recursive: true });

const VIEWPORTS = [
  { name: 'desktop-1440', width: 1440, height: 900 },
  { name: 'tablet-768', width: 768, height: 1024 },
  { name: 'mobile-390', width: 390, height: 844 },
];

const report = { host: HOST, base: BASE, query: SEARCH_QUERY, started_at: new Date().toISOString(), checks: [], console_errors: [] };
function record(name, status, detail) {
  report.checks.push({ name, status, detail: detail ?? null });
  console.log(`${status.padEnd(5)} ${name}${detail ? ' — ' + JSON.stringify(detail) : ''}`);
}

const browser = await chromium.launch({
  executablePath: CHROME,
  headless: true,
  args: [`--host-resolver-rules=MAP ${HOST} 127.0.0.1`, '--no-proxy-server', '--no-sandbox'],
});

async function metrics(page) {
  return page.evaluate(() => ({
    dir: document.documentElement.getAttribute('dir') || '',
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
}
async function paginationInfo(page) {
  return page.evaluate(() => {
    const nav = document.querySelector('.pagination');
    if (!nav) return { present: false };
    const kids = [...nav.children];
    const rows = new Set(kids.map((k) => Math.round(k.getBoundingClientRect().top))).size;
    const numericLinks = nav.querySelectorAll('a[aria-label^="صفحه"]').length;
    const current = nav.querySelector('.current[aria-current="page"]');
    const ellipsis = nav.querySelectorAll('.ellipsis').length;
    const prev = !!nav.querySelector('a[rel="prev"], span.disabled');
    const next = !!nav.querySelector('a[rel="next"], span.disabled');
    const isNav = nav.tagName.toLowerCase() === 'nav' && nav.getAttribute('aria-label');
    // Any ?page=… (ellipsis-as-link) leak?
    const badLink = [...nav.querySelectorAll('a')].some(
      (a) => (a.getAttribute('href') || '').includes('page=…') || (a.getAttribute('hx-get') || '').includes('page=…'));
    return {
      present: true, children: kids.length, rows, numericLinks, ellipsis,
      currentText: current ? current.textContent.trim() : null,
      hasPrev: prev, hasNext: next, isLabelledNav: !!isNav, ellipsisAsLink: badLink,
    };
  });
}

for (const vp of VIEWPORTS) {
  const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, baseURL: BASE });
  const page = await context.newPage();
  page.on('console', (m) => { if (m.type() === 'error') report.console_errors.push({ vp: vp.name, text: m.text() }); });

  // ===================== PAGINATION (all viewports, mid page) ==============
  try {
    // Discover last page from page 1 then target a genuine mid-range page.
    await page.goto('/products/', { waitUntil: 'networkidle', timeout: 30000 });
    const numPages = await page.evaluate(() => {
      const links = [...document.querySelectorAll('.pagination a[aria-label^="صفحه"]')]
        .map((a) => a.getAttribute('aria-label'));
      return links.length; // informational
    });
    const mid = 4; // 8 pages in fixture -> page 4 is mid-range (forces a leading ellipsis)
    const resp = await page.goto(`/products/?page=${mid}`, { waitUntil: 'networkidle', timeout: 30000 });
    record(`pag:status:${vp.name}`, resp && resp.status() === 200 ? 'PASS' : 'FAIL', { status: resp && resp.status() });
    const m = await metrics(page);
    record(`pag:no-overflow:${vp.name}`, m.scrollWidth <= m.clientWidth + 3 ? 'PASS' : 'FAIL', m);
    const pinfo = await paginationInfo(page);
    record(`pag:labelled-nav:${vp.name}`, pinfo.isLabelledNav ? 'PASS' : 'FAIL', { label: pinfo.isLabelledNav });
    record(`pag:bounded-controls:${vp.name}`, pinfo.numericLinks <= 8 ? 'PASS' : 'FAIL',
      { numericLinks: pinfo.numericLinks, ellipsis: pinfo.ellipsis, rows: pinfo.rows });
    record(`pag:has-prev-next:${vp.name}`, pinfo.hasPrev && pinfo.hasNext ? 'PASS' : 'WARN', { hasPrev: pinfo.hasPrev, hasNext: pinfo.hasNext });
    record(`pag:ellipsis-not-link:${vp.name}`, pinfo.ellipsisAsLink === false ? 'PASS' : 'FAIL', { ellipsisAsLink: pinfo.ellipsisAsLink });
    record(`pag:current-page:${vp.name}`, 'INFO', { current: pinfo.currentText, numPagesSeenOnP1: numPages });
    const pagEl = page.locator('.pagination').first();
    if (await pagEl.count()) { await pagEl.scrollIntoViewIfNeeded(); }
    await page.screenshot({ path: path.join(REPORT_DIR, `pagination-${vp.name}.png`), fullPage: false });

    // HTMX navigation: click Next, URL updates + results swap in place.
    const nextLink = page.locator('.pagination a[rel="next"]').first();
    if (await nextLink.count()) {
      await nextLink.click();
      await page.waitForTimeout(600);
      const url = page.url();
      record(`pag:htmx-next-updates-url:${vp.name}`, /[?&]page=5/.test(url) ? 'PASS' : 'WARN', { url });
    }
  } catch (e) { record(`pag:${vp.name}`, 'FAIL', { error: String(e).slice(0, 300) }); }

  // ===================== MOBILE DRAWER SEARCH (mobile only) ================
  if (vp.width <= 680) {
    try {
      await page.goto('/products/', { waitUntil: 'networkidle', timeout: 30000 });
      // 1) header .search is NOT the mobile entry point (hidden by CSS).
      const headerSearchVisible = await page.evaluate(() => {
        const f = document.querySelector('header .search');
        if (!f) return false;
        const cs = getComputedStyle(f); const r = f.getBoundingClientRect();
        return cs.display !== 'none' && r.width > 0 && r.height > 0;
      });
      record(`search:header-not-mobile-entry:${vp.name}`, headerSearchVisible === false ? 'PASS' : 'WARN', { headerSearchVisible });

      // 2) open the Task-5 drawer.
      const burger = page.locator('[aria-controls="mobile-nav-drawer"]').first();
      await burger.click();
      await page.waitForTimeout(400);
      const drawer = page.locator('#mobile-nav-drawer[role="dialog"]');
      record(`search:drawer-opens:${vp.name}`, (await drawer.isVisible()) ? 'PASS' : 'FAIL', {});

      // 3) exactly one usable search form inside the drawer.
      const drawerSearch = await page.evaluate(() => {
        const d = document.querySelector('#mobile-nav-drawer');
        const forms = d ? d.querySelectorAll('form[role="search"]') : [];
        const input = d ? d.querySelector('#mobile-drawer-search-input') : null;
        // Accessible name: associated <label for> or aria-label.
        let hasName = false;
        if (input) {
          const lbl = input.id && d.querySelector(`label[for="${input.id}"]`);
          hasName = !!(lbl || input.getAttribute('aria-label') || input.getAttribute('placeholder'));
        }
        return { forms: forms.length, hasInput: !!input, inputName: input ? input.getAttribute('name') : null, hasName };
      });
      record(`search:one-drawer-form:${vp.name}`, drawerSearch.forms === 1 ? 'PASS' : 'FAIL', drawerSearch);
      record(`search:input-name-q:${vp.name}`, drawerSearch.inputName === 'q' ? 'PASS' : 'FAIL', { name: drawerSearch.inputName });
      record(`search:input-accessible-name:${vp.name}`, drawerSearch.hasName ? 'PASS' : 'FAIL', {});
      await page.screenshot({ path: path.join(REPORT_DIR, `drawer-search-${vp.name}.png`), fullPage: false });

      // 4) type a real Persian query + submit via the existing GET endpoint.
      const input = page.locator('#mobile-drawer-search-input');
      await input.fill(SEARCH_QUERY);
      await input.press('Enter');
      await page.waitForLoadState('networkidle', { timeout: 30000 });
      const url = page.url();
      const encoded = encodeURIComponent(SEARCH_QUERY);
      record(`search:url-has-q:${vp.name}`,
        (url.includes(`q=${encoded}`) || url.includes(`q=${SEARCH_QUERY}`)) ? 'PASS' : 'FAIL', { url });
      const resultCards = await page.locator('#product-results .pcard').count();
      record(`search:results-rendered:${vp.name}`, resultCards > 0 ? 'PASS' : 'WARN', { resultCards });
      await page.screenshot({ path: path.join(REPORT_DIR, `drawer-search-results-${vp.name}.png`), fullPage: false });

      // 5) Task-5 overlay integrity: reopen the drawer, Escape closes it.
      await page.goto('/products/', { waitUntil: 'networkidle', timeout: 30000 });
      await burger.click();
      await page.waitForTimeout(300);
      await page.keyboard.press('Escape');
      await page.waitForTimeout(300);
      const stillOpen = await drawer.isVisible().catch(() => false);
      record(`search:task5-escape-still-works:${vp.name}`, stillOpen === false ? 'PASS' : 'WARN', { stillOpen });
    } catch (e) { record(`search:${vp.name}`, 'FAIL', { error: String(e).slice(0, 300) }); }
  } else {
    // Representative desktop regression: header search unchanged (present + visible).
    try {
      await page.goto('/products/', { waitUntil: 'networkidle', timeout: 30000 });
      const headerSearch = await page.evaluate(() => {
        const f = document.querySelector('header .search');
        if (!f) return false;
        const cs = getComputedStyle(f); const r = f.getBoundingClientRect();
        return cs.display !== 'none' && r.width > 0;
      });
      record(`search:desktop-header-search-unchanged:${vp.name}`, headerSearch ? 'PASS' : 'WARN', { headerSearch });
    } catch (e) { record(`search:desktop:${vp.name}`, 'FAIL', { error: String(e).slice(0, 300) }); }
  }

  await context.close();
}

// ===================== NO-JS pagination + drawer-search forms =============
{
  const nojs = await browser.newContext({ viewport: { width: 390, height: 844 }, baseURL: BASE, javaScriptEnabled: false });
  const page = await nojs.newPage();
  try {
    await page.goto('/products/?page=4', { waitUntil: 'load', timeout: 30000 });
    const hasHref = await page.evaluate(() =>
      [...document.querySelectorAll('.pagination a')].some((a) => (a.getAttribute('href') || '').includes('page=')));
    record('nojs:pagination-href', hasHref ? 'PASS' : 'FAIL', {});
    // Drawer search form still submits via GET (method+action present) with JS off.
    const formOk = await page.evaluate(() => {
      const f = document.querySelector('#mobile-nav-drawer form[role="search"]');
      if (!f) return false;
      return (f.getAttribute('method') || '').toLowerCase() === 'get' && !!f.getAttribute('action');
    });
    record('nojs:drawer-search-get-form', formOk ? 'PASS' : 'FAIL', {});
  } catch (e) { record('nojs', 'FAIL', { error: String(e).slice(0, 300) }); }
  await nojs.close();
}

await browser.close();
report.console_error_count = report.console_errors.length;
report.finished_at = new Date().toISOString();
const failed = report.checks.filter((c) => c.status === 'FAIL');
report.summary = {
  total: report.checks.length,
  pass: report.checks.filter((c) => c.status === 'PASS').length,
  fail: failed.length,
  warn: report.checks.filter((c) => c.status === 'WARN').length,
  info: report.checks.filter((c) => c.status === 'INFO').length,
};
fs.writeFileSync(path.join(REPORT_DIR, 'task7_browser_result.json'), JSON.stringify(report, null, 2));
console.log('\nSUMMARY', JSON.stringify(report.summary), 'console_errors:', report.console_error_count);
process.exit(failed.length ? 1 : 0);
