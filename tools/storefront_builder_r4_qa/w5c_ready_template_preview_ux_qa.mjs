// P5-W5C Ready Template Preview UX — targeted browser QA runner.
//
// Reuses the existing tools/storefront_builder_r4_qa conventions (same
// Chromium/playwright-core resolution, same --host-resolver-rules=MAP *
// 127.0.0.1 approach, "Python owns Store-state setup + DB-truth
// verification, Node owns only browser UI assertions" — no second
// harness). Draft non-mutation is proven by running
// w5c_qa_snapshot.py against the real DB immediately BEFORE this script
// starts and immediately AFTER it finishes, and diffing the two JSON
// snapshots in the wrapper shell command — this script itself never
// reads the DB.
//
// Usage: node w5c_ready_template_preview_ux_qa.mjs <manifest.json>
//   manifest: { origin, admin_host, username, password, report_dir,
//               expected_count, expected_keys: [...], rep_early,
//               rep_middle, rep_late }

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { createRequire } from 'node:module';

function resolvePlaywrightCore() {
  const candidates = [new URL('../storefront_builder_qa/package.json', import.meta.url)];
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

const manifestPath = process.argv[2];
if (!manifestPath) {
  console.error('Usage: node w5c_ready_template_preview_ux_qa.mjs <manifest.json>');
  process.exit(2);
}
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const { admin_host, username, password, report_dir, expected_count, expected_keys, rep_early, rep_middle, rep_late } = manifest;
const port = manifest.port || new URL(manifest.origin).port;
const origin = `http://${admin_host}:${port}`;
fs.mkdirSync(report_dir, { recursive: true });

const results = [];
function record(name, ok, detail) {
  results.push({ name, ok, detail: detail || '' });
  console.log(`${ok ? 'PASS' : 'FAIL'} — ${name}${detail ? ' — ' + detail : ''}`);
}

function triggerLocator(page, key, { merchant = true } = {}) {
  const attr = merchant ? 'data-tpl-preview-url-merchant' : 'data-tpl-preview-url-demo';
  return page.locator(`[${attr}*="/templates/${key}/preview/"]`).first();
}

async function dialogState(page) {
  return page.evaluate(() => {
    const root = document.querySelector('[data-tpl-preview-root]');
    const frame = document.querySelector('[data-tpl-preview-frame]');
    const title = document.querySelector('[data-tpl-preview-title]');
    return {
      open: root ? root.classList.contains('is-open') : false,
      ariaHidden: root ? root.getAttribute('aria-hidden') : null,
      title: title ? title.textContent : null,
      frameSrc: frame ? frame.src : null,
      frameCount: document.querySelectorAll('[data-tpl-preview-frame]').length,
    };
  });
}

async function waitForFrameNavigation(page, { timeout = 8000 } = {}) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const frame = page.frames().find((f) => f.url().includes('/templates/') && f.url().includes('/preview/'));
    if (frame) {
      try {
        await frame.waitForLoadState('domcontentloaded', { timeout: 1500 });
        return frame;
      } catch {
        // retry
      }
    }
    await page.waitForTimeout(150);
  }
  return null;
}

