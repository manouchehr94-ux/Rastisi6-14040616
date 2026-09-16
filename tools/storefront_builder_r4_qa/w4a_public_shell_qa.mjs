// P5-W4A Public Storefront Shell Convergence — browser QA runner.
//
// Reuses the existing tools/storefront_builder_r4_qa conventions (same
// Chromium/playwright-core resolution as w3_design_lab_qa.mjs, session-cookie
// auth, PASS/FAIL result JSON) — no second harness. Drives the EXISTING
// public Wishlist (customers:wishlist) and CMS content (content:page-detail)
// routes, across the required viewports, in RTL.
//
// Usage: node w4a_public_shell_qa.mjs <manifest.json>
//   manifest: { origin, populated_session, empty_session, cms_slug, report_dir }

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { createRequire } from 'node:module';

function resolvePlaywrightCore() {
  const candidates = [
    new URL('../storefront_builder_qa/package.json', import.meta.url),
    '/opt/toolchains/.nvm/versions/node/v22.23.2/lib/node_modules/@playwright/mcp/node_modules/playwright-core/package.json',
    '/opt/node22/lib/node_modules/playwright/node_modules/playwright-core/package.json',
  ];
  const errors = [];
  for (const from of candidates) {
    try {
      return createRequire(from)('playwright-core');
    } catch (error) {
      errors.push(`${from}: ${error.message}`);
    }
  }
  throw new Error(`No usable playwright-core found. ${errors.join(' | ')}`);
}
const { chromium } = resolvePlaywrightCore();

function resolveChromePath() {
  const candidates = [
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
    '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
    '/opt/playwright/chromium-1232/chrome-linux64/chrome',
    '/usr/local/bin/chrome',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ].filter(Boolean);
  for (const executablePath of candidates) {
    if (fs.existsSync(executablePath)) return executablePath;
  }
  throw new Error(`No usable installed Chromium browser found among: ${candidates.join(', ')}`);
}
const CHROME = resolveChromePath();

const manifest = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const REPORT = manifest.report_dir;
const SHOTS = path.join(REPORT, 'screenshots');
fs.mkdirSync(SHOTS, { recursive: true });

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'mobile', width: 390, height: 844 },
];

const result = {
  started_at: new Date().toISOString(),
  origin: manifest.origin,
  viewports: {},
  scenarios: [],
  console_errors: [],
  failed_requests: [],
  overall: 'PENDING',
};

