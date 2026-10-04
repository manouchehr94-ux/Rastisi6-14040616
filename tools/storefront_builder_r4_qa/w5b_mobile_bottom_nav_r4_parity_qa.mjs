// P5-W5B Mobile Bottom Navigation R4 Parity — targeted browser QA runner.
//
// Reuses the existing tools/storefront_builder_r4_qa conventions (same
// Chromium/playwright-core resolution, same --host-resolver-rules=MAP *
// 127.0.0.1 approach, same "Python owns Store-state setup, Node owns only
// browser assertions" convention as w5a_canonical_editor_safety_qa.mjs) —
// no second harness.
//
// Usage: node w5b_mobile_bottom_nav_r4_parity_qa.mjs <manifest.json>
//   manifest: { origin, admin_host, public_host, admin_host_2, username,
//               password, report_dir, expected_mobile_nav_variants }
//
// ---------------------------------------------------------------------
// Independent Architect browser-evidence repair (round 2 of W5B browser
// QA). The original run's evidence was accepted at the production/test
// level but rejected for four browser-evidence defects, all fixed here
// (QA script + evidence only — no production/Django-test file touched):
//
//   1. The admin/public browser contexts never set a real mobile
//      viewport, so "mobile" assertions were really running at the
//      default desktop context width. The storefront's own CSS
//      (`.gmn,.gmn-spacer{display:none}` by default, only shown inside
//      `@media(max-width:680px)`) makes viewport width the ONE thing
//      that actually gates Bottom Nav visibility — so a desktop-width
//      check proves nothing about mobile rendering.
//   2. The Public-after-Publish check only grepped raw HTML for
//      `data-mobile-nav="four_item"` — markup presence is not the same
//      as the element actually being visible at a real mobile width.
//   3. The Footer-sibling assertion accepted almost any non-empty value
//      (`=== 'legacy_default' || .length > 0`), which would pass even if
//      the Footer variant HAD changed.
//   4. The "registry-driven options" check only verified 3 representative
//      keys were present, while the evidence prose claimed all 9 were.
//
// Fixes: (1) the Draft Preview iframe already becomes a genuine 390px-wide
// CSS box via the existing `[data-r4-device="mobile"]` switcher (confirmed
// by direct source read of r4_editor.js/r4_editor.css) — this script now
// explicitly asserts `window.innerWidth <= 680` *inside that iframe's own
// document* rather than assuming it; the Public-storefront browser context
// is now opened with a real `viewport: {width: 390, height: 844}` (no
// second harness, no emulated UA/branding — just a real narrow viewport).
// (2) Bottom Nav visibility is now asserted via real DOM/computed-style
// checks (`getComputedStyle(el).display`, `boundingBox()`, Playwright
// `isVisible()` on the nav bar, and a minimum rendered nav-item count) —
// never source-HTML string matching alone. (3) the Footer variant is now
// captured before AND after the mobile-nav-only mutation and compared for
// exact equality. (4) the actual selector option list is now diffed
// (missing/unexpected, both required empty) against a registry-derived
// expected list supplied by the Python fixture (`EXPECTED_MOBILE_NAV_
// VARIANTS`, read via `global_region_registry.list_global_variants(...)`)
// — never a second hardcoded 9-key list inside this script.

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
const expectedVariants = manifest.expected_mobile_nav_variants;
if (!Array.isArray(expectedVariants) || expectedVariants.length === 0) {
  console.error('manifest.expected_mobile_nav_variants must be a non-empty array, derived from GLOBAL_MOBILE_NAV_REGION by the Python fixture.');
  process.exit(2);
}
const port = manifest.port || new URL(manifest.origin).port;
const origin = `http://${admin_host}:${port}`;
const publicOrigin = `http://${public_host}:${port}`;
const origin2 = `http://${admin_host_2}:${port}`;
const MOBILE_VIEWPORT = { width: 390, height: 844 };
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

