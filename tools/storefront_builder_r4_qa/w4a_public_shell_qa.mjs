// P5-W4A Public Storefront Shell Convergence — browser QA runner.
//
// Reuses the existing tools/storefront_builder_r4_qa conventions (same
// Chromium/playwright-core resolution as w3_design_lab_qa.mjs, session-cookie
// auth, PASS/FAIL result JSON) — no second harness. Drives the EXISTING
// public Wishlist (customers:wishlist) and CMS content (content:page-detail)
// routes, across the required viewports, in RTL.
//
// P5-W4A review repair (IMPORTANT 4): strengthened to prove the full
// acceptance contract per template x viewport x scenario, not just RTL/
// overflow/header-present on desktop. Canonical markers are source-discovered
// from the actual Header/Footer/Bottom-Nav variant templates (never a broad
// ``[class*="header"]`` guess):
//   - Header root:      ``header.header``      (every global_header/*.html
//                        variant renders a real ``<header>`` carrying the
//                        literal ``header`` class token — the U2A-era
//                        variants add ``gh``/``gh--<id>`` alongside it, e.g.
//                        ``<header class="header gh gh--dark">``, while the
//                        pre-U2A "legacy-alias" variants — e.g. dark_digital's
//                        actually-resolved ``compact_menu``, which is a thin
//                        ``{% include %}`` of ``page_shell_header.html`` —
//                        render plain ``<header class="header...">``; only
//                        the shared ``header`` token is universal)
//   - Footer root:       ``footer.gf, footer.footer`` (same split: U2A
//                        variants render ``<footer class="gf ...">``,
//                        legacy-alias variants render
//                        ``<footer class="footer">`` via ``page_shell_footer.html``)
//   - Bottom Nav root:   ``[data-mobile-nav]``  (global_mobile_nav/*.html;
//                        the ``hidden`` variant renders nothing at all, so a
//                        Store with no Bottom Nav configured yields count 0)
//   - Bottom Nav visibility: ``.gmn`` is ``display:none`` by default and only
//                        ``display:block`` under the canonical
//                        ``@media(max-width:680px)`` rule in
//                        storefront_builder.css — i.e. it must be
//                        visible/healthy on the 390px mobile viewport only.
//
// Usage: node w4a_public_shell_qa.mjs <manifest.json>
//   manifest: {
//     origin, populated_session, empty_session, cms_slug, report_dir,
//     expect_bottom_nav: bool  // whether THIS Store's actually-applied
//                               // mobile_nav_variant (read back from the
//                               // published layout by the QA setup script,
//                               // never assumed from the literal preset-
//                               // registry key) resolved to something other
//                               // than "hidden" -- both dark_digital and
//                               // warm_boutique can resolve true here, since
//                               // a Ready Template's structural-DNA token is
//                               // translated through the Store Appearance
//                               // manifest, not matched string-for-string
//                               // against the preset definition.
//   }

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
const EXPECT_BOTTOM_NAV = !!manifest.expect_bottom_nav;

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'mobile', width: 390, height: 844 },
];

const SCENARIOS = [
  {
    label: 'wishlist_anon',
    path: '/account/wishlist/',
    session: null,
    assertBody: async (bodyText) => /وارد حساب کاربری خود شوید/.test(bodyText || ''),
    detail: 'login prompt visible',
  },
  {
    label: 'wishlist_empty',
    path: '/account/wishlist/',
    session: 'empty_session',
    assertBody: async (bodyText) => /لیست علاقه‌مندی‌های شما خالی است/.test(bodyText || ''),
    detail: 'empty state visible',
  },
  {
    label: 'wishlist_populated',
    path: '/account/wishlist/',
    session: 'populated_session',
    assertBody: async (bodyText, page) => (await page.$$eval('article.pcard', (els) => els.length)) > 0,
    detail: 'ProductCard (article.pcard) visible',
  },
  {
    label: 'cms',
    path: `/pages/${manifest.cms_slug}/`,
    session: null,
    assertBody: async (bodyText) => /باید دقیقاً حفظ شود/.test(bodyText || ''),
    detail: 'CMS title/body visible',
  },
];

const result = {
  started_at: new Date().toISOString(),
  origin: manifest.origin,
  expect_bottom_nav: EXPECT_BOTTOM_NAV,
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

async function checkPage(page, response) {
  const dir = await page.getAttribute('html', 'dir');
  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth > document.documentElement.clientWidth + 2
  );
  const headerCount = await page.$$eval('header.header', (els) => els.length);
  const footerCount = await page.$$eval('footer.gf, footer.footer', (els) => els.length);
  const bottomNavCount = await page.$$eval('[data-mobile-nav]', (els) => els.length);
  let bottomNavVisible = null;
  if (bottomNavCount > 0) {
    bottomNavVisible = await page.$eval('[data-mobile-nav]', (el) => {
      const s = window.getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return s.display !== 'none' && s.visibility !== 'hidden' && rect.height > 0;
    });
  }
  return {
    response_status: response ? response.status() : null,
    rtl: dir === 'rtl',
    horizontal_overflow: overflow,
    header_count: headerCount,
    footer_count: footerCount,
    bottom_nav_count: bottomNavCount,
    bottom_nav_visible: bottomNavVisible,
  };
}

function acceptanceContractOk(status, vp) {
  const okStatus = status.response_status === 200;
  const okRtl = status.rtl === true;
  const okOverflow = status.horizontal_overflow === false;
  const okHeaderNoDup = status.header_count === 1;
  const okFooterNoDup = status.footer_count === 1;
  const expectedBottomNavCount = EXPECT_BOTTOM_NAV ? 1 : 0;
  const okBottomNavCount = status.bottom_nav_count === expectedBottomNavCount;
  // When a Bottom Nav is configured it must be visible on mobile AND hidden
  // on desktop/tablet (storefront_builder.css's own @media(max-width:680px)
  // rule); when none is configured there is nothing to check here (count
  // above already requires 0, so bottom_nav_visible stays null).
  const okBottomNavVisible = !EXPECT_BOTTOM_NAV
    || status.bottom_nav_visible === (vp.name === 'mobile');
  return okStatus && okRtl && okOverflow && okHeaderNoDup && okFooterNoDup
    && okBottomNavCount && okBottomNavVisible;
}

async function runScenario(browser, vp, scenario) {
  const session = scenario.session ? manifest[scenario.session] : null;
  const context = await newContextWithSession(browser, vp, session);
  const page = await context.newPage();
  wireDiagnostics(page, vp, scenario.label);
  const response = await page.goto(`${manifest.origin}${scenario.path}`, {
    waitUntil: 'networkidle', timeout: 30000,
  });
  const status = await checkPage(page, response);
  const key = `${vp.name}_${scenario.label}`;
  result.viewports[key] = status;

  const bodyText = await page.textContent('body');
  const domainOk = await scenario.assertBody(bodyText, page);
  await page.screenshot({ path: path.join(SHOTS, `${key}.png`), fullPage: false });
  await context.close();

  const contractOk = acceptanceContractOk(status, vp);
  const ok = contractOk && domainOk;
  record(key, ok, `${scenario.detail} :: ${JSON.stringify(status)}`);
}

async function run() {
  const browser = await chromium.launch({
    executablePath: CHROME,
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--host-resolver-rules=MAP * 127.0.0.1'],
  });

  try {
    for (const vp of VIEWPORTS) {
      for (const scenario of SCENARIOS) {
        await runScenario(browser, vp, scenario);
      }
    }

    result.overall =
      result.scenarios.every((s) => s.ok) &&
      result.console_errors.length === 0 &&
      result.failed_requests.length === 0
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