async function main() {
  const browser = await chromium.launch({
    executablePath: resolveChromePath(),
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--host-resolver-rules=MAP * 127.0.0.1'],
  });
  const context = await browser.newContext({ baseURL: origin });
  const page = await context.newPage();
  page.on('console', (msg) => { if (msg.type() === 'error') console.log('  [console.error]', msg.text()); });
  page.on('pageerror', (err) => console.log('  [pageerror]', err.message));

  try {
    // 1. Real login.
    await page.goto(`${origin}/admin-portal/login/`, { waitUntil: 'domcontentloaded' });
    await page.fill('input[name="username"]', username);
    await page.fill('input[name="password"]', password);
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
      page.click('button[type="submit"], input[type="submit"]'),
    ]);

    // 2. Open Ready Template Gallery.
    await page.goto(`${origin}/admin-portal/storefront-builder/templates/`, { waitUntil: 'networkidle' });
    record('2. Gallery opens', page.url().includes('/storefront-builder/templates/'), page.url());
    await page.screenshot({ path: path.join(report_dir, '01-gallery.png'), fullPage: true }).catch(() => {});

    // 3. Exactly 50 Ready Template cards/triggers.
    const cardCount = await page.locator('.tpl-card').count();
    record('3. Exactly 50 Ready Template cards present', cardCount === expected_count, `cardCount=${cardCount}, expected=${expected_count}`);
    const triggerUrlSet = await page.$$eval('[data-tpl-preview-url-demo]', (els) => Array.from(new Set(els.map((e) => e.getAttribute('data-tpl-preview-url-demo')))));
    const missingKeys = expected_keys.filter((k) => !triggerUrlSet.some((u) => u.includes(`/templates/${k}/preview/`)));
    record('3b. Every registered key has a wired preview trigger', missingKeys.length === 0, `missing=${JSON.stringify(missingKeys)}`);

    // 4-10. Open Preview for the representative (middle) template.
    const midTrigger = triggerLocator(page, rep_middle, { merchant: true });
    await midTrigger.scrollIntoViewIfNeeded();
    await midTrigger.click();
    await page.waitForTimeout(300);
    let state = await dialogState(page);
    record('7. Dialog is visible', state.open && state.ariaHidden === 'false', JSON.stringify(state));
    record('8. Dialog title contains the template label', !!state.title && state.title.includes('پیش‌نمایشِ قالبِ'), state.title);
    record('9. Exactly one preview iframe exists', state.frameCount === 1, `frameCount=${state.frameCount}`);
    record('10. Iframe URL is the canonical live-preview route (merchant default)', state.frameSrc && state.frameSrc.includes(`/templates/${rep_middle}/preview/`) && state.frameSrc.includes('data=merchant'), state.frameSrc);

    // 11-13. Merchant data mode.
    await page.click('[data-tpl-preview-datasource="merchant"]');
    await page.waitForTimeout(300);
    state = await dialogState(page);
    record('12. Iframe URL has data=merchant', !!state.frameSrc && state.frameSrc.includes('data=merchant'), state.frameSrc);
    let frame = await waitForFrameNavigation(page);
    let frameHtml = frame ? await frame.content() : '';
    record('13. Preview banner identifies Merchant-data mode', frameHtml.includes('اطلاعات فروشگاه شما'), frameHtml.includes('اطلاعات فروشگاه شما') ? 'found' : 'not found');

    // 15-16. Desktop.
    await page.click('[data-tpl-preview-device="desktop"]');
    await page.waitForTimeout(200);
    const desktopPressed = await page.$eval('[data-tpl-preview-device="desktop"]', (el) => el.getAttribute('aria-pressed'));
    const desktopFrameStyle = await page.$eval('[data-tpl-preview-frame]', (el) => ({ width: el.style.width, transform: el.style.transform }));
    record('16. Desktop device state + natural presentation', desktopPressed === 'true' && desktopFrameStyle.width === '' && desktopFrameStyle.transform === '', JSON.stringify({ desktopPressed, desktopFrameStyle }));
    await page.screenshot({ path: path.join(report_dir, '02-preview-desktop.png') }).catch(() => {});

    // 17-18. Tablet.
    await page.click('[data-tpl-preview-device="tablet"]');
    await page.waitForTimeout(300);
    frame = await waitForFrameNavigation(page);
    const tabletWidth = frame ? await frame.evaluate(() => window.innerWidth).catch(() => null) : null;
    record('18. Tablet iframe document width ≈ 768', tabletWidth !== null && Math.abs(tabletWidth - 768) <= 5, `innerWidth=${tabletWidth}`);
    await page.screenshot({ path: path.join(report_dir, '03-preview-tablet.png') }).catch(() => {});

    // 19-21. Mobile.
    await page.click('[data-tpl-preview-device="mobile"]');
    await page.waitForTimeout(300);
    frame = await waitForFrameNavigation(page);
    const mobileWidth = frame ? await frame.evaluate(() => window.innerWidth).catch(() => null) : null;
    record('20. Mobile iframe document width ≈ 390', mobileWidth !== null && Math.abs(mobileWidth - 390) <= 5, `innerWidth=${mobileWidth}`);
    const bodyBox = frame ? await frame.locator('body').boundingBox().catch(() => null) : null;
    const mobileHtml = frame ? await frame.content() : '';
    const looksLikeErrorPage = /Server Error|Traceback|DisallowedHost/.test(mobileHtml);
    record('21. Mobile: non-zero rendered body, no error page', !!bodyBox && bodyBox.width > 0 && bodyBox.height > 0 && !looksLikeErrorPage, JSON.stringify({ bodyBox, looksLikeErrorPage }));
    await page.screenshot({ path: path.join(report_dir, '04-preview-mobile.png') }).catch(() => {});

    // 22-25. Switch to Demo (same iframe element, per contract F — this
    // dialog never destroys/recreates the iframe node; proven structurally
    // by frameCount staying 1 across the whole session, checked again here).
    await page.click('[data-tpl-preview-datasource="demo"]');
    await page.waitForTimeout(300);
    state = await dialogState(page);
    record('23. Same single iframe element reused after data-source switch', state.frameCount === 1, `frameCount=${state.frameCount}`);
    record('24. Canonical preview URL now Demo mode (no data=merchant)', !!state.frameSrc && state.frameSrc.includes(`/templates/${rep_middle}/preview/`) && !state.frameSrc.includes('data=merchant'), state.frameSrc);
    frame = await waitForFrameNavigation(page);
    frameHtml = frame ? await frame.content() : '';
    record('25. Preview banner identifies Rasti Mode Demo data', frameHtml.includes('داده‌های نمایشیِ Rasti Mode Demo'), frameHtml.includes('داده‌های نمایشیِ Rasti Mode Demo') ? 'found' : 'not found');
    await page.screenshot({ path: path.join(report_dir, '05-preview-demo-mode.png') }).catch(() => {});

    // 27. Switch back to Merchant (no-mutation proven externally by the
    // wrapper's before/after DB snapshot diff).
    await page.click('[data-tpl-preview-datasource="merchant"]');
    await page.waitForTimeout(300);
    state = await dialogState(page);
    record('27. Switched back to Merchant', !!state.frameSrc && state.frameSrc.includes('data=merchant'), state.frameSrc);

    // Accessibility: focus trap sanity — Tab from the last focusable
    // element (the "open in new tab" link) wraps back to the first
    // (Close button), never escaping to the Gallery behind the backdrop.
    const closeBtnId = await page.evaluate(() => {
      const btn = document.querySelector('[data-tpl-preview-close]');
      if (!btn.id) btn.id = 'qaCloseBtnProbe';
      return btn.id;
    });
    await page.locator('[data-tpl-preview-new-tab]').focus();
    await page.keyboard.press('Tab');
    const activeAfterTrapTab = await page.evaluate(() => document.activeElement && document.activeElement.getAttribute('data-tpl-preview-close') !== null);
    record('Accessibility: Tab wraps from last to first focusable (focus trap)', activeAfterTrapTab, `closeBtnId=${closeBtnId}`);

    // 29-30. Close with Escape; focus returns to the trigger.
    await page.keyboard.press('Escape');
    await page.waitForTimeout(200);
    state = await dialogState(page);
    const focusReturnedToTrigger = await page.evaluate((key) => {
      const active = document.activeElement;
      return !!active && active.getAttribute('data-tpl-preview-url-merchant') && active.getAttribute('data-tpl-preview-url-merchant').includes(`/templates/${key}/preview/`);
    }, rep_middle);
    record('29-30. Escape closes dialog and restores focus to the trigger', !state.open && state.ariaHidden === 'true' && focusReturnedToTrigger, JSON.stringify({ state, focusReturnedToTrigger }));

    // Independent Architect repair — Escape must ALSO close the dialog
    // when keyboard focus is INSIDE the (same-origin) preview iframe's
    // own document, not just when focus is among the parent dialog's own
    // controls (the test above). Separate test, per the repair directive.
    const midTriggerAgain = triggerLocator(page, rep_middle, { merchant: true });
    await midTriggerAgain.click();
    await page.waitForTimeout(300);
    frame = await waitForFrameNavigation(page);
    // Focus a real, always-present element INSIDE the iframe's own
    // document — the live-preview banner's "بازگشت به گالری" link.
    const backLinkInFrame = frame.locator('a', { hasText: 'بازگشت به گالری' }).first();
    await backLinkInFrame.focus();
    const focusIsInsideIframe = await page.evaluate(() => {
      const active = document.activeElement;
      return !!active && active.tagName === 'IFRAME' && active.hasAttribute('data-tpl-preview-frame');
    });
    const frameActiveTag = await frame.evaluate(() => document.activeElement && document.activeElement.tagName).catch(() => null);
    record(
      'Escape-from-iframe setup: focus is genuinely inside the iframe document',
      focusIsInsideIframe && frameActiveTag === 'A',
      JSON.stringify({ focusIsInsideIframe, frameActiveTag }),
    );
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
    state = await dialogState(page);
    const focusReturnedAfterIframeEscape = await page.evaluate((key) => {
      const active = document.activeElement;
      return !!active && active.getAttribute('data-tpl-preview-url-merchant') && active.getAttribute('data-tpl-preview-url-merchant').includes(`/templates/${key}/preview/`);
    }, rep_middle);
    record(
      'Escape while focus is INSIDE the preview iframe closes the dialog and restores focus to the trigger',
      !state.open && state.ariaHidden === 'true' && focusReturnedAfterIframeEscape,
      JSON.stringify({ state, focusReturnedAfterIframeEscape }),
    );

    // Reopen and confirm normal (parent-focus) Escape behavior still
    // works after the iframe-focus Escape cycle above.
    await midTriggerAgain.click();
    await page.waitForTimeout(300);
    state = await dialogState(page);
    const reopenOk = state.open;
    await page.keyboard.press('Escape');
    await page.waitForTimeout(200);
    state = await dialogState(page);
    record('Normal parent-focus Escape still works after the iframe-focus cycle', reopenOk && !state.open && state.ariaHidden === 'true', JSON.stringify(state));

    // 31-32. Open a SECOND, different Ready Template — retargeting proof.
    const earlyTrigger = triggerLocator(page, rep_early, { merchant: true });
    await earlyTrigger.scrollIntoViewIfNeeded();
    await earlyTrigger.click();
    await page.waitForTimeout(300);
    state = await dialogState(page);
    record(
      '31-32. Retargeting to a second template shows the NEW template, not stale content',
      state.open && !!state.frameSrc && state.frameSrc.includes(`/templates/${rep_early}/preview/`) && !state.frameSrc.includes(rep_middle),
      state.frameSrc,
    );
    frame = await waitForFrameNavigation(page);
    const secondTemplateOk = frame ? (await frame.content()).length > 0 : false;
    record('32b. Second template iframe loads successfully', secondTemplateOk);

    // 33. Close with the Close button.
    await page.click('[data-tpl-preview-close]');
    await page.waitForTimeout(200);
    state = await dialogState(page);
    record('33. Close button closes the dialog', !state.open && state.ariaHidden === 'true');

    // Representative coverage: a THIRD, "late" registry template — prove
    // successful retargeting + iframe load only (no full device/data-source
    // sweep — see the plan's browser-QA-scope decision, matching the
    // directive's "no 50x3 matrix" instruction).
    const lateTrigger = triggerLocator(page, rep_late, { merchant: false });
    await lateTrigger.scrollIntoViewIfNeeded();
    await lateTrigger.click();
    await page.waitForTimeout(300);
    state = await dialogState(page);
    frame = await waitForFrameNavigation(page);
    const lateOk = frame ? (await frame.content()).length > 0 : false;
    record('Representative coverage: third (late) template retargets + loads', state.open && !!state.frameSrc && state.frameSrc.includes(`/templates/${rep_late}/preview/`) && lateOk, state.frameSrc);
    await page.click('[data-tpl-preview-close]');
    await page.waitForTimeout(200);

    // 34. Existing Apply control remains available and unmodified.
    const applyFormAction = await page.$$eval('form[action*="apply-preset"]', (forms) => forms.length);
    record('34. Existing Apply control(s) still present', applyFormAction > 0, `applyFormCount=${applyFormAction}`);

    // Keyboard reachability: a plain trigger link is Tab-reachable and
    // Enter-activatable (no custom JS keyboard handling needed for a real
    // <a href>).
    const lastTrigger = triggerLocator(page, rep_late, { merchant: false });
    await lastTrigger.focus();
    await page.keyboard.press('Enter');
    await page.waitForTimeout(300);
    state = await dialogState(page);
    record('Keyboard: Enter on a focused trigger opens the dialog', state.open, JSON.stringify(state));
    await page.click('[data-tpl-preview-close]');
  } catch (error) {
    record('UNEXPECTED ERROR', false, error.stack || String(error));
    await page.screenshot({ path: path.join(report_dir, 'unexpected-error.png'), fullPage: true }).catch(() => {});
  } finally {
    await browser.close();
  }

  const summary = { total: results.length, pass: results.filter((r) => r.ok).length, fail: results.filter((r) => !r.ok).length, results };
  fs.writeFileSync(path.join(report_dir, 'w5c_browser_qa_results.json'), JSON.stringify(summary, null, 2));
  console.log(`\n${summary.pass}/${summary.total} PASS`);
  process.exit(summary.fail > 0 ? 1 : 0);
}

main();