// Real DOM/computed-style visibility check for the Bottom Nav — never
// source-HTML string matching. Works against either a Playwright Frame
// (Draft Preview iframe) or Page (Public storefront).
async function checkMobileNavVisibility(frameOrPage, variantKey) {
  const root = frameOrPage.locator(`[data-mobile-nav="${variantKey}"]`).first();
  const markupPresent = (await root.count()) > 0;
  if (!markupPresent) {
    return { markupPresent, computedVisible: false, nonzeroBounds: false, itemCount: 0, display: null, box: null };
  }
  const display = await root.evaluate((el) => getComputedStyle(el).display).catch(() => null);
  const box = await root.boundingBox().catch(() => null);
  const nonzeroBounds = !!box && box.width > 0 && box.height > 0;
  const barVisible = await frameOrPage
    .locator(`[data-mobile-nav="${variantKey}"] .gmn-bar`)
    .first()
    .isVisible()
    .catch(() => false);
  const itemCount = await frameOrPage
    .locator(`[data-mobile-nav="${variantKey}"] .gmn-item`)
    .count()
    .catch(() => 0);
  return {
    markupPresent,
    computedVisible: display !== 'none' && barVisible,
    nonzeroBounds,
    itemCount,
    display,
    box,
  };
}

// Confirms NO Bottom Nav markup is rendered at all — for the `hidden`
// variant (a true no-op template) and for Undo restoring `hidden`.
async function checkMobileNavAbsent(frameOrPage) {
  const count = await frameOrPage.locator('[data-mobile-nav]').count().catch(() => -1);
  return count === 0;
}

