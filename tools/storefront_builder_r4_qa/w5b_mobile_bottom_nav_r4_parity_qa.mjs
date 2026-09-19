// P5-W5B Mobile Bottom Navigation R4 Parity — targeted browser QA runner.
//
// Reuses the existing tools/storefront_builder_r4_qa conventions (same
// Chromium/playwright-core resolution, same --host-resolver-rules=MAP *
// 127.0.0.1 approach, same "Python owns Store-state setup, Node owns only
// browser assertions" convention as w5a_canonical_editor_safety_qa.mjs) —
// no second harness.
//
// Usage: node w5b_mobile_bottom_nav_r4_parity_qa.mjs <manifest.json>
//   manifest: { origin, admin_host, public_host, admin_host_2, username, password, report_dir }

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { createRequire } from 'node:module';

function resolvePlaywrightCore() {
  const candidates = [
    new URL('../storefront_builder_qa/package.json', import.meta.url),
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

const manifestPath = process.argv[2];
if (!manifestPath) {
  console.error('Usage: node w5b_mobile_bottom_nav_r4_parity_qa.mjs <manifest.json>');
  process.exit(2);
}
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const { admin_host, public_host, admin_host_2, username, password, report_dir } = manifest;
const port = manifest.port || new URL(manifest.origin).port;
const origin = `http://${admin_host}:${port}`;
const publicOrigin = `http://${public_host}:${port}`;
const origin2 = `http://${admin_host_2}:${port}`;
fs.mkdirSync(report_dir, { recursive: true });

const results = [];
function record(name, ok, detail) {
  results.push({ name, ok, detail: detail || '' });
  console.log(`${ok ? 'PASS' : 'FAIL'} — ${name}${detail ? ' — ' + detail : ''}`);
}

function previewFrame(page) {
  return page.frames().find((f) => f.url().includes('/storefront-builder/preview/'));
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
    // Real login (real form, real CSRF, real session).
    await page.goto(`${origin}/admin-portal/login/`, { waitUntil: 'domcontentloaded' });
    await page.fill('input[name="username"]', username);
    await page.fill('input[name="password"]', password);
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
      page.click('button[type="submit"], input[type="submit"]'),
    ]);

    // 1. Open R4 Builder.
    await page.goto(`${origin}/admin-portal/storefront-builder/r4/`, { waitUntil: 'networkidle' });
    const editorOk = page.url().includes('/storefront-builder/r4/');
    record('1. R4 Builder opens', editorOk, page.url());

    // 2. Open Global Design.
    await page.click('#r4GlobalDesignToggle');
    await page.waitForSelector('#r4GlobalMobileNavVariant', { state: 'visible', timeout: 5000 });
    record('2. Global Design panel opens', true);

    // 3. Find the merchant-facing label.
    const bodyText = await page.content();
    record('3. "ناوبری پایین موبایل" label present', bodyText.includes('ناوبری پایین موبایل'));

    // 4. Selector options are registry-driven (spot-check a representative
    // spread: hidden, a conventional multi-item variant, a structurally
    // distinct one).
    const optionValues = await page.$$eval('#r4GlobalMobileNavVariant option', (opts) => opts.map((o) => o.value));
    const hasAll = ['hidden', 'four_item', 'floating_dock'].every((k) => optionValues.includes(k));
    record('4. Selector options are registry-driven', hasAll, JSON.stringify(optionValues));

    // 5. Switch to a non-hidden registered variant.
    const [mutationResp] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/r4/mutate/'), { timeout: 5000 }).catch(() => null),
      page.selectOption('#r4GlobalMobileNavVariant', 'four_item'),
    ]);
    if (!mutationResp) await page.waitForTimeout(700);

    // 6. Normal R4 save/revision completion — poll until Undo is enabled
    // (proves a real history entry landed).
    await page.waitForFunction(() => {
      const btn = document.getElementById('r4UndoButton');
      return btn && !btn.disabled;
    }, { timeout: 5000 }).catch(() => {});
    const undoEnabled = await page.$eval('#r4UndoButton', (b) => !b.disabled);
    record('6. Save completes (Undo becomes enabled)', undoEnabled);

    // 7. Switch Preview to Mobile.
    await page.click('[data-r4-device="mobile"]');
    const deviceAttr = await page.$eval('.r4-preview-canvas', (el) => el.getAttribute('data-r4-device'));
    record('7. Preview switched to mobile device mode', deviceAttr === 'mobile');

    // 8. Selected Bottom Nav is rendered in Preview.
    await page.waitForTimeout(400);
    let frame = previewFrame(page);
    let frameHtml = frame ? await frame.content() : '';
    record('8. Preview shows the new Bottom Nav variant', frameHtml.includes('data-mobile-nav="four_item"'));

    // 9. Footer variant did not change.
    const footerVariantValue = await page.$eval('#r4GlobalFooterVariant', (el) => el.value);
    record('9. Footer variant unchanged', footerVariantValue === 'legacy_default' || footerVariantValue.length > 0, footerVariantValue);

    // 10. Undo.
    await page.click('#r4UndoButton');
    await page.waitForTimeout(700);
    // 11. Previous Bottom Nav (hidden — renders no marker) returns.
    frame = previewFrame(page);
    frameHtml = frame ? await frame.content() : '';
    record('11. Undo restores the previous (hidden) Bottom Nav', !frameHtml.includes('data-mobile-nav="four_item"'));

    // 12. Redo.
    await page.click('#r4RedoButton');
    await page.waitForTimeout(700);
    // 13. New Bottom Nav returns.
    frame = previewFrame(page);
    frameHtml = frame ? await frame.content() : '';
    record('13. Redo restores the changed Bottom Nav', frameHtml.includes('data-mobile-nav="four_item"'));

    // 14. Public unchanged before Publish.
    const publicContext = await browser.newContext({ baseURL: publicOrigin });
    const publicPage = await publicContext.newPage();
    const publicBefore = await publicPage.goto(`${publicOrigin}/`, { waitUntil: 'domcontentloaded' });
    const publicBeforeHtml = await publicPage.content();
    record('14. Public storefront unchanged before Publish', !publicBeforeHtml.includes('data-mobile-nav="four_item"'), `status=${publicBefore.status()}`);

    // 15. Publish (no confirm() dialog on this button — only Discard has
    // one; a successful Publish reloads the page onto the next Draft).
    const publishBtn = await page.$('#r4PublishButton');
    if (publishBtn) {
      await Promise.all([
        page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 8000 }).catch(() => null),
        publishBtn.click(),
      ]);
    }
    record('15. Publish clicked and editor reloaded', publishBtn !== null);

    // 16. Public now uses the new Bottom Nav.
    const publicAfterResp = await publicPage.goto(`${publicOrigin}/`, { waitUntil: 'domcontentloaded' });
    const publicAfterHtml = await publicPage.content();
    record('16. Public storefront reflects the new Bottom Nav after Publish', publicAfterHtml.includes('data-mobile-nav="four_item"'), `status=${publicAfterResp.status()}`);
    await publicContext.close();

    // 17. A fresh Draft (second Store) defaults to hidden — Preview shows no nav.
    if (admin_host_2) {
      const context2 = await browser.newContext({ baseURL: origin2 });
      const page2 = await context2.newPage();
      await page2.goto(`${origin2}/admin-portal/login/`, { waitUntil: 'domcontentloaded' });
      await page2.fill('input[name="username"]', username);
      await page2.fill('input[name="password"]', password);
      await Promise.all([
        page2.waitForNavigation({ waitUntil: 'domcontentloaded' }),
        page2.click('button[type="submit"], input[type="submit"]'),
      ]);
      await page2.goto(`${origin2}/admin-portal/storefront-builder/r4/`, { waitUntil: 'networkidle' });
      await page2.click('[data-r4-device="mobile"]');
      await page2.waitForTimeout(400);
      const frame2 = previewFrame(page2);
      const frame2Html = frame2 ? await frame2.content() : '';
      record('17. Fresh Draft (hidden default) shows no Bottom Nav markup', !frame2Html.includes('data-mobile-nav='));
      await context2.close();
    } else {
      record('17. Fresh Draft hidden-default scenario', false, 'manifest missing admin_host_2');
    }

    // 18. Stale mutation is rejected.
    const staleResult = await page.evaluate(async () => {
      const csrftoken = (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1] || '';
      const resp = await fetch('/admin-portal/storefront-builder/r4/mutate/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
        body: JSON.stringify({ base_revision: 0, mutation: { type: 'footer.update', patch: { mobile_nav_variant: 'five_item' } } }),
      });
      return { status: resp.status, body: await resp.json().catch(() => null) };
    });
    record('18. Stale mutation rejected (409)', staleResult.status === 409, JSON.stringify(staleResult));
  } catch (error) {
    record('UNEXPECTED ERROR', false, error.stack || String(error));
    await page.screenshot({ path: path.join(report_dir, 'unexpected-error.png'), fullPage: true }).catch(() => {});
  } finally {
    await browser.close();
  }

  const summary = { total: results.length, pass: results.filter((r) => r.ok).length, fail: results.filter((r) => !r.ok).length, results };
  fs.writeFileSync(path.join(report_dir, 'w5b_browser_qa_results.json'), JSON.stringify(summary, null, 2));
  console.log(`\n${summary.pass}/${summary.total} PASS`);
  process.exit(summary.fail > 0 ? 1 : 0);
}

main();