function record(scenario, ok, detail) {
  result.scenarios.push({ scenario, ok, detail });
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${scenario} :: ${detail || ''}`);
}

async function newContextWithSession(browser, vp, session) {
  const context = await browser.newContext({
    viewport: { width: vp.width, height: vp.height },
    locale: 'fa-IR',
    deviceScaleFactor: 1,
  });
  if (session) {
    await context.addCookies([{
      name: session.name, value: session.value, domain: '127.0.0.1',
      path: session.path || '/', httpOnly: true, secure: false, sameSite: 'Lax',
    }]);
  }
  return context;
}

function wireDiagnostics(page, vp, label) {
  page.on('console', (m) => {
    if (m.type() === 'error') {
      result.console_errors.push(`[${vp.name}/${label}] ${m.text()}`);
    }
  });
  page.on('requestfailed', (req) => {
    const u = req.url();
    if (/favicon|analytics|gtag|fonts.gstatic/.test(u)) return;
    result.failed_requests.push(`[${vp.name}/${label}] ${u} :: ${req.failure()?.errorText || ''}`);
  });
}

async function checkPage(page, vp, label) {
  const dir = await page.getAttribute('html', 'dir');
  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth > document.documentElement.clientWidth + 2
  );
  const headerCount = await page.$$eval('[data-r4-global-header], header, .sfb-header, [class*="header"]', (els) => els.length);
  return { rtl: dir === 'rtl', horizontal_overflow: overflow, header_present: headerCount > 0 };
}

async function run() {
  const browser = await chromium.launch({
    executablePath: CHROME,
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--host-resolver-rules=MAP * 127.0.0.1'],
  });

  try {
    for (const vp of VIEWPORTS) {
      // ---- Wishlist: anonymous ----
      {
        const context = await newContextWithSession(browser, vp, null);
        const page = await context.newPage();
        wireDiagnostics(page, vp, 'wishlist-anon');
        await page.goto(`${manifest.origin}/account/wishlist/`, { waitUntil: 'networkidle', timeout: 30000 });
        const status = await checkPage(page, vp, 'wishlist-anon');
        result.viewports[`${vp.name}_wishlist_anon`] = status;
        const bodyText = await page.textContent('body');
        const hasLoginPrompt = /وارد حساب کاربری خود شوید/.test(bodyText || '');
        await page.screenshot({ path: path.join(SHOTS, `${vp.name}_wishlist_anon.png`), fullPage: false });
        if (vp.name === 'desktop') {
          record('wishlist_anonymous_state', hasLoginPrompt, 'login prompt visible');
        }
        await context.close();
      }

      // ---- Wishlist: empty authenticated ----
      {
        const context = await newContextWithSession(browser, vp, manifest.empty_session);
        const page = await context.newPage();
        wireDiagnostics(page, vp, 'wishlist-empty');
        await page.goto(`${manifest.origin}/account/wishlist/`, { waitUntil: 'networkidle', timeout: 30000 });
        const status = await checkPage(page, vp, 'wishlist-empty');
        result.viewports[`${vp.name}_wishlist_empty`] = status;
        const bodyText = await page.textContent('body');
        const hasEmptyState = /لیست علاقه‌مندی‌های شما خالی است/.test(bodyText || '');
        await page.screenshot({ path: path.join(SHOTS, `${vp.name}_wishlist_empty.png`), fullPage: false });
        if (vp.name === 'desktop') {
          record('wishlist_empty_authenticated_state', hasEmptyState, 'empty state visible');
        }
        await context.close();
      }

      // ---- Wishlist: populated ----
      {
        const context = await newContextWithSession(browser, vp, manifest.populated_session);
        const page = await context.newPage();
        wireDiagnostics(page, vp, 'wishlist-populated');
        await page.goto(`${manifest.origin}/account/wishlist/`, { waitUntil: 'networkidle', timeout: 30000 });
        const status = await checkPage(page, vp, 'wishlist-populated');
        result.viewports[`${vp.name}_wishlist_populated`] = status;
        const productCardCount = await page.$$eval('article.pcard', (els) => els.length);
        await page.screenshot({ path: path.join(SHOTS, `${vp.name}_wishlist_populated.png`), fullPage: false });
        if (vp.name === 'desktop') {
          record('wishlist_populated_productcard_visible', productCardCount > 0, `${productCardCount} product card(s)`);
        }
        await context.close();
      }

      // ---- CMS published page ----
      {
        const context = await newContextWithSession(browser, vp, null);
        const page = await context.newPage();
        wireDiagnostics(page, vp, 'cms');
        await page.goto(`${manifest.origin}/pages/${manifest.cms_slug}/`, { waitUntil: 'networkidle', timeout: 30000 });
        const status = await checkPage(page, vp, 'cms');
        result.viewports[`${vp.name}_cms`] = status;
        const bodyText = await page.textContent('body');
        const hasBody = /باید دقیقاً حفظ شود/.test(bodyText || '');
        await page.screenshot({ path: path.join(SHOTS, `${vp.name}_cms.png`), fullPage: false });
        if (vp.name === 'desktop') {
          record('cms_title_body_visible', hasBody, 'CMS body text visible');
        }
        await context.close();
      }
    }

    result.overall =
      result.scenarios.every((s) => s.ok) &&
      result.console_errors.length === 0 &&
      result.failed_requests.length === 0 &&
      Object.values(result.viewports).every((v) => v.rtl && !v.horizontal_overflow && v.header_present)
        ? 'PASS'
        : 'FAIL';
  } catch (err) {
    result.overall = 'ERROR';
    result.error = String((err && err.stack) || err);
  } finally {
    await browser.close();
  }

  result.finished_at = new Date().toISOString();
  fs.writeFileSync(path.join(REPORT, 'w4a_browser_qa_result.json'), JSON.stringify(result, null, 2));
  console.log('OVERALL=' + result.overall);
  console.log('CONSOLE_ERRORS=' + result.console_errors.length);
  console.log('FAILED_REQUESTS=' + result.failed_requests.length);
}

run();