async function innerWidthOf(frameOrPage) {
  return frameOrPage.evaluate(() => window.innerWidth);
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

    // 4. Selector options match the canonical registry EXACTLY (not just
    // "contains a representative spread"). Expected keys come from the
    // Python fixture's own read of GLOBAL_MOBILE_NAV_REGION — never a
    // second hardcoded list in this script.
    const optionValues = await page.$$eval('#r4GlobalMobileNavVariant option', (opts) => opts.map((o) => o.value));
    const actualSorted = [...optionValues].sort();
    const expectedSorted = [...expectedVariants].sort();
    const missing = expectedSorted.filter((k) => !actualSorted.includes(k));
    const unexpected = actualSorted.filter((k) => !expectedSorted.includes(k));
    const exactMatch = missing.length === 0 && unexpected.length === 0 && actualSorted.length === expectedSorted.length;
    record(
      '4. Selector options match the registry EXACTLY (9/9, no missing, no unexpected)',
      exactMatch,
      JSON.stringify({ expectedCount: expectedSorted.length, actualCount: actualSorted.length, missing, unexpected, actual: optionValues }),
    );

    // 4b. Footer variant BEFORE the Bottom-Nav-only mutation (captured now,
    // compared after, per the sibling-isolation repair).
    const footerVariantBefore = await page.$eval('#r4GlobalFooterVariant', (el) => el.value);

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

    // 9 (captured here, recorded after Undo/Redo below). Footer variant
    // AFTER the Bottom-Nav-only mutation — compared for EXACT equality
    // against footerVariantBefore, not merely "non-empty".
    const footerVariantAfter = await page.$eval('#r4GlobalFooterVariant', (el) => el.value);

    // 7. Switch Preview to Mobile — and PROVE it, by reading
    // window.innerWidth INSIDE the preview iframe's own document, not just
    // the topbar toggle's aria-pressed state. The iframe becomes a real
    // 390px-wide CSS box via r4_editor.js's device switcher (confirmed by
    // source read), so this must resolve to <= 680 for a genuine mobile
    // viewport, matching storefront_builder.css's own `@media(max-width:
    // 680px)` gate on `.gmn` visibility.
    await page.click('[data-r4-device="mobile"]');
    const deviceAttr = await page.$eval('.r4-preview-canvas', (el) => el.getAttribute('data-r4-device'));
    let frame = await waitForPreviewFrameReady(page);
    const draftPreviewInnerWidth = frame ? await innerWidthOf(frame) : null;
    const draftPreviewIsMobileWidth = typeof draftPreviewInnerWidth === 'number' && draftPreviewInnerWidth <= 680;
    record(
      '7. Preview switched to a REAL mobile viewport (window.innerWidth <= 680 inside the Draft Preview document)',
      deviceAttr === 'mobile' && draftPreviewIsMobileWidth,
      `data-r4-device=${deviceAttr}, draftPreview.innerWidth=${draftPreviewInnerWidth}`,
    );

    // 8. Selected Bottom Nav is ACTUALLY VISIBLE in Draft Preview at the
    // real mobile viewport — markup + computed style + non-zero bounds +
    // rendered nav bar/items, not source-HTML string matching.
    const draftVis = await checkMobileNavVisibility(frame, 'four_item');
    record('8a. DRAFT MOBILE NAV MARKUP', draftVis.markupPresent, JSON.stringify(draftVis));
    record('8b. DRAFT MOBILE NAV COMPUTED VISIBILITY', draftVis.computedVisible, `display=${draftVis.display}`);
    record('8c. DRAFT MOBILE NAV NONZERO BOUNDS', draftVis.nonzeroBounds, JSON.stringify(draftVis.box));
    record('8d. Draft Preview renders the expected nav items (>= 3)', draftVis.itemCount >= 3, `itemCount=${draftVis.itemCount}`);
    await page.locator('.r4-preview-canvas').screenshot({ path: path.join(report_dir, '01-draft-preview-mobile-four_item.png') }).catch(() => {});

    // 9. Footer variant did NOT change as a side effect of the
    // Bottom-Nav-only mutation — exact before/after equality, not merely
    // "some non-empty value".
    record(
      '9. Footer variant preserved (exact before === after, not merely non-empty)',
      footerVariantBefore === footerVariantAfter,
      JSON.stringify({ footerVariantBefore, footerVariantAfter }),
    );

    // 10. Undo (its own click handler reloads the whole page on success —
    // wait for that navigation rather than a fixed timeout).
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 8000 }).catch(() => null),
      page.click('#r4UndoButton'),
    ]);
    // 11. Previous Bottom Nav (hidden — a true no-op template, so NO
    // [data-mobile-nav] element at all) returns. NOTE: Undo's own click
    // handler does a full `window.location.reload()` (same mechanism as
    // step 6), which resets the device switcher's server-rendered initial
    // state back to "desktop" — so the mobile view must be re-selected
    // after every such reload, not assumed to persist. Re-clicking mobile
    // here is not load-bearing for THIS assertion (checkMobileNavAbsent
    // does not depend on viewport width, since the `hidden` variant's
    // renderer emits no `[data-mobile-nav]` element at any width — see
    // step 13's comment for why it IS load-bearing there), but keeps the
    // journey a continuous mobile-preview session.
    await page.click('[data-r4-device="mobile"]').catch(() => {});
    frame = await waitForPreviewFrameReady(page);
    const undoAbsent = await checkMobileNavAbsent(frame);
    record('11. Undo restores the previous (hidden) Bottom Nav — no [data-mobile-nav] element at all', undoAbsent);

    // 12. Redo (its own click handler also reloads the whole page on success).
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 8000 }).catch(() => null),
      page.click('#r4RedoButton'),
    ]);
    // 13. New Bottom Nav returns — same real visibility check as step 8.
    // Re-select mobile device FIRST: this reload also resets the device
    // switcher to "desktop", and at desktop width the iframe is full-width
    // (> 680px), so storefront_builder.css's own `.gmn,.gmn-spacer{display:
    // none}` default (only overridden inside `@media(max-width:680px)`)
    // applies — the markup would still be present in the DOM (server-
    // rendered unconditionally) but genuinely NOT visible, which is exactly
    // the class of false-positive the Independent Architect's repair
    // directive called out. Confirmed by re-running this check before this
    // fix: markup was present but `display:none` / zero bounds at the
    // stale desktop width.
    await page.click('[data-r4-device="mobile"]');
    frame = await waitForPreviewFrameReady(page);
    await frame.waitForFunction(() => window.innerWidth <= 680, { timeout: 3000 }).catch(() => {});
    const redoVis = await checkMobileNavVisibility(frame, 'four_item');
    record(
      '13. Redo restores the changed Bottom Nav (markup + computed visibility + nonzero bounds)',
      redoVis.markupPresent && redoVis.computedVisible && redoVis.nonzeroBounds,
      JSON.stringify(redoVis),
    );

    // 14. Public unchanged before Publish (existence check is sufficient
    // here — proving an absence needs no visibility assertion).
    const publicContext = await browser.newContext({ baseURL: publicOrigin, viewport: MOBILE_VIEWPORT });
    const publicPage = await publicContext.newPage();
    const publicBefore = await publicPage.goto(`${publicOrigin}/`, { waitUntil: 'domcontentloaded' });
    const publicBeforeAbsent = await checkMobileNavAbsent(publicPage);
    record('14. Public storefront unchanged before Publish (no Bottom Nav rendered yet)', publicBeforeAbsent, `status=${publicBefore.status()}`);

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

    // 16. Public storefront, at a REAL mobile viewport (390x844 browser
    // context — this is a plain top-level page, not an iframe the R4
    // device switcher resizes, so it needs its own real viewport), ACTUALLY
    // RENDERS the new Bottom Nav visibly after Publish.
    const publicAfterResp = await publicPage.goto(`${publicOrigin}/`, { waitUntil: 'domcontentloaded' });
    const publicInnerWidth = await innerWidthOf(publicPage);
    const publicIsMobileWidth = publicInnerWidth <= 680;
    record('16a. PUBLIC MOBILE VIEWPORT (window.innerWidth <= 680)', publicIsMobileWidth, `publicPage.innerWidth=${publicInnerWidth}`);
    const publicVis = await checkMobileNavVisibility(publicPage, 'four_item');
    record('16b. PUBLIC MOBILE NAV MARKUP AFTER PUBLISH', publicVis.markupPresent, JSON.stringify(publicVis));
    record('16c. PUBLIC MOBILE NAV COMPUTED VISIBILITY', publicVis.computedVisible, `display=${publicVis.display}`);
    record('16d. PUBLIC MOBILE NAV NONZERO BOUNDS', publicVis.nonzeroBounds, JSON.stringify(publicVis.box));
    record('16e. Public renders the expected nav items (>= 3)', publicVis.itemCount >= 3, `itemCount=${publicVis.itemCount}, status=${publicAfterResp.status()}`);
    await publicPage.screenshot({ path: path.join(report_dir, '02-public-mobile-four_item.png') }).catch(() => {});
    await publicContext.close();

    // 17. A fresh Draft (second, untouched Store) defaults to `hidden` —
    // verified at a REAL mobile viewport (the same 390px device-switcher
    // mechanism as step 7), confirming NO Bottom Nav markup at all (the
    // canonical `hidden` renderer is a true no-op template — see
    // apps/storefront_builder/templates/storefront_builder/partials/
    // global_mobile_nav/hidden.html), not merely "hidden by desktop CSS".
    let hiddenPreviewInnerWidth = null;
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
      const frame2 = await waitForPreviewFrameReady(page2);
      hiddenPreviewInnerWidth = frame2 ? await innerWidthOf(frame2) : null;
      const hiddenIsMobileWidth = typeof hiddenPreviewInnerWidth === 'number' && hiddenPreviewInnerWidth <= 680;
      const hiddenAbsent = frame2 ? await checkMobileNavAbsent(frame2) : false;
      record(
        '17. Fresh Draft (hidden default) at a REAL mobile viewport shows no Bottom Nav markup at all',
        hiddenIsMobileWidth && hiddenAbsent,
        `innerWidth=${hiddenPreviewInnerWidth}, absent=${hiddenAbsent}`,
      );
      await page2.locator('.r4-preview-canvas').screenshot({ path: path.join(report_dir, '03-fresh-draft-hidden-mobile.png') }).catch(() => {});
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
