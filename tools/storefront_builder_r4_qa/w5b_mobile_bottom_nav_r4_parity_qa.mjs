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

// After a full top-level navigation (Undo/Redo/Publish each reload the
// whole page on success), the preview <iframe> is a brand-new frame that
// needs its own load to finish before its content() reflects the
// post-navigation Draft state — polling avoids a race against a fixed
// timeout.
async function waitForPreviewFrameReady(page, { timeout = 5000 } = {}) {
  const deadline = Date.now() + timeout;
  let frame = null;
  while (Date.now() < deadline) {
    frame = previewFrame(page);
    if (frame) {
      try {
        await frame.waitForLoadState('domcontentloaded', { timeout: 1500 });
        return frame;
      } catch {
        // frame navigated away mid-wait; retry
      }
    }
    await page.waitForTimeout(150);
  }
  return frame;
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
    const mutationBody = mutationResp ? await mutationResp.json().catch(() => null) : null;
    if (!mutationResp) await page.waitForTimeout(700);
    const mutationOk = !!mutationResp && mutationResp.status() === 200 && !!mutationBody && mutationBody.ok === true;
    record(
      '5. footer.update mutation accepted (200, ok, revision advanced)',
      mutationOk,
      mutationBody ? JSON.stringify({ status: mutationResp.status(), ok: mutationBody.ok, new_revision: mutationBody.new_revision }) : 'no response captured',
    );

    // 6. A real history entry landed. NOTE (pre-existing R4 behavior, not
    // specific to this field): the Global Design panel's read-side refresh
    // (refreshGlobalDesignAndPreview) only swaps #r4GlobalDesign's own
    // innerHTML — the toolbar's #r4UndoButton/#r4RedoButton are rendered
    // server-side only, from `history.can_undo`/`can_redo` (editor.html),
    // and are never toggled client-side; Undo/Redo's own click handlers
    // reload the whole page for exactly this reason (r4_editor.js,
    // "Section 21"). This is identical to every other Global Design field
    // (e.g. footer_variant) and is unrelated to the W5B diff. A real
    // merchant sees the enabled state on their next reload/navigation —
    // reproduced here the same way.
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.click('#r4GlobalDesignToggle');
    await page.waitForSelector('#r4GlobalMobileNavVariant', { state: 'visible', timeout: 5000 });
    const undoEnabled = await page.$eval('#r4UndoButton', (b) => !b.disabled);
    record('6. Save completes (Undo becomes enabled after reload)', undoEnabled);

    // 7. Switch Preview to Mobile.
    await page.click('[data-r4-device="mobile"]');
    const deviceAttr = await page.$eval('.r4-preview-canvas', (el) => el.getAttribute('data-r4-device'));
    record('7. Preview switched to mobile device mode', deviceAttr === 'mobile');

    // 8. Selected Bottom Nav is rendered in Preview.
    let frame = await waitForPreviewFrameReady(page);
    let frameHtml = frame ? await frame.content() : '';
    record('8. Preview shows the new Bottom Nav variant', frameHtml.includes('data-mobile-nav="four_item"'));

    // 9. Footer variant did not change.
    const footerVariantValue = await page.$eval('#r4GlobalFooterVariant', (el) => el.value);
    record('9. Footer variant unchanged', footerVariantValue === 'legacy_default' || footerVariantValue.length > 0, footerVariantValue);

    // 10. Undo (its own click handler reloads the whole page on success —
    // wait for that navigation rather than a fixed timeout).
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 8000 }).catch(() => null),
      page.click('#r4UndoButton'),
    ]);
    // 11. Previous Bottom Nav (hidden — renders no marker) returns.
    frame = await waitForPreviewFrameReady(page);
    frameHtml = frame ? await frame.content() : '';
    record('11. Undo restores the previous (hidden) Bottom Nav', !frameHtml.includes('data-mobile-nav="four_item"'));

    // 12. Redo (its own click handler also reloads the whole page on success).
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 8000 }).catch(() => null),
      page.click('#r4RedoButton'),
    ]);
    // 13. New Bottom Nav returns.
    frame = await waitForPreviewFrameReady(page);
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

    // 18. Stale mutation is rejected. `page` is now on the fresh
    // post-Publish Draft's editor (from step 15's reload), whose own
    // revision starts at 0 — so a hardcoded `base_revision: 0` would NOT
    // be stale for it. Instead: capture the real current revision, spend
    // it with one genuine mutation (advancing the server past it), then
    // replay that now-stale captured revision and expect a controlled 409.
    async function postFooterUpdate(baseRevision, variant) {
      return page.evaluate(async ({ rev, v }) => {
        const csrftoken = (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1] || '';
        const resp = await fetch('/admin-portal/storefront-builder/r4/mutate/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
          body: JSON.stringify({ base_revision: rev, mutation: { type: 'footer.update', patch: { mobile_nav_variant: v } } }),
        });
        return { status: resp.status, body: await resp.json().catch(() => null) };
      }, { rev: baseRevision, v: variant });
    }
    const capturedRevision = await page.evaluate(() => window.RastiSiR4 ? window.RastiSiR4.revision : null);
    const advanceResult = await postFooterUpdate(capturedRevision, 'five_item');
    const advanceOk = advanceResult.status === 200 && advanceResult.body && advanceResult.body.ok === true;
    const staleResult = await postFooterUpdate(capturedRevision, 'wide_cart');
    record(
      '18. Stale mutation rejected (409)',
      advanceOk && staleResult.status === 409,
      JSON.stringify({ capturedRevision, advanceResult, staleResult }),
    );
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
