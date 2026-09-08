// RastiSi R4 Task 12 — deterministic Playwright smoke QA for the full R4
// Phase-1 vertical slice (Global Design + Undo/Redo + Publish + the shared
// Resource Picker, on top of the Task 5-10 mutation/structure/inspector
// work). Conceptually reuses tools/storefront_builder_qa/run.mjs's proven
// conventions (session-cookie auth, installed-Chromium discovery, one
// runtime manifest, PASS/FAIL result JSON) without touching that file or
// its 52KB R3 browser matrix — this is a small, separate, R4-only runner.
//
// Usage: node run.mjs <runtime-manifest.json>
//
// The manifest never carries a username/password — only a pre-built
// session cookie (see the caller's ad-hoc preflight script, which mirrors
// apps/storefront_builder/management/commands/qa_storefront_builder.py's
// _make_session_cookie/_build_manifest). No credentials are read from or
// written to this file.

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

// Section 3 — prefer the existing tools/storefront_builder_qa dependency
// over a second package.json/package-lock.json.
const require = createRequire(new URL('../storefront_builder_qa/package.json', import.meta.url));
let chromium;
try {
  ({ chromium } = require('playwright-core'));
} catch (_error) {
  console.error(
    'playwright-core is not installed. Run:\n' +
    '  cd tools/storefront_builder_qa\n' +
    '  npm install\n' +
    'then re-run this R4 QA script.'
  );
  process.exit(2);
}

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'qa_evidence', 'storefront_builder', 'r4', 'phase1');

// Phase 3 (opt-in via manifest.phase3) — the three responsive viewports the
// Phase 3 responsive capture iterates: desktop 1440x900, mobile 390x844,
// tablet 768x1024. Off by default; the default (non-phase3) run never touches
// these and its behavior/scenarios are unchanged.
const PHASE3_VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
  { name: 'tablet', width: 768, height: 1024 },
];

const REQUIRED_SCREENSHOTS = [
  '01_r4_initial.png',
  '02_hero_basic.png',
  '03_hero_advanced_typography_override.png',
  '04_product_added_reordered.png',
  '05_product_manual_picker.png',
  '06_brand_manual_picker.png',
  '07_conflict_detected.png',
  '08_publish_success.png',
  '09_public_storefront_after_publish.png',
  '10_draft_changed_public_unchanged.png',
];

const manifestPath = process.argv[2];
if (!manifestPath) {
  console.error('Usage: node run.mjs <runtime-manifest.json>');
  process.exit(2);
}
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
fs.mkdirSync(manifest.report_dir, { recursive: true });
fs.mkdirSync(EVIDENCE_DIR, { recursive: true });

const SAVE_STATE = {
  saved: 'ذخیره شد',
  saving: 'در حال ذخیره...',
  error: 'خطا در ذخیره تغییرات',
  conflict: 'نسخه‌ی جدیدتری از این صفحه موجود است',
};

const result = {
  started_at: new Date().toISOString(),
  builder_url: manifest.builder_url,
  public_url: manifest.public_url,
  scenarios: [],
  mutation_posts: [],
  history_posts: [],
  publish_posts: [],
  http_error_responses: [],
  console_errors: [],
  page_errors: [],
  request_failures: [],
  main_frame_navigations: [],
  screenshots: [],
  summary: { passed: 0, failed: 0 },
};

let browser;
let context;
let page;
let publicPage;

// The Preview endpoint the admin `page`'s #r4PreviewFrame child iframe GETs.
// R4's editor JS reloads that iframe fire-and-forget after every mutation
// (previewFrame.contentWindow.location.reload() in applyResourcePicker /
// refreshStructureAndPreview, r4_editor.js). We track how many such preview
// requests are in-flight on the admin `page` so settlePreviewFrame() can
// wait DETERMINISTICALLY for them all to complete — leaving nothing for the
// next main-frame navigation to abort — rather than relying on a networkidle
// heuristic that can sample the network while a reload is still queued.
const PREVIEW_URL_FRAGMENT = '/storefront-builder/preview/';
let inFlightPreviewRequests = 0;

// Scenario-crossing discovered state (never hardcoded — always read from
// the manifest or the rendered UI).
let heroSectionId = null;
let productSectionId = null;
let brandSectionId = null;
let productManualIds = [];
let brandManualIds = [];
let productManualLabels = [];
let brandManualLabels = [];
let publishedProductTitleSentinel = null;
let draftOnlyProductTitleSentinel = null;
// Section 9/Corrective Finding 2 — identity of the ONE deliberate stale-revision
// request Scenario 9 sends, captured directly off Playwright's own
// waitForResponse (not inferred from array position). Used to tightly bind
// the one browser-generated "Failed to load resource" console event Chromium
// unconditionally logs for that specific non-2xx response — by exact URL AND
// a narrow timestamp window — so no unrelated console error can hide behind
// a generic "contains 409" text match.
let staleConflictExpected = null;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function cleanName(value) {
  return String(value || 'scenario').replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80) || 'scenario';
}

function shot(filename) {
  return path.join(EVIDENCE_DIR, filename);
}

async function capture(filename) {
  const dest = shot(filename);
  await page.screenshot({ path: dest });
  result.screenshots.push(dest);
}

function deleteStaleScreenshots() {
  for (const name of REQUIRED_SCREENSHOTS) {
    try { fs.unlinkSync(shot(name)); } catch (_error) { /* did not exist — fine */ }
  }
}

async function scenario(name, fn) {
  const started = Date.now();
  try {
    await fn();
    result.scenarios.push({ name, status: 'PASS', ms: Date.now() - started });
    console.log(`PASS  ${name}`);
    result.summary.passed += 1;
  } catch (error) {
    result.scenarios.push({ name, status: 'FAIL', ms: Date.now() - started, error: error.stack || error.message || String(error) });
    console.log(`FAIL  ${name} — ${error.message || error}`);
    result.summary.failed += 1;
    try {
      if (page && !page.isClosed()) {
        await page.screenshot({ path: path.join(manifest.report_dir, `FAILURE-${cleanName(name)}.png`) });
      }
    } catch (_error) { /* best effort only */ }
  }
}

async function launchSystemBrowser() {
  const preferred = manifest.browser_channel === 'auto' ? ['chrome', 'msedge'] : [manifest.browser_channel];
  const errors = [];
  for (const channel of preferred) {
    try {
      return await chromium.launch({ channel, headless: !manifest.headed });
    } catch (error) {
      errors.push(`${channel}: ${error.message}`);
    }
  }
  // This sandboxed Linux QA environment ships a pre-installed Playwright
  // Chromium (no system Chrome/Edge channel) — same fallback spirit as the
  // existing tool's Windows candidate list, extended for Linux.
  const candidates = [
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
    '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
    '/usr/local/bin/chrome',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ].filter(Boolean);
  for (const executablePath of candidates) {
    if (!fs.existsSync(executablePath)) continue;
    try {
      return await chromium.launch({ executablePath, headless: !manifest.headed });
    } catch (error) {
      errors.push(`${executablePath}: ${error.message}`);
    }
  }
  throw new Error(`No usable installed Chromium browser found. ${errors.join(' | ')}`);
}

// ---- Section 10 — save helper ---------------------------------------------
async function waitSaved({ expectConflict = false, expectError = false, timeout = 10000 } = {}) {
  await page.waitForFunction(
    (labels) => {
      const el = document.getElementById('r4SaveState');
      return Boolean(el && (el.textContent === labels.saved || el.textContent === labels.conflict || el.textContent === labels.error));
    },
    SAVE_STATE,
    { timeout },
  );
  const text = await page.locator('#r4SaveState').textContent();
  if (text === SAVE_STATE.conflict) {
    assert(expectConflict, `Unexpected conflict save-state: ${text}`);
    return 'conflict';
  }
  if (text === SAVE_STATE.error) {
    assert(expectError, `Unexpected error save-state: ${text}`);
    return 'error';
  }
  assert(text === SAVE_STATE.saved, `Unexpected save-state text: ${text}`);
  return 'saved';
}

// ---- Section 11 — preview helper -------------------------------------------
async function previewFrame() {
  const locator = page.locator('#r4PreviewFrame');
  await locator.waitFor({ state: 'visible', timeout: 15000 });
  const handle = await locator.elementHandle();
  const frame = await handle.contentFrame();
  assert(frame, 'Preview iframe is not resolvable');
  assert(frame.url().includes('/storefront-builder/preview/'), `Preview navigated away from the existing Preview endpoint: ${frame.url()}`);
  const nestedIframeCount = await frame.locator('iframe').count();
  assert(nestedIframeCount === 0, `Unexpected nested iframe inside Preview (${nestedIframeCount})`);
  return frame;
}

async function discoverSectionIdFromPreview(sectionKey) {
  const frame = await previewFrame();
  const locator = frame.locator(`[data-section-key="${sectionKey}"]`).first();
  await locator.waitFor({ state: 'visible', timeout: 10000 });
  const id = await locator.getAttribute('data-section-id');
  assert(id, `Could not discover a Section id for "${sectionKey}" from Preview`);
  return id;
}

async function openSectionViaPreview(sectionKey) {
  const frame = await previewFrame();
  const locator = frame.locator(`[data-section-key="${sectionKey}"]`).first();
  await locator.waitFor({ state: 'visible', timeout: 10000 });
  await locator.scrollIntoViewIfNeeded();
  // The Preview Builder overlay renders a floating Container toolbar
  // (.sfb-rcontainer-toolbar) pinned to the TOP of an otherwise-empty
  // Section (e.g. hero_banner with no HeroSlide rows in this QA fixture).
  // A center-point click (even {force:true}) hit-tests to that overlay,
  // not the Section underneath, so preview.html's real capture-phase
  // click listener (interceptBuilderEditClick) never sees the click at
  // all — no postMessage, no Inspector. Clicking near the BOTTOM of the
  // Section's own box (still well inside it, but below the toolbar) is
  // the real "click through Preview" interaction a merchant would use on
  // an empty Section.
  const box = await locator.boundingBox();
  assert(box, `Could not resolve a bounding box for [data-section-key="${sectionKey}"]`);
  await locator.click({ position: { x: box.width / 2, y: Math.max(box.height - 6, 1) } });
  await page.locator('[data-r4-section-inspector]').waitFor({ state: 'visible', timeout: 10000 });
  return page.getAttribute('[data-r4-section-inspector]', 'data-r4-section-id');
}

// text/integer/boolean/choice/resource_source fields render BOTH a generic
// row wrapper (data-r4-field-row + the same data-r4-field-key/type) and the
// actual control with the same key/type but no data-r4-field-row — this
// always resolves to the control alone, never the ambiguous 2-element match
// (settings_field.html; appearance_override's compound wrapper is the one
// legitimate exception, where the ambiguity does not exist).
function fieldControl(key) {
  return page.locator(`[data-r4-field-key="${key}"]:not([data-r4-field-row])`);
}

async function openSectionById(sectionId) {
  await page.evaluate((id) => window.RastiSiR4.openSection(Number(id)), sectionId);
  await page.locator('[data-r4-section-inspector]').waitFor({ state: 'visible', timeout: 10000 });
}

async function closeInspectorIfOpen() {
  const closeBtn = page.locator('[data-r4-inspector-close]');
  if (await closeBtn.count()) {
    const hidden = await page.getAttribute('#r4Inspector', 'hidden');
    if (hidden === null) await closeBtn.click();
  }
}

// Round-2 corrective Finding C — deterministic main-frame navigation
// accounting. `framenavigated` fires synchronously on the Node event loop
// for the single `page` instance, so array-length before/after a bracketed
// `await actionFn()` captures precisely (and only) the main-frame
// navigation(s) THAT action caused — not a timestamp guess. Every scenario
// that intentionally navigates/reloads must go through this wrapper and
// mark its own navigation(s) as expected; anything that ever lands in
// main_frame_navigations without being marked here is, by construction, an
// unexpected navigation and fails finalInstrumentationAssertions().
async function withExpectedNavigation(actionFn, { count = 1 } = {}) {
  // Settle BEFORE the navigation too: R4's editor JS reloads the preview
  // iframe (previewFrame.contentWindow.location.reload(), r4_editor.js) after
  // every successful mutation, so by the time a scenario finishes its
  // save/apply and calls page.reload()/page.goto() here, a JS-triggered
  // preview GET (…/preview/?page=home) can still be in-flight. The upcoming
  // main-frame navigation would abort it (net::ERR_ABORTED). Waiting for the
  // preview iframe's load to settle first means there is nothing left to
  // abort. (Best-effort; scoped to the admin `page` only.)
  await settlePreviewFrame();
  const before = result.main_frame_navigations.length;
  await actionFn();
  const gained = result.main_frame_navigations.length - before;
  assert(gained === count, `Expected exactly ${count} main-frame navigation(s) from this action, got ${gained}`);
  for (let i = before; i < result.main_frame_navigations.length; i += 1) {
    result.main_frame_navigations[i].expected = true;
  }
  // Every admin navigation/reload goes through this wrapper. Each such
  // main-frame navigation re-mounts the R4 editor, whose #r4PreviewFrame
  // child iframe then kicks off its own GET of the Preview endpoint
  // (…/preview/?page=home). page.reload()/page.goto() above resolve on the
  // MAIN frame's `domcontentloaded`, which fires BEFORE that child-iframe
  // request has finished. If the very next scenario triggers another
  // main-frame navigation while the preview iframe's request is still
  // in-flight, Chromium tears down the old document and aborts that
  // in-flight sub-frame request with net::ERR_ABORTED — a benign,
  // harness-initiated superseded navigation, but a real dangling request
  // all the same. Rather than allow-list the abort, we eliminate it at its
  // source: after each admin navigation settles, wait for the preview
  // iframe to reach its own committed/loaded state so NO preview request is
  // left in-flight for the next navigation to abort. (Best-effort and
  // scoped strictly to the admin `page`; the phase3 matrix runs in its own
  // contexts and never touches this frame.)
  await settlePreviewFrame();
}

// Wait for the admin `page`'s #r4PreviewFrame child iframe to finish its
// in-flight Preview GET so a subsequent main-frame navigation has nothing
// to abort. Best-effort: if the preview frame is not present/resolvable
// (e.g. the page just navigated away entirely, or is closed), there is by
// definition no in-flight preview request to settle, so we return quietly.
async function settlePreviewFrame() {
  try {
    if (!page || page.isClosed()) return;
    const locator = page.locator('#r4PreviewFrame');
    if ((await locator.count()) === 0) return;
    // The preview reload R4's editor JS performs after a mutation
    // (previewFrame.contentWindow.location.reload() in applyResourcePicker /
    // refreshStructureAndPreview) is fire-and-forget: it is triggered from a
    // mutation-response .then() and is NOT awaited by the code that resolves
    // the save-state text waitSaved() keys off. So at the instant this helper
    // is first entered, that preview GET may not have STARTED yet (network
    // momentarily idle) — checking networkidle once would return immediately
    // and still leave the request to fire and then be aborted by the imminent
    // main-frame navigation. A short bounded settle lets any such just-issued
    // reload actually begin; then networkidle waits for it (and every other
    // sub-frame request) to fully COMPLETE. Only then is there provably
    // nothing in-flight for the next navigation to abort. Both steps are
    // bounded and best-effort; neither can hide a real error (the
    // request-failure gate still runs).
    //
    // Grace period: the reload R4's editor JS issues is fire-and-forget from
    // a mutation-response .then(), so at the instant we enter this helper the
    // preview GET may not have been dispatched yet. This bounded wait lets any
    // such just-issued reload REGISTER on the `request` listener (bumping
    // inFlightPreviewRequests) before we start polling for it to drain.
    await page.waitForTimeout(400);

    // Deterministic drain: poll until there is provably NO preview request
    // in-flight on the admin `page`. inFlightPreviewRequests is incremented on
    // every `request` whose URL hits the preview endpoint and decremented on
    // its `requestfinished`/`requestfailed`, so reaching 0 means every preview
    // GET has fully completed and nothing is left for the next main-frame
    // navigation to abort. Bounded (~8s) so a genuinely stuck request can
    // never hang the run — and if one somehow remained in-flight past the
    // bound, the request-failure gate would still catch the resulting abort,
    // so nothing is silently hidden.
    const drainDeadline = Date.now() + 8000;
    while (inFlightPreviewRequests > 0 && Date.now() < drainDeadline) {
      await page.waitForTimeout(50);
    }

    // Belt-and-suspenders: also let the overall network reach idle so any
    // non-preview sub-frame work the reload kicked off has settled too.
    await page.waitForLoadState('networkidle', { timeout: 10000 });
  } catch (_error) {
    // Best effort only — never let settling the preview frame fail a
    // scenario. If it genuinely could not settle in time, the existing
    // request-failure gate still catches any resulting abort, so nothing is
    // silently hidden.
  }
}

// =============================================================================
// Section 12 — Scenario 1: INITIAL R4
// =============================================================================
async function scenario01InitialR4() {
  await page.locator('[data-r4-shell]').waitFor({ state: 'visible', timeout: 15000 });
  assert(page.url().includes('/storefront-builder/r4/'), `Not on the R4 editor: ${page.url()}`);
  assert((await page.locator('[data-r4-shell]').count()) === 1, 'Expected exactly one R4 shell');
  await previewFrame();
  assert((await page.getAttribute('#r4Inspector', 'hidden')) !== null, 'Inspector must start hidden');
  assert((await page.getAttribute('#r4GlobalDesign', 'hidden')) !== null, 'Global Design must not be force-open initially');
  assert((await page.locator('#r4ConflictBanner').count()) === 0, 'No conflict banner should be present initially');
  await waitSaved();
  await capture('01_r4_initial.png');
}

// =============================================================================
// Section 13 — Scenario 2: Hero / Basic autosave
//
// PLAN RULING: HERO_BANNER_SCHEMA (section_registry.py) has NO free-text
// "title" field in its Basic group — only hero_style (choice) and autoplay
// (boolean). There is no other hero_* section key in the registry either.
// hero_style is used as the real Basic-tab sentinel value instead — it
// proves the exact same thing the plan asked for (a Basic-tab schema field
// autosaves through one mutate POST and survives a reload), just via the
// field that actually exists.
// =============================================================================
async function scenario02HeroBasic() {
  heroSectionId = await openSectionViaPreview('hero_banner');
  assert(heroSectionId, 'Could not discover the Hero section id');
  assert((await page.locator('[data-r4-section-inspector]').count()) === 1, 'Expected exactly one Inspector');
  assert((await page.locator('#r4Inspector iframe').count()) === 0, 'No iframe expected inside the Inspector');
  assert((await page.locator('.modal.show').count()) === 0, 'No modal expected');
  assert((await page.getAttribute('[data-r4-tab="basic"]', 'aria-selected')) === 'true', 'Basic tab must be active by default');

  const styleSelect = fieldControl('hero_style');
  const originalStyle = await styleSelect.inputValue();
  const sentinelStyle = originalStyle === 'split' ? 'overlay' : 'split';

  const beforeMutateCount = result.mutation_posts.length;
  const beforeNavCount = result.main_frame_navigations.length;
  await styleSelect.selectOption(sentinelStyle);
  await waitSaved();
  assert(result.mutation_posts.length - beforeMutateCount === 1, `Expected exactly 1 mutate POST for the Hero Basic edit, got ${result.mutation_posts.length - beforeMutateCount}`);
  assert(result.mutation_posts[result.mutation_posts.length - 1].status === 200, 'Hero Basic edit must return 200');
  assert(result.main_frame_navigations.length === beforeNavCount, 'The main R4 page must not navigate on an inline Inspector autosave');

  await withExpectedNavigation(() => page.reload({ waitUntil: 'domcontentloaded' }));
  await page.locator('[data-r4-shell]').waitFor({ state: 'visible' });
  await openSectionById(heroSectionId);
  const persisted = await fieldControl('hero_style').inputValue();
  assert(persisted === sentinelStyle, `Expected the server-authoritative hero_style=${sentinelStyle} after reload, got ${persisted}`);

  await capture('02_hero_basic.png');
}

// =============================================================================
// Section 14 — Scenario 3: Hero Advanced typography override (Section-local)
// =============================================================================
async function activateAdvancedTab() {
  await page.click('[data-r4-tab="advanced"]');
  await page.waitForFunction(() => {
    const panel = document.querySelector('[data-r4-tab-panel="advanced"]');
    return Boolean(panel && !panel.hasAttribute('hidden'));
  }, null, { timeout: 5000 });
}

async function scenario03HeroAdvancedTypography() {
  await activateAdvancedTab();
  const wrapper = page.locator('[data-r4-field-type="appearance_override"]');
  await wrapper.waitFor({ state: 'visible', timeout: 5000 });

  const fontSelect = wrapper.locator('[data-r4-appearance-font]');
  const scaleSelect = wrapper.locator('[data-r4-appearance-type-scale]');
  const inheritedFont = await fontSelect.inputValue();
  const inheritedScale = await scaleSelect.inputValue();

  await wrapper.locator('[data-r4-appearance-enabled]').check();

  const fontValues = await fontSelect.evaluate((el) => Array.from(el.options).map((o) => o.value));
  const scaleValues = await scaleSelect.evaluate((el) => Array.from(el.options).map((o) => o.value));
  const chosenFont = fontValues.find((v) => v !== inheritedFont) || fontValues[0];
  const chosenScale = scaleValues.find((v) => v !== inheritedScale) || scaleValues[0];
  assert(chosenFont, 'No selectable font option found');
  assert(chosenScale, 'No selectable type-scale option found');

  await fontSelect.selectOption(chosenFont);
  await scaleSelect.selectOption(chosenScale);
  await waitSaved();

  await withExpectedNavigation(() => page.reload({ waitUntil: 'domcontentloaded' }));
  await page.locator('[data-r4-shell]').waitFor({ state: 'visible' });
  await openSectionById(heroSectionId);
  await activateAdvancedTab();

  const wrapper2 = page.locator('[data-r4-field-type="appearance_override"]');
  assert(await wrapper2.locator('[data-r4-appearance-enabled]').isChecked(), 'Hero typography override must remain enabled after reload');
  const persistedFont = await wrapper2.locator('[data-r4-appearance-font]').inputValue();
  const persistedScale = await wrapper2.locator('[data-r4-appearance-type-scale]').inputValue();
  assert(persistedFont === chosenFont, `Expected persisted font=${chosenFont}, got ${persistedFont}`);
  assert(persistedScale === chosenScale, `Expected persisted type_scale=${chosenScale}, got ${persistedScale}`);

  await capture('03_hero_advanced_typography_override.png');

  // appearance_override exists ONLY on hero_banner's schema in the entire
  // registry (confirmed by inspecting section_registry.py) — there is no
  // second section type carrying the same field to compare a "did it leak"
  // value against. The observable proxy for "this stays Section-local, not
  // Global Design" is that a sibling schema-enabled Section (brand_carousel)
  // exposes NO such field at all in its own Inspector projection.
  await closeInspectorIfOpen();
  brandSectionId = await openSectionViaPreview('brand_carousel');
  assert((await page.locator('[data-r4-field-type="appearance_override"]').count()) === 0, 'brand_carousel unexpectedly exposes an appearance_override field');
  await closeInspectorIfOpen();
}

// =============================================================================
// Section 15 — Scenario 4: Add Product + reorder
// =============================================================================
async function scenario04AddProductAndReorder() {
  const structureOpen = await page.evaluate(() => document.querySelector('[data-r4-shell]').dataset.r4StructureOpen);
  if (structureOpen !== 'true') {
    await page.click('#r4StructureToggle');
    await page.locator('#r4Structure').waitFor({ state: 'visible', timeout: 5000 });
  }

  const idsBefore = await page.locator('[data-r4-structure-row]').evaluateAll((els) => els.map((el) => el.getAttribute('data-r4-structure-section-id')));

  const beforeMutateCount = result.mutation_posts.length;
  const beforeNavCount = result.main_frame_navigations.length;
  await page.selectOption('#r4StructureAddSelect', 'product_section');
  await page.click('#r4StructureAddButton');
  await waitSaved();
  await page.waitForFunction((n) => document.querySelectorAll('[data-r4-structure-row]').length === n, idsBefore.length + 1, { timeout: 10000 });
  assert(result.mutation_posts.length - beforeMutateCount === 1, `Expected exactly 1 add mutation, got ${result.mutation_posts.length - beforeMutateCount}`);
  assert(result.main_frame_navigations.length === beforeNavCount, 'Add must not cause a full main-page navigation');

  const idsAfterAdd = await page.locator('[data-r4-structure-row]').evaluateAll((els) => els.map((el) => el.getAttribute('data-r4-structure-section-id')));
  const newIds = idsAfterAdd.filter((id) => !idsBefore.includes(id));
  assert(newIds.length === 1, `Expected exactly one newly-added Section id, found ${newIds.length}`);
  productSectionId = newIds[0];

  const indexBeforeMove = idsAfterAdd.indexOf(productSectionId);
  const moveDirection = indexBeforeMove > 0 ? 'up' : 'down';

  const beforeMoveMutateCount = result.mutation_posts.length;
  await page.click(`[data-r4-structure-row][data-r4-structure-section-id="${productSectionId}"] [data-r4-structure-move="${moveDirection}"]`);
  await waitSaved();
  await page.waitForFunction(
    (old) => JSON.stringify(Array.from(document.querySelectorAll('[data-r4-structure-row]')).map((el) => el.getAttribute('data-r4-structure-section-id'))) !== JSON.stringify(old),
    idsAfterAdd,
    { timeout: 10000 },
  );
  assert(result.mutation_posts.length - beforeMoveMutateCount === 1, `Expected exactly 1 move mutation, got ${result.mutation_posts.length - beforeMoveMutateCount}`);

  const idsAfterMove = await page.locator('[data-r4-structure-row]').evaluateAll((els) => els.map((el) => el.getAttribute('data-r4-structure-section-id')));
  assert(JSON.stringify(idsAfterMove) !== JSON.stringify(idsAfterAdd), 'Section order did not actually change after the move');
  assert(new Set(idsAfterMove).size === idsAfterMove.length, 'Duplicate Section IDs found after add+move');

  const frame = await previewFrame();
  await frame.locator(`[data-section-id="${productSectionId}"]`).waitFor({ state: 'visible', timeout: 10000 });

  await capture('04_product_added_reordered.png');
}

// =============================================================================
// Section 16 — Scenario 5: Product auto rule + Persian-digit item_limit
// =============================================================================
async function scenario05ProductAutoAndPersianDigits() {
  await openSectionById(productSectionId);
  await page.click('[data-r4-resource-picker-open]');
  const pickerRoot = page.locator('[data-r4-picker-root]');
  await pickerRoot.waitFor({ state: 'visible', timeout: 10000 });

  await page.click('[data-r4-picker-mode="auto"]');
  await page.click('[data-r4-picker-auto-rule="newest"]');
  assert((await page.getAttribute('[data-r4-picker-apply]', 'disabled')) === null, 'Apply should be enabled once a supported auto rule is chosen');

  const beforeMutateCount = result.mutation_posts.length;
  await page.click('[data-r4-picker-apply]');
  await pickerRoot.waitFor({ state: 'hidden', timeout: 10000 });
  await waitSaved();
  assert(result.mutation_posts.length - beforeMutateCount === 1, `Expected exactly 1 mutation for the auto-rule Apply, got ${result.mutation_posts.length - beforeMutateCount}`);

  await page.locator('[data-r4-section-inspector]').waitFor({ state: 'visible', timeout: 10000 });
  const itemLimitField = fieldControl('item_limit');
  await itemLimitField.fill('۸');
  await itemLimitField.press('Tab');
  await waitSaved();

  await withExpectedNavigation(() => page.reload({ waitUntil: 'domcontentloaded' }));
  await page.locator('[data-r4-shell]').waitFor({ state: 'visible' });
  await openSectionById(productSectionId);

  const summaryText = await page.locator('[data-r4-field-type="resource_source"]:not([data-r4-field-row])').innerText();
  assert(summaryText.includes('محصول'), 'Source kind must still project as Product');
  assert(summaryText.includes('خودکار'), 'Source mode must still project as auto');
  assert(summaryText.includes('جدیدترین'), 'Auto rule must still project as newest');

  const persistedLimit = await fieldControl('item_limit').inputValue();
  assert(persistedLimit === '8', `Expected item_limit persisted as semantic integer displayed "8", got "${persistedLimit}"`);
}

// =============================================================================
// Section 17 — Scenario 6: Product manual Picker
// =============================================================================
async function selectTwoAndReorder(searchTerm) {
  const pickerRoot = page.locator('[data-r4-picker-root]');
  await page.click('[data-r4-picker-mode="manual"]');
  await page.fill('[data-r4-picker-search]', searchTerm);
  await page.waitForTimeout(500);
  await page.waitForSelector('#r4PickerResults [data-r4-picker-add]', { timeout: 10000 });

  const addButtons = await page.locator('#r4PickerResults [data-r4-picker-add]').all();
  assert(addButtons.length >= 2, `Expected >=2 search results for "${searchTerm}", got ${addButtons.length}`);
  const id1 = await addButtons[0].getAttribute('data-r4-picker-item-id');
  const label1 = await addButtons[0].getAttribute('data-r4-picker-item-label');
  const id2 = await addButtons[1].getAttribute('data-r4-picker-item-id');
  const label2 = await addButtons[1].getAttribute('data-r4-picker-item-label');
  await addButtons[0].click();
  await page.locator(`[data-r4-picker-selected-item][data-r4-picker-item-id="${id1}"]`).waitFor({ timeout: 5000 });
  await addButtons[1].click();
  await page.locator(`[data-r4-picker-selected-item][data-r4-picker-item-id="${id2}"]`).waitFor({ timeout: 5000 });

  const countText = await page.locator('[data-r4-picker-selected-count]').innerText();
  assert(Number(countText) >= 2, `Expected selected count >=2, got ${countText}`);
  assert((await page.locator('[data-r4-picker-root] iframe').count()) === 0, 'No iframe expected inside the Picker');
  assert((await page.locator('[data-r4-picker-root] form').count()) === 0, 'No <form> (save action) expected inside the Picker');

  const orderBefore = await page.evaluate(() => window.RastiSiR4.resourcePicker.selectedIds.slice());
  await page.click(`[data-r4-picker-selected-item][data-r4-picker-item-id="${id2}"] [data-r4-picker-move="up"]`);
  const orderAfter = await page.evaluate(() => window.RastiSiR4.resourcePicker.selectedIds.slice());
  assert(JSON.stringify(orderBefore) !== JSON.stringify(orderAfter), 'Reordering did not change the Picker selection order');
  assert((await page.getAttribute('[data-r4-picker-apply]', 'disabled')) === null, 'Apply should be enabled with a non-empty manual selection');

  return { ids: orderAfter, labels: [label1, label2] };
}

async function scenario06ProductManualPicker() {
  await page.click('[data-r4-resource-picker-open]');
  await page.locator('[data-r4-picker-root]').waitFor({ state: 'visible', timeout: 10000 });

  const picked = await selectTwoAndReorder('تی۱۲');
  productManualIds = picked.ids;
  productManualLabels = picked.labels;

  await capture('05_product_manual_picker.png');

  const beforeMutateCount = result.mutation_posts.length;
  await page.click('[data-r4-picker-apply]');
  await page.locator('[data-r4-picker-root]').waitFor({ state: 'hidden', timeout: 10000 });
  await waitSaved();
  assert(result.mutation_posts.length - beforeMutateCount === 1, `Expected exactly 1 mutation for the manual Apply, got ${result.mutation_posts.length - beforeMutateCount}`);

  await withExpectedNavigation(() => page.reload({ waitUntil: 'domcontentloaded' }));
  await page.locator('[data-r4-shell]').waitFor({ state: 'visible' });
  await openSectionById(productSectionId);
  const fieldValues = JSON.parse(await page.locator('#r4InspectorFieldValues').innerText());
  assert(fieldValues.source.mode === 'manual', 'Product source must persist as manual');
  assert(JSON.stringify(fieldValues.source.manual_ids) === JSON.stringify(productManualIds), `Expected persisted manual_ids ${JSON.stringify(productManualIds)}, got ${JSON.stringify(fieldValues.source.manual_ids)}`);
}

// =============================================================================
// Section 18 — Scenario 7: Brand — the SAME shared Picker
// =============================================================================
async function scenario07BrandManualPicker() {
  await closeInspectorIfOpen();
  brandSectionId = await openSectionViaPreview('brand_carousel');

  await page.click('[data-r4-resource-picker-open]');
  const pickerRoot = page.locator('[data-r4-picker-root]');
  await pickerRoot.waitFor({ state: 'visible', timeout: 10000 });

  for (const cls of ['r4-picker-overlay', 'r4-picker-dialog', 'r4-picker-mode-tabs', 'r4-picker-columns']) {
    assert((await page.locator(`.${cls}`).count()) >= 1, `Brand Picker is missing the shared Product-Picker class .${cls}`);
  }

  const picked = await selectTwoAndReorder('تی۱۲');
  brandManualIds = picked.ids;
  brandManualLabels = picked.labels;

  await capture('06_brand_manual_picker.png');

  const beforeMutateCount = result.mutation_posts.length;
  await page.click('[data-r4-picker-apply]');
  await pickerRoot.waitFor({ state: 'hidden', timeout: 10000 });
  await waitSaved();
  assert(result.mutation_posts.length - beforeMutateCount === 1, `Expected exactly 1 mutation for the Brand manual Apply, got ${result.mutation_posts.length - beforeMutateCount}`);

  await withExpectedNavigation(() => page.reload({ waitUntil: 'domcontentloaded' }));
  await page.locator('[data-r4-shell]').waitFor({ state: 'visible' });
  await openSectionById(brandSectionId);
  const fieldValues = JSON.parse(await page.locator('#r4InspectorFieldValues').innerText());
  assert(fieldValues.source.mode === 'manual', 'Brand source must persist as manual');
  assert(JSON.stringify(fieldValues.source.manual_ids) === JSON.stringify(brandManualIds), `Expected persisted Brand manual_ids ${JSON.stringify(brandManualIds)}, got ${JSON.stringify(fieldValues.source.manual_ids)}`);
}

// =============================================================================
// Section 19 — Scenario 8: Undo / Redo
//
// Uses product_section's real "title" text field (the plan's own suggested
// alternative to "Hero Basic title", which does not exist — see Scenario 2).
// =============================================================================
async function scenario08UndoRedo() {
  await closeInspectorIfOpen();
  await openSectionById(productSectionId);

  const titleField = fieldControl('title');
  const originalTitle = await titleField.inputValue();
  const sentinelTitle = `R4 QA Undo Sentinel ${Date.now()}`;

  const revisionN = await page.evaluate(() => window.RastiSiR4.revision);
  await titleField.fill(sentinelTitle);
  await titleField.press('Tab');
  await waitSaved();
  const revisionAfterEdit = await page.evaluate(() => window.RastiSiR4.revision);
  assert(revisionAfterEdit === revisionN + 1, `Expected revision N+1=${revisionN + 1} after the edit, got ${revisionAfterEdit}`);

  const beforeUndoHistoryCount = result.history_posts.length;
  await withExpectedNavigation(() => Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 15000 }),
    page.click('#r4UndoButton'),
  ]));
  await page.locator('[data-r4-shell]').waitFor({ state: 'visible' });
  assert(result.history_posts.length - beforeUndoHistoryCount === 1, `Expected exactly 1 history POST for Undo, got ${result.history_posts.length - beforeUndoHistoryCount}`);
  assert(result.history_posts[result.history_posts.length - 1].status === 200, 'Undo must return 200');
  const revisionAfterUndo = await page.evaluate(() => window.RastiSiR4.revision);
  assert(revisionAfterUndo === revisionN + 2, `Expected revision N+2=${revisionN + 2} after Undo, got ${revisionAfterUndo}`);

  await openSectionById(productSectionId);
  const titleAfterUndo = await fieldControl('title').inputValue();
  assert(titleAfterUndo === originalTitle, `Expected title restored to original "${originalTitle}" after Undo, got "${titleAfterUndo}"`);

  const beforeRedoHistoryCount = result.history_posts.length;
  await withExpectedNavigation(() => Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 15000 }),
    page.click('#r4RedoButton'),
  ]));
  await page.locator('[data-r4-shell]').waitFor({ state: 'visible' });
  assert(result.history_posts.length - beforeRedoHistoryCount === 1, `Expected exactly 1 history POST for Redo, got ${result.history_posts.length - beforeRedoHistoryCount}`);
  assert(result.history_posts[result.history_posts.length - 1].status === 200, 'Redo must return 200');
  const revisionAfterRedo = await page.evaluate(() => window.RastiSiR4.revision);
  assert(revisionAfterRedo === revisionN + 3, `Expected revision N+3=${revisionN + 3} after Redo, got ${revisionAfterRedo}`);

  await openSectionById(productSectionId);
  const titleAfterRedo = await fieldControl('title').inputValue();
  assert(titleAfterRedo === sentinelTitle, `Expected title restored to sentinel "${sentinelTitle}" after Redo, got "${titleAfterRedo}"`);

  publishedProductTitleSentinel = sentinelTitle;
}

// =============================================================================
// Section 20 — Scenario 9: real stale conflict (through R4's own sender)
// =============================================================================
async function scenario09StaleConflict() {
  await closeInspectorIfOpen();
  await openSectionById(heroSectionId);

  const oldRevision = await page.evaluate(() => window.RastiSiR4.revision);

  const heroStyleSelect = fieldControl('hero_style');
  const currentStyle = await heroStyleSelect.inputValue();
  const advancedStyle = currentStyle === 'split' ? 'overlay' : 'split';
  await heroStyleSelect.selectOption(advancedStyle);
  await waitSaved();
  const serverRevision = await page.evaluate(() => window.RastiSiR4.revision);
  assert(serverRevision === oldRevision + 1, 'Server revision did not advance from the normal edit');

  // Round-2 corrective Finding A — read the actual server-authoritative
  // value of the field the stale mutation will target (autoplay) BEFORE
  // sending the stale attempt, and choose the stale attempted value to be
  // its exact opposite. Proving hero_style survived (the field the
  // PRECEDING successful mutation touched) does not prove the stale patch
  // itself was rejected — only a direct pre/post comparison of the field
  // the REJECTED mutation targeted does that.
  const autoplayBeforeStale = await fieldControl('autoplay').isChecked();
  const staleAttemptedAutoplay = !autoplayBeforeStale;

  const beforeMutateCount = result.mutation_posts.length;
  const navCountBeforeStale = result.main_frame_navigations.length;
  await page.evaluate((old) => { window.RastiSiR4.revision = old; }, oldRevision);

  // Bind directly to the ONE real server response this exact deliberate
  // request receives — via Playwright's own waitForResponse, not by reading
  // back the last entry of a shared array — so its identity (URL) and a
  // narrow timestamp window can later tie the one expected browser-console
  // "Failed to load resource" noise line to this specific request and no
  // other (Finding 2 corrective).
  const staleWindowStart = Date.now();
  const [staleResponse] = await Promise.all([
    page.waitForResponse((resp) => resp.url().includes('/r4/mutate/') && resp.request().method() === 'POST', { timeout: 10000 }),
    page.evaluate(
      (args) => window.RastiSiR4.enqueueMutation({ type: 'section.update_settings', section_id: Number(args.sectionId), patch: { autoplay: args.value } }),
      { sectionId: heroSectionId, value: staleAttemptedAutoplay },
    ),
  ]);
  await waitSaved({ expectConflict: true });
  // Short, bounded settle window (not an arbitrary sleep — it exists solely
  // to let Chromium's own asynchronous DevTools console line for this exact
  // response, if any, land before the correlation window closes).
  await page.waitForTimeout(300);
  const staleWindowEnd = Date.now();

  assert(result.mutation_posts.length - beforeMutateCount === 1, `Expected exactly 1 mutate POST for the deliberate stale attempt, got ${result.mutation_posts.length - beforeMutateCount}`);
  const staleEntry = result.mutation_posts[result.mutation_posts.length - 1];
  assert(staleEntry.status === 409, 'The deliberate stale mutation must return a REAL server HTTP 409');
  assert(staleResponse.url() === staleEntry.url && staleResponse.status() === 409, 'Playwright waitForResponse must observe the same single stale mutate response the global listener recorded');
  const staleBody = await staleResponse.json();
  assert(staleBody?.code === 'stale_revision', `Expected the 409 body code to be exactly "stale_revision", got ${JSON.stringify(staleBody)}`);
  assert(await page.evaluate(() => window.RastiSiR4.conflict) === true, 'R4.conflict must become true');
  assert(await page.locator('#r4ConflictBanner').isVisible(), 'Conflict banner must be visible');
  assert(result.main_frame_navigations.length === navCountBeforeStale, 'No auto-reload may occur immediately after the conflict');

  staleConflictExpected = { url: staleEntry.url, windowStart: staleWindowStart, windowEnd: staleWindowEnd };

  await capture('07_conflict_detected.png');

  await withExpectedNavigation(() => page.reload({ waitUntil: 'domcontentloaded' }));
  await page.locator('[data-r4-shell]').waitFor({ state: 'visible' });
  assert(await page.evaluate(() => window.RastiSiR4.conflict) === false, 'R4.conflict must reset after reload');
  const revisionAfterReload = await page.evaluate(() => window.RastiSiR4.revision);
  assert(revisionAfterReload === serverRevision, `Expected the reload revision=${serverRevision}, got ${revisionAfterReload}`);

  await openSectionById(heroSectionId);
  const persistedStyle = await fieldControl('hero_style').inputValue();
  assert(persistedStyle === advancedStyle, `The stale attempt must not have overwritten server state — expected ${advancedStyle}, got ${persistedStyle}`);

  // Round-2 corrective Finding A — the direct proof: the field the stale
  // mutation actually TARGETED (autoplay) must retain exactly its
  // pre-stale-attempt value, and must NOT equal the rejected stale value.
  // This is the assertion the prior round was missing — hero_style above
  // only proves an unrelated, already-successful mutation was not clobbered.
  const autoplayAfterReload = await fieldControl('autoplay').isChecked();
  assert(
    autoplayAfterReload === autoplayBeforeStale,
    `The stale attempt must not have overwritten its targeted field — expected autoplay=${autoplayBeforeStale}, got ${autoplayAfterReload}`,
  );
  assert(
    autoplayAfterReload !== staleAttemptedAutoplay,
    `The rejected stale value must not have been applied — autoplay must not equal ${staleAttemptedAutoplay}`,
  );

  // A distinct, successful post-reload recovery mutation — proves normal
  // editing works again after a conflict (separate from the no-overwrite
  // proof above, which only reads state).
  const beforeRecoveryMutateCount = result.mutation_posts.length;
  const autoplayCheckbox = fieldControl('autoplay');
  await autoplayCheckbox.setChecked(!autoplayAfterReload);
  await waitSaved();
  assert(result.mutation_posts.length - beforeRecoveryMutateCount === 1, `Expected exactly 1 mutate POST for the post-recovery edit, got ${result.mutation_posts.length - beforeRecoveryMutateCount}`);
  assert(result.mutation_posts[result.mutation_posts.length - 1].status === 200, 'Post-recovery edit must succeed');
}

// =============================================================================
// Section 21 — Scenario 10: Publish
// =============================================================================
async function scenario10Publish() {
  await closeInspectorIfOpen();

  const beforePublishCount = result.publish_posts.length;
  await withExpectedNavigation(() => Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 15000 }),
    page.click('#r4PublishButton'),
  ]));
  await page.locator('[data-r4-shell]').waitFor({ state: 'visible' });
  assert(result.publish_posts.length - beforePublishCount === 1, `Expected exactly 1 publish POST, got ${result.publish_posts.length - beforePublishCount}`);
  assert(result.publish_posts[result.publish_posts.length - 1].status === 200, 'Publish must return 200');
  assert(!result.publish_posts.slice(-1).some((p) => p.status === 409), 'Publish must not be a 409');
  assert(page.url().includes('/storefront-builder/r4/'), `Expected the reload to return to R4, got ${page.url()}`);

  const newDraftRevision = await page.evaluate(() => window.RastiSiR4.revision);
  assert(newDraftRevision === 0, `Expected the fresh next Draft to start at its normal lifecycle revision (0), got ${newDraftRevision}`);

  await capture('08_publish_success.png');
}

// =============================================================================
// Section 22 — Scenario 11: public storefront parity
// =============================================================================
async function scenario11PublicParity() {
  publicPage = await context.newPage();
  // Round-2 corrective Finding B — publicPage previously had only
  // console/pageerror listeners (no response/requestfailed coverage at
  // all), so a 4xx/5xx or a failed request on the public storefront could
  // never be caught. It now gets the exact same instrumentation as the
  // admin `page`.
  attachNetworkInstrumentation(publicPage, { source: 'public' });

  await publicPage.goto(manifest.public_url, { waitUntil: 'domcontentloaded', timeout: 20000 });
  const html = await publicPage.content();
  assert(!html.includes('data-r4-shell'), 'Public storefront must not contain the R4 editor shell');
  assert((await publicPage.locator('#r4Inspector').count()) === 0, 'Public storefront must not contain the Inspector');
  assert((await publicPage.locator('#r4Structure').count()) === 0, 'Public storefront must not contain admin Structure controls');

  assert(publishedProductTitleSentinel, 'No published Product-title sentinel was recorded');
  assert(html.includes(publishedProductTitleSentinel), `Public storefront missing the published sentinel "${publishedProductTitleSentinel}"`);

  // Round-2 corrective "Additional hardening" — independently prove BOTH
  // resource types render on Public, not merely "at least one of the two
  // combined." A regression that dropped Brand entirely (or Product
  // entirely) from the public render could previously still pass this
  // assertion as long as the other type's label happened to appear.
  assert(productManualLabels.length > 0, 'No selected manual Product labels were recorded to check against Public');
  const productLabelHits = productManualLabels.filter((label) => label && html.includes(label));
  assert(productLabelHits.length > 0, `Public storefront shows none of the selected manual Product labels: ${JSON.stringify(productManualLabels)}`);

  assert(brandManualLabels.length > 0, 'No selected manual Brand labels were recorded to check against Public');
  const brandLabelHits = brandManualLabels.filter((label) => label && html.includes(label));
  assert(brandLabelHits.length > 0, `Public storefront shows none of the selected manual Brand labels: ${JSON.stringify(brandManualLabels)}`);

  result.public_parity = {
    product_label_hits: productLabelHits,
    brand_label_hits: brandLabelHits,
  };

  // capture() always screenshots the admin `page` — this must be the
  // separate publicPage/tab (Section 22: "Do NOT reuse the admin Preview
  // as proof").
  const dest = shot('09_public_storefront_after_publish.png');
  await publicPage.screenshot({ path: dest });
  result.screenshots.push(dest);
}

// =============================================================================
// Section 23 — Scenario 12: new Draft-only change
// =============================================================================
async function scenario12NewDraftOnlyChange() {
  await page.locator('[data-r4-shell]').waitFor({ state: 'visible' });
  // Publish cloned the just-Published version's content into a brand-new
  // Draft with new Section PKs — rediscover Product from the fresh Preview,
  // never reuse the old (now-immutable, Published-version) productSectionId.
  const freshProductSectionId = await openSectionViaPreview('product_section');

  const titleField = fieldControl('title');
  const currentTitle = await titleField.inputValue();
  assert(currentTitle === publishedProductTitleSentinel, `Expected the new Draft to start from the just-Published title "${publishedProductTitleSentinel}", got "${currentTitle}"`);

  draftOnlyProductTitleSentinel = `R4 QA DRAFT ONLY ${Date.now()}`;
  await titleField.fill(draftOnlyProductTitleSentinel);
  await titleField.press('Tab');
  await waitSaved();

  // A plain scalar Inspector field edit (section.update_settings) does not
  // itself reload the Preview iframe — only structural and Global Design
  // mutations do that (r4_editor.js). Reloading the whole R4 page is the
  // same "reload R4 and prove it persists" step the plan already calls
  // for next, and it also gives Preview a fresh, server-authoritative
  // render to check against — so the Preview assertion moves here rather
  // than expecting a live no-reload refresh that no R4 task ever built.
  await withExpectedNavigation(() => page.reload({ waitUntil: 'domcontentloaded' }));
  await page.locator('[data-r4-shell]').waitFor({ state: 'visible' });
  const frame = await previewFrame();
  await frame.locator('h2', { hasText: draftOnlyProductTitleSentinel }).first().waitFor({ state: 'visible', timeout: 10000 });
  await openSectionById(freshProductSectionId);
  const persisted = await fieldControl('title').inputValue();
  assert(persisted === draftOnlyProductTitleSentinel, `Draft-only title edit did not persist: expected "${draftOnlyProductTitleSentinel}", got "${persisted}"`);
}

// =============================================================================
// Section 24 — Scenario 13: public must remain unchanged
// =============================================================================
async function scenario13PublicUnchanged() {
  await publicPage.reload({ waitUntil: 'domcontentloaded' });
  const html = await publicPage.content();
  assert(html.includes(publishedProductTitleSentinel), `Published sentinel "${publishedProductTitleSentinel}" must still be present on the public storefront`);
  assert(!html.includes(draftOnlyProductTitleSentinel), `Draft-only sentinel "${draftOnlyProductTitleSentinel}" must NOT leak to the public storefront`);

  await publicPage.screenshot({ path: shot('10_draft_changed_public_unchanged.png') });
  result.screenshots.push(shot('10_draft_changed_public_unchanged.png'));
}

// =============================================================================
// Final cross-cutting instrumentation assertions (Section 9)
// =============================================================================
// A URL a real browser tab requests unprompted by any R4/Preview/Public
// application code (the tab-icon fetch) and that a bare Django dev server
// with no favicon route will answer 404 — Chromium logs its own
// "Failed to load resource" console line for that too, same mechanism as
// the deliberate 409 below, but it is not attributable to R4/Preview/
// Public at all. Correlated by the console message's own `location.url`
// (never by scanning `text`, which does not carry the failing URL).
const FAVICON_URL_PATTERN = /\/favicon\.ico(\?|$)/i;
// Task 7's disposable broken-image fixtures (a Brand logo + a Collection
// cover, each pointing at a filename that was never written to storage) are
// the one OTHER intentional, spec-required exception to the zero-error
// instrumentation gates below — "record browser network failure; do not
// equate no-image with broken-image" — gated to the phase3-only opt-in run
// so the default R3 harness's zero-error behavior is byte-for-byte
// unchanged. The marker is unique to this fixture; nothing else can
// produce a URL containing it.
const BROKEN_IMAGE_URL_PATTERN = /qa-broken-nonexistent/i;
function isExpectedBrokenImageNoise(url) {
  return Boolean(manifest.phase3) && BROKEN_IMAGE_URL_PATTERN.test(url || '');
}

function isExpectedStaleConflictNoise(entry) {
  // Chromium's DevTools protocol unconditionally logs a console.error for
  // ANY non-2xx/3xx response, regardless of how correctly the application
  // handled it — this is the one browser-generated line Scenario 9's SINGLE
  // deliberate stale mutate POST can produce (0 or 1 times; best-effort,
  // not guaranteed by Chromium on every run). It is bound tightly to that
  // one physical request — never to "any 409 anywhere" — by requiring ALL
  // three: (1) the exact response URL Scenario 9 itself captured via
  // page.waitForResponse, (2) a narrow timestamp window bracketing only
  // Scenario 9's own deliberate attempt, and (3) the expected Chromium
  // message shape. No other console error, however its text is worded, can
  // satisfy all three at once — so nothing can "hide" behind this exception.
  if (!staleConflictExpected) return false;
  const text = entry?.text || '';
  const url = entry?.location?.url || '';
  const at = typeof entry?.at === 'number' ? entry.at : null;
  return (
    /Failed to load resource/i.test(text) &&
    /409/.test(text) &&
    url === staleConflictExpected.url &&
    at !== null &&
    at >= staleConflictExpected.windowStart &&
    at <= staleConflictExpected.windowEnd
  );
}

// Round-2 corrective Finding B — the same tight, three-way correlation
// (exact URL + narrow timestamp window + expected status) applied to the
// raw HTTP-error-response record itself, not just the derived console
// noise line. This is what lets the ONE deliberate stale 409 be excluded
// from the otherwise-total HTTP error gate below without opening a hole
// any other error could hide in.
function isExpectedStale409Response(entry) {
  if (!staleConflictExpected) return false;
  return (
    entry.status === 409 &&
    entry.url === staleConflictExpected.url &&
    typeof entry.at === 'number' &&
    entry.at >= staleConflictExpected.windowStart &&
    entry.at <= staleConflictExpected.windowEnd
  );
}

// Round-2 corrective Finding B — attached identically to the admin/Preview
// `page` AND the standalone `publicPage` so a 4xx/5xx or a failed request
// from ANY R4-owned surface (R4 shell/document, Preview iframe/resources,
// Resource Picker/search endpoint, public storefront/resources) cannot
// silently escape the HTTP gate the way the old three-endpoint-only bucket
// allowlist did. Classification of "is this the one expected stale 409" is
// deliberately deferred to finalInstrumentationAssertions() (via the `at`
// timestamp recorded here) rather than decided inline — at the moment this
// listener observes the stale response, Scenario 9 has not yet returned
// from its own page.evaluate()/waitForResponse() call, so staleConflictExpected
// is not populated yet; filtering later, once it is, avoids that race
// instead of requiring one.
function attachNetworkInstrumentation(targetPage, { source } = {}) {
  targetPage.on('console', (message) => {
    if (message.type() === 'error') {
      result.console_errors.push({ text: message.text(), location: message.location(), source, at: Date.now() });
    }
  });
  targetPage.on('pageerror', (error) => {
    result.page_errors.push({ text: String(error.message || error), source });
  });
  targetPage.on('requestfailed', (request) => {
    const url = request.url();
    if (source === 'admin' && url.includes(PREVIEW_URL_FRAGMENT)) inFlightPreviewRequests -= 1;
    if (url.startsWith('data:')) return;
    result.request_failures.push({ url, method: request.method(), error: request.failure()?.errorText || '', source, at: Date.now() });
  });
  // Preview child-iframe request-lifecycle tracking, scoped strictly to the
  // admin `page` (source === 'admin'). This is installed here, alongside the
  // requestfailed/response listeners, so it observes exactly the same request
  // stream. settlePreviewFrame() polls inFlightPreviewRequests down to 0
  // before any main-frame navigation, guaranteeing no preview GET is left
  // in-flight to be aborted (net::ERR_ABORTED).
  if (source === 'admin') {
    targetPage.on('request', (request) => {
      if (request.url().includes(PREVIEW_URL_FRAGMENT)) inFlightPreviewRequests += 1;
    });
    targetPage.on('requestfinished', (request) => {
      if (request.url().includes(PREVIEW_URL_FRAGMENT)) inFlightPreviewRequests -= 1;
    });
  }
  targetPage.on('response', (response) => {
    const url = response.url();
    const status = response.status();
    let bucket = null;
    if (url.includes('/r4/mutate/')) bucket = 'mutation_posts';
    else if (url.includes('/r4/history/')) bucket = 'history_posts';
    else if (url.includes('/r4/publish/')) bucket = 'publish_posts';
    if (bucket) result[bucket].push({ url, status, source });

    if (status >= 400 && !FAVICON_URL_PATTERN.test(url)) {
      result.http_error_responses.push({ url, status, source, bucket, at: Date.now() });
    }
  });
}

async function finalInstrumentationAssertions() {
  assert(staleConflictExpected, 'Scenario 9 must have recorded the identity of its one deliberate stale request before final assertions can run');

  // The real, deterministic proof of "exactly one deliberate 409" is the
  // mutation_posts status + body-code check Scenario 9 already made against
  // Playwright's own response listener — never browser console noise.
  const total409 = result.mutation_posts.filter((p) => p.status === 409).length;
  assert(total409 === 1, `Expected exactly one stale HTTP 409 across all mutate POSTs, got ${total409}`);
  const the409 = result.mutation_posts.find((p) => p.status === 409);
  assert(the409.url === staleConflictExpected.url, 'The one HTTP 409 must be the same request Scenario 9 deliberately triggered');

  const expectedStaleConsoleEvents = result.console_errors.filter((e) => isExpectedStaleConflictNoise(e));
  assert(
    expectedStaleConsoleEvents.length <= 1,
    `A single physical request cannot legitimately produce more than 1 browser console event; got ${expectedStaleConsoleEvents.length} correlated to ${staleConflictExpected.url}`,
  );

  const unexpectedConsoleErrors = result.console_errors.filter(
    (e) => !isExpectedStaleConflictNoise(e) && !FAVICON_URL_PATTERN.test(e?.location?.url || '') && !isExpectedBrokenImageNoise(e?.location?.url),
  );
  assert(unexpectedConsoleErrors.length === 0, `Unexpected console errors: ${JSON.stringify(unexpectedConsoleErrors.slice(0, 5))}`);

  assert(result.page_errors.length === 0, `Page errors: ${JSON.stringify(result.page_errors.slice(0, 5))}`);

  const unexpectedRequestFailures = result.request_failures.filter((f) => !FAVICON_URL_PATTERN.test(f.url || '') && !isExpectedBrokenImageNoise(f.url));
  assert(unexpectedRequestFailures.length === 0, `Failed requests: ${JSON.stringify(unexpectedRequestFailures.slice(0, 5))}`);

  // Round-2 corrective Finding B — the full R4/Preview/Public HTTP-error
  // gate: every 4xx/5xx response attach{Network,}Instrumentation recorded,
  // across BOTH page and publicPage, minus only the one tightly-correlated
  // deliberate stale 409. No generic "contains 409" or bucket-shaped
  // allowlist remains — an unrelated error on the Picker/search endpoint,
  // Preview iframe resources, or public storefront resources now fails the
  // run exactly like an unrelated error on /r4/mutate/ already did.
  const expectedStale409Responses = result.http_error_responses.filter((e) => isExpectedStale409Response(e));
  assert(
    expectedStale409Responses.length === 1,
    `Expected exactly 1 HTTP-error-response record correlated to the one deliberate stale 409, got ${expectedStale409Responses.length}`,
  );
  const unexpectedHttp = result.http_error_responses.filter((e) => !isExpectedStale409Response(e) && !isExpectedBrokenImageNoise(e.url));
  assert(unexpectedHttp.length === 0, `Unexpected HTTP errors: ${JSON.stringify(unexpectedHttp.slice(0, 5))}`);

  // Round-2 corrective Finding C — every main-frame navigation must have
  // been explicitly bracketed by withExpectedNavigation() at the point it
  // happened; anything that was not is, by construction, unaccounted for.
  const unexpectedNavigations = result.main_frame_navigations.filter((n) => !n.expected);
  assert(unexpectedNavigations.length === 0, `Unexpected main-frame navigations: ${JSON.stringify(unexpectedNavigations.slice(0, 5))}`);

  // Explicit, disaggregated accounting (Finding 2 / Round-2 Findings B & C)
  // — no bucket may absorb an error/navigation it is not tightly
  // correlated to.
  result.instrumentation_summary = {
    unexpected_console_errors: unexpectedConsoleErrors.length,
    expected_stale_409_console_events: expectedStaleConsoleEvents.length,
    expected_stale_409_http: total409,
    expected_stale_409_url: staleConflictExpected.url,
    unexpected_http_errors: unexpectedHttp.length,
    unexpected_request_failures: unexpectedRequestFailures.length,
    page_errors: result.page_errors.length,
    expected_main_frame_navigations: result.main_frame_navigations.length - unexpectedNavigations.length,
    unexpected_main_frame_navigations: unexpectedNavigations.length,
  };
}

async function verifyScreenshots() {
  for (const name of REQUIRED_SCREENSHOTS) {
    const filePath = shot(name);
    assert(fs.existsSync(filePath), `Missing required screenshot: ${name}`);
    assert(fs.statSync(filePath).size > 0, `Empty screenshot file: ${name}`);
  }
}

// =============================================================================
// Phase 3 (opt-in) — Task 3 "Brand gate" real browser certification.
//
// Runs ONLY when manifest.phase3 is truthy. It is purely additive: it uses
// its own viewport-sized contexts (and reuses the admin `page` only for the
// Preview-iframe wrapper-projection check, after scenarios 01-13 have already
// finished), and every artifact is written under manifest.report_dir (never
// the committed evidence dir). The default (non-phase3) run never calls this,
// so existing scenarios and default behavior are completely unchanged.
//
// The certification exercises, for EACH of the three PHASE3_VIEWPORTS and
// EACH distinct envelope E1-E5 where Brand is placed:
//   E1 home           -> "/"
//   E2 product_detail -> "/products/<slug>/"
//   E3 listing        -> "/products/"
//   E4 collection      -> "/collections/<slug>/"
//   E5 cart           -> "/cart/"
// The fixture (management command, phase3 branch) placed one brand_carousel
// per variant (grid/carousel/beauty_tabs) on each of those five pages, all
// selecting the SAME ordered five brands (four with logos, one deliberately
// logo-less), with a resolvable View-all destination (a MerchantCollection),
// and published them via the normal lifecycle (Scenario 10). So public GETs
// already render every variant; the runner reads ids/slugs from the manifest
// (never hard-coded) and asserts.
// =============================================================================

// The public brand_carousel container class per variant (public markup
// carries NO editor data-section-* hooks — variants are told apart by the
// container/section classes the template emits).
const BRAND_VARIANT_CONTAINER = {
  grid: '.grid',
  carousel: '.brand-carousel',
  beauty_tabs: '.brand-beauty-tabs',
};

function phase3Fixture() {
  const fx = manifest.phase3_fixture;
  assert(fx && typeof fx === 'object', 'manifest.phase3_fixture is missing — the phase3 fixture was not threaded into the manifest');
  assert(fx.brand_section_ids && typeof fx.brand_section_ids === 'object', 'phase3_fixture.brand_section_ids missing');
  assert(Array.isArray(fx.brand_ids) && fx.brand_ids.length >= 2, 'phase3_fixture.brand_ids must list the selected brands');
  assert(Array.isArray(fx.variants) && fx.variants.length === 3, 'phase3_fixture.variants must list the 3 variant display_modes');
  assert(typeof fx.product_slug === 'string' && fx.product_slug, 'phase3_fixture.product_slug missing');
  assert(typeof fx.collection_slug === 'string' && fx.collection_slug, 'phase3_fixture.collection_slug missing');
  return fx;
}

function phase3Envelopes(fx) {
  // Public URL per envelope, resolved from manifest fixture ids/slugs.
  const origin = manifest.public_url.replace(/\/+$/, '');
  return [
    { key: 'home', label: 'E1-home', url: `${origin}/` },
    { key: 'product_detail', label: 'E2-product_detail', url: `${origin}/products/${fx.product_slug}/` },
    { key: 'listing', label: 'E3-listing', url: `${origin}/products/` },
    { key: 'collection', label: 'E4-collection', url: `${origin}/collections/${fx.collection_slug}/` },
    { key: 'cart', label: 'E5-cart', url: `${origin}/cart/` },
  ];
}

function mkReportDir(...parts) {
  const dir = path.join(manifest.report_dir, ...parts);
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

// Locate the brand_carousel <section> for a given variant on a PUBLIC page.
// beauty_tabs adds `.brand-section--beauty-tabs` on the <section>; grid/
// carousel are identified by the inner container class since the <section>
// class is generic. We scope to a section whose inner container matches.
function brandSectionLocatorFor(targetPage, variant) {
  if (variant === 'beauty_tabs') {
    // beauty_tabs uniquely tags the <section> AND every tile with brand-beauty.
    return targetPage.locator('section.brand-section--beauty-tabs:has(a.brand-tile)');
  }
  // A brand <section> (contains a.brand-tile) that directly holds the
  // variant's container class but is NOT the beauty-tabs section AND whose
  // tiles are NOT beauty tabs — this disambiguates grid vs carousel and
  // excludes any non-brand section that happens to use a `.grid` container.
  return targetPage.locator(
    `section.section:not(.brand-section--beauty-tabs):has(> ${BRAND_VARIANT_CONTAINER[variant]} a.brand-tile:not(.brand-beauty-tab))`,
  );
}

// ---------------------------------------------------------------------------
// Metrics + per-envelope/per-variant/per-viewport recording.
// ---------------------------------------------------------------------------
const phase3 = {
  started_at: new Date().toISOString(),
  viewports: PHASE3_VIEWPORTS.map((v) => v.name),
  envelopes: [],
  variant_checks: [],
  asset_envelope: [],
  v02_anchor: [],
  wrapper_projection: [],
  cart_htmx: [],
  screenshots: [],
  errors: [],
  // Task 7 additions (top-level, Brand-scoped).
  broken_image: null,
  combined_cart_htmx: [],
  tenant_negatives: null,
  // Task 5 "Collection gate" — additive Collection matrix metrics namespace.
  collection: {
    started_at: new Date().toISOString(),
    envelopes: [],
    variant_checks: [],
    asset_envelope: [],
    cart_htmx: [],
    page2: null,
    screenshots: [],
    errors: [],
    // Task 7 additions.
    broken_image_records: [],
    index_companion: null,
    known_red_findings: [],
  },
};

// ---------------------------------------------------------------------------
// Task 4 — ONE shared parameterized helper for every registered family's
// public per-envelope × variant × viewport browser matrix: asset envelope
// (once, no dup, no home.css off-home), document horizontal overflow, RTL,
// computed display/gridTemplateColumns/gap/overflowX, image objectFit,
// native horizontal scroll, keyboard focus, and console/page/request error
// collection. Brand and Collection (below) are the two families wired in
// today; a Task 6 family supplies the same config shape rather than
// duplicating this block again.
//
// Family-specific business logic — which tiles are "decoded" vs
// "fallback", slug/order semantics, extra per-variant checks (Brand's V02
// View-all anchor), and whether a layout mismatch throws immediately or is
// recorded as a known-red finding for the gate to check at the end — stays
// with the caller via the `classifyTiles` / `afterClassify` / `afterVariants`
// / `onLayoutIssue` callbacks; only the generic assertion machinery lives
// here.
// ---------------------------------------------------------------------------
async function phase3FamilyPublicMatrix(cfg) {
  const {
    errorSource, viewports, envelopes, variants, state, cssHomeOnlyNote,
    selectSection, tileSelector, imgSelector, extractTileData,
    tileCountFor, exactTileCount, classifyTiles, containerSelFor,
    imgObjectFitExpected, onLayoutIssue, afterClassify, afterVariants,
    screenshotFamily,
  } = cfg;

  for (const vp of viewports) {
    for (const env of envelopes) {
      const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
      await ctx.addCookies([manifest.session]);
      const pubPage = await ctx.newPage();
      const localErrors = [];
      pubPage.on('console', (m) => {
        if (m.type() !== 'error') return;
        const u = m.location()?.url || '';
        if (isExpectedBrokenImageNoise(u)) return; // Task 7 disposable broken-image fixture — recorded separately
        localErrors.push({ text: m.text(), url: u, source: `${errorSource}:${env.key}:${vp.name}` });
      });
      pubPage.on('pageerror', (e) => localErrors.push({ text: String(e.message || e), source: `${errorSource}:${env.key}:${vp.name}` }));
      pubPage.on('requestfailed', (r) => {
        const u = r.url();
        if (u.startsWith('data:') || /\/favicon\.ico(\?|$)/i.test(u) || isExpectedBrokenImageNoise(u)) return;
        localErrors.push({ text: `requestfailed ${u}`, source: `${errorSource}:${env.key}:${vp.name}` });
      });
      try {
        const resp = await pubPage.goto(env.url, { waitUntil: 'networkidle', timeout: 25000 });
        assert(resp && resp.status() < 400, `${env.label} public GET returned ${resp && resp.status()}`);

        // ---- Asset envelope A06 — page-scoped (once per page load) ----
        const assets = await pubPage.evaluate(() => {
          const styles = Array.from(document.querySelectorAll('link[rel=stylesheet]')).map((l) => l.getAttribute('href') || '');
          const scripts = Array.from(document.querySelectorAll('script[src]')).map((s) => s.getAttribute('src') || '');
          const norm = (u) => (u || '').split('?')[0];
          return {
            sb_css: styles.filter((h) => /storefront_builder\.css/.test(h)).length,
            home_css: styles.filter((h) => /\/home\.css/.test(h)).length,
            htmx: scripts.filter((s) => /htmx/i.test(s)).length,
            alpine: scripts.filter((s) => /alpine/i.test(s)).length,
            styleHrefs: styles.map(norm).filter(Boolean),
            scriptSrcs: scripts.map(norm).filter(Boolean),
          };
        });
        assert(assets.sb_css === 1, `${env.label}: storefront_builder.css must appear exactly once, got ${assets.sb_css}`);
        assert(assets.htmx === 1, `${env.label}: htmx script must appear exactly once, got ${assets.htmx}`);
        assert(assets.alpine === 1, `${env.label}: alpine script must appear exactly once, got ${assets.alpine}`);
        const dupStyles = assets.styleHrefs.filter((h, i) => assets.styleHrefs.indexOf(h) !== i);
        const dupScripts = assets.scriptSrcs.filter((s, i) => assets.scriptSrcs.indexOf(s) !== i);
        assert(dupStyles.length === 0, `${env.label}: duplicate stylesheet URLs: ${JSON.stringify(dupStyles)}`);
        assert(dupScripts.length === 0, `${env.label}: duplicate script URLs: ${JSON.stringify(dupScripts)}`);
        if (env.key !== 'home') {
          assert(assets.home_css === 0, `${env.label}: non-home envelope must NOT load home.css (found ${assets.home_css}) — ${cssHomeOnlyNote}`);
        }

        // Document must not overflow horizontally (internal carousel rail
        // overflow is allowed — scoped to documentElement, not the rail).
        const overflow = await pubPage.evaluate(() => ({
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        }));
        assert(overflow.scrollWidth <= vp.width + 1, `${env.label} @${vp.name}: document horizontal overflow scrollWidth=${overflow.scrollWidth} > ${vp.width + 1}`);
        state.asset_envelope.push({ envelope: env.key, viewport: vp.name, ...assets, scrollWidth: overflow.scrollWidth, clientWidth: overflow.clientWidth });

        // ---- per variant on this envelope ----
        const perVariantOrders = [];
        for (const variant of variants) {
          const section = await selectSection(pubPage, variant);
          assert(section, `${env.label} @${vp.name} ${variant}: could not locate the expected section`);
          await section.waitFor({ state: 'attached', timeout: 15000 });

          const tiles = section.locator(tileSelector);
          const tileCount = await tiles.count();
          const expectedCount = tileCountFor(variant);
          if (exactTileCount) {
            assert(tileCount === expectedCount, `${env.label} @${vp.name} ${variant}: expected ${expectedCount} tiles, got ${tileCount}`);
          } else {
            assert(tileCount >= expectedCount, `${env.label} @${vp.name} ${variant}: expected >=${expectedCount} tiles, got ${tileCount}`);
          }

          const tileData = await tiles.evaluateAll(extractTileData);
          const classified = classifyTiles(tileData, { env, vp, variant });
          perVariantOrders.push({ variant, slugOrder: classified.slugOrder });

          if (afterClassify) await afterClassify(section, { env, vp, variant, tileData, classified });

          // ---- Task 7: computed layout / RTL / keyboard focus / native scroll ----
          const containerSel = containerSelFor(variant);
          const layout = await section.evaluate((sec, { sel, imgSel }) => {
            const container = sec.querySelector(sel) || sec;
            const cs = getComputedStyle(container);
            const img = sec.querySelector(imgSel);
            return {
              display: cs.display,
              gridTemplateColumns: cs.gridTemplateColumns,
              gap: cs.gap,
              overflowX: cs.overflowX,
              scrollWidth: container.scrollWidth,
              clientWidth: container.clientWidth,
              imgObjectFit: img ? getComputedStyle(img).objectFit : null,
              dir: document.documentElement.dir,
            };
          }, { sel: containerSel, imgSel: imgSelector });
          assert(layout.dir === 'rtl', `${env.label} @${vp.name}: document must render RTL, got dir="${layout.dir}"`);
          if (variant === 'grid') {
            // Both halves required: `display` alone would still pass a
            // `display:grid` container with no actual column tracks (a
            // single-column collapse). gridTemplateColumns must resolve to
            // more than one track.
            const trackCount = (layout.gridTemplateColumns || '').trim().split(/\s+/).filter((t) => t && t !== 'none').length;
            const displayOk = /grid|flex/.test(layout.display);
            const tracksOk = trackCount >= 2;
            if (!displayOk || !tracksOk) {
              onLayoutIssue({
                envelope: env.key, viewport: vp.name, variant,
                expected: 'display grid|flex AND >=2 resolved grid/flex tracks',
                actual: `display="${layout.display}" gridTemplateColumns="${layout.gridTemplateColumns}"`,
              });
            }
          } else {
            // Both halves required: `overflowX` alone would still pass a
            // `display:block` container that happens to compute
            // overflow-x:auto but never actually lays tiles out horizontally.
            const displayOk = /flex/.test(layout.display);
            const overflowOk = layout.overflowX === 'auto' || layout.overflowX === 'scroll';
            if (!displayOk || !overflowOk) {
              onLayoutIssue({
                envelope: env.key, viewport: vp.name, variant,
                expected: 'display flex AND overflowX auto|scroll',
                actual: `display="${layout.display}" overflowX="${layout.overflowX}"`,
              });
            }
          }
          if (layout.imgObjectFit) {
            assert(layout.imgObjectFit === imgObjectFitExpected, `${env.label} @${vp.name} ${variant}: tile image objectFit expected "${imgObjectFitExpected}", got "${layout.imgObjectFit}"`);
          }

          // Native horizontal scroll proof — only meaningful when the rail
          // actually overflows (carousel/beauty_tabs at this viewport width).
          let nativeScroll = null;
          if (variant !== 'grid' && layout.scrollWidth > layout.clientWidth) {
            const scrolled = await section.evaluate((sec, sel) => {
              const rail = sec.querySelector(sel);
              const before = rail.scrollLeft;
              // These rails use `scroll-snap-type: x mandatory` (home.css /
              // storefront_builder.css), so an arbitrary small delta (e.g.
              // +40px, not aligned to any tile's scroll-snap-align edge) is
              // legitimately snapped straight back to the nearest snap point
              // — usually 0 — which is native scroll-snap behavior, not a
              // broken rail. Scroll all the way to the far end instead (a
              // real, snap-aligned resting position at the last tile), tried
              // in both the positive and RTL "negative scrollLeft" direction
              // Chromium uses for RTL block content.
              rail.scrollLeft = rail.scrollWidth;
              let after = rail.scrollLeft;
              if (after === before) {
                rail.scrollLeft = -rail.scrollWidth;
                after = rail.scrollLeft;
              }
              return { before, after };
            }, containerSel);
            assert(scrolled.after !== scrolled.before, `${env.label} @${vp.name} ${variant}: carousel rail did not respond to native scrollLeft (before=${scrolled.before} after=${scrolled.after})`);
            nativeScroll = scrolled;
          }

          // Keyboard focus on the first interactive tile anchor.
          const focusable = await tiles.first().evaluate((a) => { a.focus(); return document.activeElement === a; });
          assert(focusable, `${env.label} @${vp.name} ${variant}: tile anchor did not receive keyboard focus`);

          // Screenshot public per variant/viewport.
          const pubDir = mkReportDir(screenshotFamily, variant, vp.name);
          const pubShot = path.join(pubDir, `${env.key}-public.png`);
          await section.scrollIntoViewIfNeeded().catch(() => {});
          await pubPage.screenshot({ path: pubShot });
          state.screenshots.push(pubShot);

          state.variant_checks.push({
            envelope: env.key, viewport: vp.name, variant,
            tile_count: tileCount, slug_order: classified.slugOrder,
            decoded_imgs: classified.decodedCount,
            ...classified.extraFields,
            computed_layout: { display: layout.display, gridTemplateColumns: layout.gridTemplateColumns, gap: layout.gap, overflowX: layout.overflowX, imgObjectFit: layout.imgObjectFit, dir: layout.dir },
            native_scroll: nativeScroll,
            keyboard_focusable: focusable,
          });
        }

        if (afterVariants) afterVariants(perVariantOrders, { env, vp });

        state.envelopes.push({ envelope: env.key, viewport: vp.name, url: env.url, status: resp.status() });
      } finally {
        if (localErrors.length) state.errors.push(...localErrors);
        try { await ctx.close(); } catch (_error) { /* best effort */ }
      }
    }
  }
  assert(state.errors.length === 0, `${errorSource} console/page/request errors: ${JSON.stringify(state.errors.slice(0, 6))}`);
}

// ---------------------------------------------------------------------------
// Scenario group 1 + 2 + 3 — public per envelope × variant × viewport:
//   (1) brand tiles present, count/order, logo decoded or name-fallback
//   (2) asset envelope A06 (assets once, no dup, bounded img height, no doc overflow)
//   (3) V02 view-all anchor truth (grid/carousel present, beauty_tabs absent)
// ---------------------------------------------------------------------------
async function phase3PublicMatrix(fx, envelopes) {
  const expectedSlugs = fx.brand_slugs || null; // may be absent; we derive order from hrefs

  await phase3FamilyPublicMatrix({
    errorSource: 'public',
    viewports: PHASE3_VIEWPORTS,
    envelopes,
    variants: fx.variants,
    state: phase3,
    cssHomeOnlyNote: 'brand CSS must come from storefront_builder.css',
    screenshotFamily: 'brand',
    imgSelector: 'a.brand-tile img',
    tileSelector: 'a.brand-tile',
    tileCountFor: () => fx.brand_ids.length,
    exactTileCount: true,
    imgObjectFitExpected: 'contain',
    containerSelFor: (variant) => BRAND_VARIANT_CONTAINER[variant],

    // Home also carries the BASE fixture's brand_carousel (a 2-brand grid
    // mutated by scenarios 06/07). Disambiguate the phase3 section by its
    // full five-brand tile count (never by DOM position).
    selectSection: async (pubPage, variant) => {
      const candidates = brandSectionLocatorFor(pubPage, variant);
      const candCount = await candidates.count();
      assert(candCount >= 1, `no brand_carousel section found for variant ${variant}`);
      for (let i = 0; i < candCount; i += 1) {
        const cand = candidates.nth(i);
        const n = await cand.locator('a.brand-tile').count();
        if (n === fx.brand_ids.length) return cand;
      }
      return null;
    },

    extractTileData: (els) => els.map((a) => {
      const img = a.querySelector('img');
      const nameSpan = a.querySelector('.brand-tile-name');
      const href = a.getAttribute('href') || '';
      const brandParam = (href.split('?brand=')[1] || '').split('&')[0];
      return {
        href,
        brandSlug: decodeURIComponent(brandParam),
        hasImg: Boolean(img),
        imgComplete: img ? img.complete : null,
        imgNaturalWidth: img ? img.naturalWidth : null,
        hasNameFallback: Boolean(nameSpan),
        nameText: nameSpan ? nameSpan.textContent.trim() : null,
        imgHeightPx: img ? Math.round(img.getBoundingClientRect().height) : null,
        imgComputedMaxHeight: img ? getComputedStyle(img).maxHeight : null,
      };
    }),

    // Logo decode OR name-fallback: every tile is either a decoded img
    // (complete && naturalWidth>0) or a name-fallback span. At least one
    // tile must be the no-logo name-fallback (the deliberate brand).
    classifyTiles: (tileData, { env, vp, variant }) => {
      const slugOrder = tileData.map((t) => t.brandSlug);
      let decodedImgs = 0;
      let nameFallbacks = 0;
      let boundedImgSample = null;
      for (const t of tileData) {
        if (t.hasImg) {
          assert(t.imgComplete === true && t.imgNaturalWidth > 0, `${env.label} @${vp.name} ${variant}: brand logo <img> did not decode (complete=${t.imgComplete}, naturalWidth=${t.imgNaturalWidth}) href=${t.href}`);
          decodedImgs += 1;
          // Bounded height: the storefront_builder.css rule caps
          // .brand-tile img (max-height ~40-48px). Prove the rendered
          // height is bounded (not the 48px natural image height blown up)
          // — a small logo rendered under CSS control stays <= ~120px.
          assert(t.imgHeightPx !== null && t.imgHeightPx > 0 && t.imgHeightPx <= 120, `${env.label} @${vp.name} ${variant}: brand logo rendered height ${t.imgHeightPx}px is not bounded by CSS`);
          if (boundedImgSample === null) boundedImgSample = { heightPx: t.imgHeightPx, computedMaxHeight: t.imgComputedMaxHeight };
        } else {
          assert(t.hasNameFallback && t.nameText, `${env.label} @${vp.name} ${variant}: tile with no logo must render a .brand-tile-name fallback`);
          nameFallbacks += 1;
        }
      }
      assert(nameFallbacks >= 1, `${env.label} @${vp.name} ${variant}: expected at least one no-logo name-fallback tile, got ${nameFallbacks}`);
      assert(boundedImgSample, `${env.label} @${vp.name} ${variant}: expected at least one decoded logo image to sample computed height`);
      return { slugOrder, decodedCount: decodedImgs, extraFields: { name_fallbacks: nameFallbacks, bounded_img_sample: boundedImgSample } };
    },

    // ---- V02 view-all anchor truth ----
    afterClassify: async (section, { env, vp, variant }) => {
      const moreCount = await section.locator('a.more').count();
      if (variant === 'beauty_tabs') {
        assert(moreCount === 0, `${env.label} @${vp.name} beauty_tabs: must NOT render a View-all anchor, found ${moreCount}`);
        phase3.v02_anchor.push({ envelope: env.key, viewport: vp.name, variant, present: false });
      } else {
        assert(moreCount === 1, `${env.label} @${vp.name} ${variant}: expected exactly one View-all anchor, found ${moreCount}`);
        const moreHref = await section.locator('a.more').first().getAttribute('href');
        assert(moreHref && moreHref.includes(fx.view_all_url_path), `${env.label} @${vp.name} ${variant}: View-all href "${moreHref}" does not resolve to expected destination "${fx.view_all_url_path}"`);
        phase3.v02_anchor.push({ envelope: env.key, viewport: vp.name, variant, present: true, href: moreHref });
      }
    },

    // Layout mismatch on Brand is a hard failure (never observed in
    // practice; unlike Collection, no pre-existing CSS-cascade gap is
    // documented for Brand, so nothing here should ever throw).
    onLayoutIssue: (finding) => {
      assert(false, `${finding.envelope}@${finding.viewport} ${finding.variant}: expected ${finding.expected}, got ${finding.actual}`);
    },

    // Cross-variant order equality on this envelope/viewport, plus the
    // expected-slug-order check when the fixture supplies one.
    afterVariants: (perVariantOrders, { env, vp }) => {
      for (let i = 1; i < perVariantOrders.length; i += 1) {
        assert(JSON.stringify(perVariantOrders[i].slugOrder) === JSON.stringify(perVariantOrders[0].slugOrder), `${env.label} @${vp.name}: brand order differs across variants: ${JSON.stringify(perVariantOrders.map((r) => r.slugOrder))}`);
      }
      if (expectedSlugs) {
        assert(JSON.stringify(perVariantOrders[0].slugOrder) === JSON.stringify(expectedSlugs), `${env.label} @${vp.name}: brand order ${JSON.stringify(perVariantOrders[0].slugOrder)} != expected ${JSON.stringify(expectedSlugs)}`);
      }
    },
  });
}

// ---------------------------------------------------------------------------
// Scenario group 4 — wrapper replacement (harness projection) in the Preview
// iframe. Discover the brand section data-section-id, fetch the Preview HTML,
// extract the matching [data-section-id] wrapper, replace the existing one in
// the DOM 3 times. Assert brand anchor hrefs list is identical before/after
// and the count of stylesheet/script asset tags is unchanged (assets don't
// multiply). Scripts from fetched markup are NOT executed.
// ---------------------------------------------------------------------------
async function phase3WrapperProjection() {
  // Reuse the admin `page` (scenarios 01-13 are done). Navigate to the R4
  // editor fresh so the Preview iframe is in a known state.
  await withExpectedNavigation(() => page.goto(manifest.builder_url, { waitUntil: 'domcontentloaded', timeout: 20000 }));
  await page.locator('[data-r4-shell]').waitFor({ state: 'visible', timeout: 15000 });

  const frame = await previewFrame();
  const sectionId = await discoverSectionIdFromPreview('brand_carousel');
  assert(sectionId, 'Could not discover a brand_carousel data-section-id in Preview');

  // Baseline: brand anchor hrefs inside this wrapper + page-wide asset count.
  const readState = async () => frame.evaluate((id) => {
    const wrapper = document.querySelector(`[data-section-id="${id}"]`);
    const hrefs = wrapper ? Array.from(wrapper.querySelectorAll('a.brand-tile')).map((a) => a.getAttribute('href')) : [];
    const assetCount = document.querySelectorAll('link[rel=stylesheet], script[src]').length;
    const wrapperCount = document.querySelectorAll(`[data-section-id="${id}"]`).length;
    return { hrefs, assetCount, wrapperCount };
  }, sectionId);

  const before = await readState();
  assert(before.hrefs.length >= 2, `Expected the Preview brand wrapper to contain brand anchors, got ${before.hrefs.length}`);
  assert(before.wrapperCount === 1, `Expected exactly one brand wrapper in Preview, got ${before.wrapperCount}`);

  // Fetch the full Preview HTML (same-origin, credentialed) and parse it with
  // DOMParser (which does NOT execute scripts), extract the matching wrapper,
  // and replace the live one — 3 times. This is a harness projection: we
  // deliberately re-inject the server-rendered wrapper markup.
  const projection = await frame.evaluate(async (id) => {
    const res = await fetch(location.href, { credentials: 'same-origin' });
    const text = await res.text();
    const doc = new DOMParser().parseFromString(text, 'text/html');
    const fresh = doc.querySelector(`[data-section-id="${id}"]`);
    if (!fresh) return { ok: false, reason: 'no matching wrapper in fetched HTML' };
    const freshHtml = fresh.outerHTML;
    for (let i = 0; i < 3; i += 1) {
      const live = document.querySelector(`[data-section-id="${id}"]`);
      if (!live) return { ok: false, reason: `live wrapper missing on iteration ${i}` };
      const holder = document.createElement('div');
      holder.innerHTML = freshHtml; // parses markup; inline scripts not executed on innerHTML assignment
      const replacement = holder.firstElementChild;
      live.replaceWith(replacement);
    }
    return { ok: true };
  }, sectionId);
  assert(projection.ok, `Wrapper projection failed: ${projection.reason}`);

  const after = await readState();
  assert(JSON.stringify(after.hrefs) === JSON.stringify(before.hrefs), `Brand anchor hrefs changed after wrapper projection:\nbefore=${JSON.stringify(before.hrefs)}\nafter=${JSON.stringify(after.hrefs)}`);
  assert(after.assetCount === before.assetCount, `Asset tags multiplied after wrapper projection: before=${before.assetCount} after=${after.assetCount}`);
  assert(after.wrapperCount === 1, `Expected exactly one brand wrapper after projection, got ${after.wrapperCount}`);

  const dir = mkReportDir('wrapper_projection');
  const shotPath = path.join(dir, 'preview-after-3x-replacement.png');
  await page.screenshot({ path: shotPath });
  phase3.screenshots.push(shotPath);

  phase3.wrapper_projection.push({
    section_id: sectionId,
    replacements: 3,
    hrefs_before: before.hrefs,
    hrefs_after: after.hrefs,
    asset_count_before: before.assetCount,
    asset_count_after: after.assetCount,
    hrefs_identical: JSON.stringify(after.hrefs) === JSON.stringify(before.hrefs),
    assets_stable: after.assetCount === before.assetCount,
  });
}

// ---------------------------------------------------------------------------
// Scenario group 5 — real cart HTMX (V05/A04). Add a product, GET /cart/ per
// viewport, read the real hx-post URLs + item id from the DOM (never
// hard-coded), POST quantity update and item removal via the actual controls,
// assert the Brand section survives the HTMX swap, #cart-count OOB badge
// updates, and totals/quantities are correct.
// ---------------------------------------------------------------------------
async function phase3CartHtmx(fx) {
  const origin = manifest.public_url.replace(/\/+$/, '');
  for (const vp of PHASE3_VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
    await ctx.addCookies([manifest.session]);
    const cartPage = await ctx.newPage();
    const localErrors = [];
    cartPage.on('console', (m) => {
      if (m.type() !== 'error') return;
      const u = m.location()?.url || '';
      if (isExpectedBrokenImageNoise(u)) return; // Task 7 disposable broken-image fixture (auto-selected onto Cart too) — recorded separately
      localErrors.push({ text: m.text(), url: u, source: `cart:${vp.name}` });
    });
    cartPage.on('pageerror', (e) => localErrors.push({ text: String(e.message || e), source: `cart:${vp.name}` }));
    cartPage.on('requestfailed', (r) => {
      const u = r.url();
      if (u.startsWith('data:') || /\/favicon\.ico(\?|$)/i.test(u) || isExpectedBrokenImageNoise(u)) return;
      localErrors.push({ text: `requestfailed ${u}`, source: `cart:${vp.name}` });
    });
    const dir = mkReportDir('fragments', 'cart', vp.name);
    try {
      // Add a product to the cart via the real add endpoint. We read the CSRF
      // token from the product detail page and POST through the browser's
      // fetch so the session cookie + CSRF are real (never hard-coding ids —
      // the product slug comes from the manifest fixture).
      const pdpUrl = `${origin}/products/${fx.product_slug}/`;
      await cartPage.goto(pdpUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });
      const added = await cartPage.evaluate(async (slug) => {
        const tokenEl = document.querySelector('input[name=csrfmiddlewaretoken]');
        const token = tokenEl ? tokenEl.value : (document.cookie.match(/csrftoken=([^;]+)/) || [])[1];
        const body = new URLSearchParams();
        body.set('quantity', '2');
        const res = await fetch(`/cart/add/${slug}/`, {
          method: 'POST',
          headers: { 'X-CSRFToken': token || '', 'HX-Request': 'true', 'Content-Type': 'application/x-www-form-urlencoded' },
          credentials: 'same-origin',
          body: body.toString(),
        });
        return { status: res.status };
      }, fx.product_slug);
      assert(added.status < 400, `Add-to-cart POST failed with status ${added.status}`);

      // GET the cart page — it renders storefront-builder sections for the
      // cart page type, so the Brand section must be present.
      await cartPage.goto(`${origin}/cart/`, { waitUntil: 'networkidle', timeout: 20000 });

      const brandBefore = await cartPage.evaluate(() => {
        const sec = document.querySelector('#cart-container a.brand-tile');
        const tiles = Array.from(document.querySelectorAll('#cart-container a.brand-tile'));
        return { present: Boolean(sec), tileCount: tiles.length, hrefs: tiles.map((a) => a.getAttribute('href')) };
      });
      assert(brandBefore.present && brandBefore.tileCount >= 2, `Cart page must render the Brand section (found ${brandBefore.tileCount} tiles)`);

      // Read the REAL hx-post URLs + item id from the DOM (never hard-coded).
      const cartDom = await cartPage.evaluate(() => {
        const items = Array.from(document.querySelectorAll('#cart-container .citem'));
        const first = items[0];
        const readHx = (sel) => { const el = first ? first.querySelector(sel) : null; return el ? el.getAttribute('hx-post') : null; };
        // The + stepper button (increment) — the LAST stepper button.
        const steppers = first ? Array.from(first.querySelectorAll('.stepper button[hx-post]')) : [];
        const incUrl = steppers.length ? steppers[steppers.length - 1].getAttribute('hx-post') : null;
        const removeUrl = readHx('button.rm');
        const badge = document.querySelector('#cart-count');
        return {
          itemCount: items.length,
          incUrl,
          removeUrl,
          badgeText: badge ? badge.textContent.trim() : null,
        };
      });
      assert(cartDom.itemCount >= 1, `Cart must have at least one line item, got ${cartDom.itemCount}`);
      assert(cartDom.incUrl && /\/cart\/items\/\d+\/update\/$/.test(cartDom.incUrl), `Could not read a real quantity-update hx-post URL, got ${cartDom.incUrl}`);
      assert(cartDom.removeUrl && /\/cart\/items\/\d+\/remove\/$/.test(cartDom.removeUrl), `Could not read a real item-remove hx-post URL, got ${cartDom.removeUrl}`);
      const itemId = cartDom.incUrl.match(/\/cart\/items\/(\d+)\/update\//)[1];

      await cartPage.screenshot({ path: path.join(dir, 'before.png') });

      // ---- Quantity UPDATE via the real form/URL ----
      const updated = await cartPage.evaluate(async (args) => {
        const token = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1];
        const body = new URLSearchParams(); body.set('quantity', String(args.qty));
        const res = await fetch(args.url, {
          method: 'POST',
          headers: { 'X-CSRFToken': token || '', 'HX-Request': 'true', 'Content-Type': 'application/x-www-form-urlencoded' },
          credentials: 'same-origin',
          body: body.toString(),
        });
        const html = await res.text();
        // Apply the swap the way HTMX would: innerHTML of #cart-container,
        // and process any hx-swap-oob nodes into the header badge.
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const oob = doc.querySelector('#cart-count[hx-swap-oob]');
        const container = document.querySelector('#cart-container');
        // Separate OOB nodes from main content, mirroring htmx.
        Array.from(doc.body.querySelectorAll('[hx-swap-oob]')).forEach((n) => n.remove());
        container.innerHTML = doc.body.innerHTML;
        const badge = document.querySelector('#cart-count');
        if (oob && badge) badge.textContent = oob.textContent;
        return { status: res.status };
      }, { url: cartDom.incUrl, qty: 3 });
      assert(updated.status < 400, `Quantity update POST failed: ${updated.status}`);

      const afterUpdate = await cartPage.evaluate(() => {
        const brand = Array.from(document.querySelectorAll('#cart-container a.brand-tile'));
        const qtyInput = document.querySelector('#cart-container .citem .stepper input');
        const badge = document.querySelector('#cart-count');
        return {
          brandTiles: brand.length,
          brandHrefs: brand.map((a) => a.getAttribute('href')),
          qtyText: qtyInput ? qtyInput.value : null,
          badgeText: badge ? badge.textContent.trim() : null,
        };
      });
      assert(afterUpdate.brandTiles === brandBefore.tileCount, `Brand section lost tiles after HTMX update: before=${brandBefore.tileCount} after=${afterUpdate.brandTiles}`);
      assert(JSON.stringify(afterUpdate.brandHrefs) === JSON.stringify(brandBefore.hrefs), `Brand tile order/source changed after HTMX update`);
      await cartPage.screenshot({ path: path.join(dir, 'update.png') });

      // ---- Item REMOVE via the real form/URL ----
      const removed = await cartPage.evaluate(async (url) => {
        const token = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1];
        const res = await fetch(url, {
          method: 'POST',
          headers: { 'X-CSRFToken': token || '', 'HX-Request': 'true', 'Content-Type': 'application/x-www-form-urlencoded' },
          credentials: 'same-origin',
          body: '',
        });
        const html = await res.text();
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const oob = doc.querySelector('#cart-count[hx-swap-oob]');
        const container = document.querySelector('#cart-container');
        Array.from(doc.body.querySelectorAll('[hx-swap-oob]')).forEach((n) => n.remove());
        container.innerHTML = doc.body.innerHTML;
        const badge = document.querySelector('#cart-count');
        if (oob && badge) badge.textContent = oob.textContent;
        return { status: res.status };
      }, cartDom.removeUrl);
      assert(removed.status < 400, `Item remove POST failed: ${removed.status}`);

      const afterRemove = await cartPage.evaluate(() => {
        const items = Array.from(document.querySelectorAll('#cart-container .citem'));
        const badge = document.querySelector('#cart-count');
        return { itemCount: items.length, badgeText: badge ? badge.textContent.trim() : null };
      });
      assert(afterRemove.itemCount === 0, `Cart line item should be removed after remove POST, still ${afterRemove.itemCount}`);
      await cartPage.screenshot({ path: path.join(dir, 'remove.png') });

      phase3.cart_htmx.push({
        viewport: vp.name,
        item_id: itemId,
        inc_url: cartDom.incUrl,
        remove_url: cartDom.removeUrl,
        badge_before: cartDom.badgeText,
        badge_after_update: afterUpdate.badgeText,
        badge_after_remove: afterRemove.badgeText,
        qty_after_update: afterUpdate.qtyText,
        brand_tiles_before: brandBefore.tileCount,
        brand_tiles_after_update: afterUpdate.brandTiles,
        brand_hrefs_stable: JSON.stringify(afterUpdate.brandHrefs) === JSON.stringify(brandBefore.hrefs),
        item_count_after_remove: afterRemove.itemCount,
      });
      phase3.screenshots.push(path.join(dir, 'before.png'), path.join(dir, 'update.png'), path.join(dir, 'remove.png'));
    } finally {
      if (localErrors.length) phase3.errors.push(...localErrors);
      try { await ctx.close(); } catch (_error) { /* best effort */ }
    }
  }
}

// =============================================================================
// Phase 3 (opt-in) — Task 5 "Collection gate" real browser certification.
//
// Purely additive (same lifecycle/publish as the Brand gate — both sections
// were placed on the SAME Draft and published together in Scenario 10). Reads
// ids/slugs from manifest.phase3_fixture.collection (never hard-coded).
//
// Exercises, for EACH of the three PHASE3_VIEWPORTS and EACH envelope where a
// collection_tiles was placed (home / product_detail / listing / search /
// collection / cart), and for BOTH tile_style variants (grid / carousel):
//   (1) collection tiles present (a.pcard[href*="/collections/"]), count/order
//       (newest-first, deterministic newest collection FIRST),
//   (2) each tile's cover image decoded OR the folder-glyph fallback shown,
//   (3) asset envelope (storefront_builder.css / htmx / alpine once; no dup;
//       no home.css on non-home; no document horizontal overflow),
// plus a `/collections/<newest-slug>/?page=2` fetch asserting the domain
// visible-membership + shared product cards + NO HTMX branch, and a real Cart
// HTMX action with collection_tiles placed (tiles survive the swap; totals
// unchanged). All metrics recorded to metrics.json.
// =============================================================================

// Public collection_tiles container class per variant.
const COLLECTION_VARIANT_CONTAINER = {
  grid: '.grid.g4',
  carousel: '.collection-tiles-carousel.tiles-carousel',
};

function phase3CollectionFixture() {
  const fx = manifest.phase3_fixture;
  assert(fx && typeof fx === 'object', 'manifest.phase3_fixture is missing');
  const c = fx.collection;
  assert(c && typeof c === 'object', 'phase3_fixture.collection missing — the Collection gate fixture was not threaded into the manifest');
  assert(c.tiles_section_ids && typeof c.tiles_section_ids === 'object', 'phase3_fixture.collection.tiles_section_ids missing');
  assert(Array.isArray(c.tile_variants) && c.tile_variants.length === 2, 'phase3_fixture.collection.tile_variants must list the 2 tile_style variants');
  assert(typeof c.newest_collection_slug === 'string' && c.newest_collection_slug, 'collection.newest_collection_slug missing');
  assert(typeof c.page2_collection_slug === 'string' && c.page2_collection_slug, 'collection.page2_collection_slug missing');
  assert(typeof c.product_slug === 'string' && c.product_slug, 'collection.product_slug missing');
  assert(typeof c.broken_collection_slug === 'string' && c.broken_collection_slug, 'collection.broken_collection_slug missing (Task 7 disposable broken-image fixture)');
  return c;
}

function phase3CollectionEnvelopes(fx, c) {
  const origin = manifest.public_url.replace(/\/+$/, '');
  return [
    { key: 'home', label: 'C-E1-home', url: `${origin}/` },
    { key: 'product_detail', label: 'C-E2-product_detail', url: `${origin}/products/${c.product_slug}/` },
    { key: 'listing', label: 'C-E3-listing', url: `${origin}/products/` },
    { key: 'search', label: 'C-E4-search', url: `${origin}/products/?q=${encodeURIComponent('کالا')}` },
    { key: 'collection', label: 'C-E5-collection', url: `${origin}/collections/${c.newest_collection_slug}/` },
    { key: 'cart', label: 'C-E6-cart', url: `${origin}/cart/` },
  ];
}

// Locate the collection_tiles <section> for a given tile_style variant on a
// PUBLIC page. grid => a `.grid.g4` inner container; carousel => the
// `.collection-tiles-carousel.tiles-carousel` container. Both hold
// a.pcard[href*="/collections/"] (collection-detail links), which
// distinguishes them from a product grid (whose pcards link to /products/).
function collectionSectionLocatorFor(targetPage, variant) {
  return targetPage.locator(
    `section.section:has(> ${COLLECTION_VARIANT_CONTAINER[variant]} a.pcard[href*="/collections/"])`,
  );
}

async function phase3CollectionPublicMatrix(c, envelopes) {
  await phase3FamilyPublicMatrix({
    errorSource: 'coll-public',
    viewports: PHASE3_VIEWPORTS,
    envelopes,
    variants: c.tile_variants,
    state: phase3.collection,
    cssHomeOnlyNote: 'collection carousel CSS must come from storefront_builder.css',
    screenshotFamily: 'collection',
    imgSelector: 'a.pcard .img img',
    tileSelector: 'a.pcard[href*="/collections/"]',
    tileCountFor: () => 2,
    exactTileCount: false,
    imgObjectFitExpected: 'cover',
    containerSelFor: (variant) => COLLECTION_VARIANT_CONTAINER[variant],

    selectSection: async (pubPage, variant) => {
      const candidates = collectionSectionLocatorFor(pubPage, variant);
      const candCount = await candidates.count();
      assert(candCount >= 1, `no collection_tiles section found for variant ${variant}`);
      return candidates.first();
    },

    extractTileData: (els) => els.map((a) => {
      const img = a.querySelector('.img img');
      const glyph = a.querySelector('.img .emo');
      const nameEl = a.querySelector('.name');
      const rateEl = a.querySelector('.rate');
      const href = a.getAttribute('href') || '';
      const slugMatch = href.match(/\/collections\/([^/]+)\//);
      return {
        href,
        slug: slugMatch ? decodeURIComponent(slugMatch[1]) : null,
        hasImg: Boolean(img),
        imgComplete: img ? img.complete : null,
        imgNaturalWidth: img ? img.naturalWidth : null,
        hasGlyph: Boolean(glyph),
        name: nameEl ? nameEl.textContent.trim() : null,
        rate: rateEl ? rateEl.textContent.trim() : null,
      };
    }),

    // Order: auto (newest-first) => the deterministic-newest collection is
    // the FIRST tile. Every tile: cover image decoded OR folder-glyph
    // fallback — except the Task 7 disposable broken-image collection,
    // which is recorded separately (per spec: "record browser network
    // failure; do not equate no-image with broken-image").
    classifyTiles: (tileData, { env, vp, variant }) => {
      const slugOrder = tileData.map((t) => t.slug);
      assert(slugOrder[0] === c.newest_collection_slug, `${env.label} @${vp.name} ${variant}: newest collection "${c.newest_collection_slug}" is not first, order=${JSON.stringify(slugOrder)}`);

      let decoded = 0;
      let glyphs = 0;
      for (const t of tileData) {
        if (c.broken_collection_slug && t.slug === c.broken_collection_slug) {
          phase3.collection.broken_image_records = phase3.collection.broken_image_records || [];
          phase3.collection.broken_image_records.push({
            envelope: env.key, viewport: vp.name, variant, href: t.href,
            img_complete: t.imgComplete, img_natural_width: t.imgNaturalWidth,
          });
          continue;
        }
        if (t.hasImg) {
          assert(t.imgComplete === true && t.imgNaturalWidth > 0, `${env.label} @${vp.name} ${variant}: collection cover <img> did not decode (complete=${t.imgComplete}, naturalWidth=${t.imgNaturalWidth}) href=${t.href}`);
          decoded += 1;
        } else {
          assert(t.hasGlyph, `${env.label} @${vp.name} ${variant}: no-image tile must render the folder-glyph fallback (href=${t.href})`);
          glyphs += 1;
        }
      }
      // Both an image tile AND a folder-glyph fallback tile exist in the
      // auto listing (fixture guarantees one with a cover + one without).
      assert(decoded >= 1, `${env.label} @${vp.name} ${variant}: expected >=1 decoded cover image, got ${decoded}`);
      assert(glyphs >= 1, `${env.label} @${vp.name} ${variant}: expected >=1 folder-glyph fallback tile, got ${glyphs}`);
      return { slugOrder, decodedCount: decoded, extraFields: { glyph_fallbacks: glyphs } };
    },

    // Layout mismatch on Collection is a KNOWN RED finding (Task 7),
    // recorded rather than thrown, so the rest of this run's evidence is
    // still collected — the end-of-gate assertion in phase3BrandGate()
    // still fails the overall scenario. See the two notes below for why
    // each shape can legitimately diverge from Brand's on this envelope.
    onLayoutIssue: (finding) => {
      const isGrid = finding.variant === 'grid';
      phase3.collection.known_red_findings.push({
        ...finding,
        note: isGrid
          ? 'Collection grid container has no display:grid (or no resolved column tracks) on this envelope (base .grid rule lives in product_card.css, which this envelope does not load; no inline template fallback exists).'
          : 'Collection carousel container has no display:flex/overflow-x:auto on this non-Home envelope (missing base .tiles-carousel rule in storefront_builder.css; home.css is not loaded here). Pre-existing Task 5 CSS-fix gap, not a Task 7 harness defect.',
      });
    },
  });
}

// `/collections/<newest-slug>/?page=2` — domain visible-membership + shared
// product cards + NO HTMX fragment branch (a full storefront envelope).
async function phase3CollectionPage2(c) {
  const origin = manifest.public_url.replace(/\/+$/, '');
  const url = `${origin}/collections/${c.page2_collection_slug}/?page=2`;
  const ctx = await browser.newContext({ viewport: { width: PHASE3_VIEWPORTS[0].width, height: PHASE3_VIEWPORTS[0].height } });
  await ctx.addCookies([manifest.session]);
  const p = await ctx.newPage();
  try {
    // A normal (non-HX) GET is a full page; an HX-Request header must NOT turn
    // it into a bare fragment (the collection detail view has no HX branch).
    const resp = await p.goto(url, { waitUntil: 'networkidle', timeout: 25000 });
    assert(resp && resp.status() < 400, `collection ?page=2 GET returned ${resp && resp.status()}`);

    const domain = await p.evaluate(() => {
      // Shared product card markup (catalog/partials/product_card.html) is
      // <article class="pcard">…<a class="pcard-hitarea" href="/products/<slug>/">…
      // — the `.pcard` itself is the <article>, NOT an <a>. The card's LINK
      // (the "shared product card that links to a product") is
      // a.pcard-hitarea[href*="/products/"]. (The collection-TILE selector
      // a.pcard[href*="/collections/"] is a genuinely different element — a
      // tile IS an <a class="pcard"> — and stays as-is elsewhere.)
      const productCards = Array.from(document.querySelectorAll('a.pcard-hitarea[href*="/products/"]'));
      const currentPage = document.querySelector('.pagination .current');
      const sbCss = Array.from(document.querySelectorAll('link[rel=stylesheet]')).some((l) => /storefront_builder\.css/.test(l.getAttribute('href') || ''));
      return {
        productCardCount: productCards.length,
        currentPageText: currentPage ? currentPage.textContent.trim() : null,
        hasFullEnvelope: sbCss,
      };
    });
    // Page 2 of a 13-visible-member collection holds the remaining member(s),
    // rendered via the SHARED product card (links to /products/).
    assert(domain.productCardCount >= 1, `collection ?page=2 must render shared product cards, got ${domain.productCardCount}`);
    // Full storefront envelope (NOT a bare HTMX fragment).
    assert(domain.hasFullEnvelope, 'collection ?page=2 must render the full storefront envelope (storefront_builder.css present) — no HTMX fragment branch');

    // Confirm no HX branch: an explicit HX-Request header still returns the
    // full page (same shell), not a partial.
    const hx = await p.evaluate(async (u) => {
      const res = await fetch(u, { headers: { 'HX-Request': 'true' }, credentials: 'same-origin' });
      const text = await res.text();
      return { status: res.status, hasHtml: /<html/i.test(text), hasSbCss: /storefront_builder\.css/.test(text) };
    }, url);
    assert(hx.status < 400, `collection ?page=2 HX GET returned ${hx.status}`);
    assert(hx.hasHtml && hx.hasSbCss, 'collection ?page=2 under HX-Request must STILL be the full page (no fragment branch)');

    const dir = mkReportDir('collection', 'page2');
    const shotPath = path.join(dir, 'page2.png');
    await p.screenshot({ path: shotPath });
    phase3.collection.screenshots.push(shotPath);
    phase3.collection.page2 = {
      url,
      product_card_count: domain.productCardCount,
      current_page_text: domain.currentPageText,
      full_envelope: domain.hasFullEnvelope,
      hx_still_full_page: hx.hasHtml && hx.hasSbCss,
    };
  } finally {
    try { await ctx.close(); } catch (_error) { /* best effort */ }
  }
}

// Real Cart HTMX with collection_tiles placed on the published cart page: the
// collection tiles must survive the swap and totals stay correct.
async function phase3CollectionCartHtmx(c) {
  const origin = manifest.public_url.replace(/\/+$/, '');
  const vp = PHASE3_VIEWPORTS[0];
  const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
  await ctx.addCookies([manifest.session]);
  const cartPage = await ctx.newPage();
  const localErrors = [];
  cartPage.on('pageerror', (e) => localErrors.push({ text: String(e.message || e), source: `coll-cart:${vp.name}` }));
  const dir = mkReportDir('collection', 'cart');
  try {
    const pdpUrl = `${origin}/products/${c.product_slug}/`;
    await cartPage.goto(pdpUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });
    const added = await cartPage.evaluate(async (slug) => {
      const tokenEl = document.querySelector('input[name=csrfmiddlewaretoken]');
      const token = tokenEl ? tokenEl.value : (document.cookie.match(/csrftoken=([^;]+)/) || [])[1];
      const body = new URLSearchParams(); body.set('quantity', '2');
      const res = await fetch(`/cart/add/${slug}/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': token || '', 'HX-Request': 'true', 'Content-Type': 'application/x-www-form-urlencoded' },
        credentials: 'same-origin',
        body: body.toString(),
      });
      return { status: res.status };
    }, c.product_slug);
    assert(added.status < 400, `Collection cart add-to-cart failed with status ${added.status}`);

    await cartPage.goto(`${origin}/cart/`, { waitUntil: 'networkidle', timeout: 20000 });
    const collBefore = await cartPage.evaluate(() => {
      const tiles = Array.from(document.querySelectorAll('#cart-container a.pcard[href*="/collections/"]'));
      return { tileCount: tiles.length, hrefs: tiles.map((a) => a.getAttribute('href')) };
    });
    assert(collBefore.tileCount >= 2, `Cart page must render the collection_tiles section (found ${collBefore.tileCount} tiles)`);

    const cartDom = await cartPage.evaluate(() => {
      const items = Array.from(document.querySelectorAll('#cart-container .citem'));
      const first = items[0];
      const steppers = first ? Array.from(first.querySelectorAll('.stepper button[hx-post]')) : [];
      const incUrl = steppers.length ? steppers[steppers.length - 1].getAttribute('hx-post') : null;
      const removeBtn = first ? first.querySelector('button.rm') : null;
      return { itemCount: items.length, incUrl, removeUrl: removeBtn ? removeBtn.getAttribute('hx-post') : null };
    });
    assert(cartDom.incUrl && /\/cart\/items\/\d+\/update\/$/.test(cartDom.incUrl), `Could not read a real quantity-update hx-post URL, got ${cartDom.incUrl}`);

    await cartPage.screenshot({ path: path.join(dir, 'before.png') });

    // Quantity update; collection tiles must survive the swap.
    const updated = await cartPage.evaluate(async (args) => {
      const token = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1];
      const body = new URLSearchParams(); body.set('quantity', String(args.qty));
      const res = await fetch(args.url, {
        method: 'POST',
        headers: { 'X-CSRFToken': token || '', 'HX-Request': 'true', 'Content-Type': 'application/x-www-form-urlencoded' },
        credentials: 'same-origin',
        body: body.toString(),
      });
      const html = await res.text();
      const doc = new DOMParser().parseFromString(html, 'text/html');
      const oob = doc.querySelector('#cart-count[hx-swap-oob]');
      const container = document.querySelector('#cart-container');
      Array.from(doc.body.querySelectorAll('[hx-swap-oob]')).forEach((n) => n.remove());
      container.innerHTML = doc.body.innerHTML;
      const badge = document.querySelector('#cart-count');
      if (oob && badge) badge.textContent = oob.textContent;
      return { status: res.status };
    }, { url: cartDom.incUrl, qty: 3 });
    assert(updated.status < 400, `Collection cart quantity update failed: ${updated.status}`);

    const afterUpdate = await cartPage.evaluate(() => {
      const tiles = Array.from(document.querySelectorAll('#cart-container a.pcard[href*="/collections/"]'));
      const qtyInput = document.querySelector('#cart-container .citem .stepper input');
      return { tileCount: tiles.length, hrefs: tiles.map((a) => a.getAttribute('href')), qtyText: qtyInput ? qtyInput.value : null };
    });
    assert(afterUpdate.tileCount === collBefore.tileCount, `Collection tiles lost after HTMX update: before=${collBefore.tileCount} after=${afterUpdate.tileCount}`);
    assert(JSON.stringify(afterUpdate.hrefs) === JSON.stringify(collBefore.hrefs), 'Collection tile order/source changed after HTMX update');
    await cartPage.screenshot({ path: path.join(dir, 'update.png') });

    phase3.collection.cart_htmx.push({
      viewport: vp.name,
      inc_url: cartDom.incUrl,
      coll_tiles_before: collBefore.tileCount,
      coll_tiles_after_update: afterUpdate.tileCount,
      coll_hrefs_stable: JSON.stringify(afterUpdate.hrefs) === JSON.stringify(collBefore.hrefs),
      qty_after_update: afterUpdate.qtyText,
    });
    phase3.collection.screenshots.push(path.join(dir, 'before.png'), path.join(dir, 'update.png'));
  } finally {
    if (localErrors.length) phase3.collection.errors.push(...localErrors);
    try { await ctx.close(); } catch (_error) { /* best effort */ }
  }
}

// ---------------------------------------------------------------------------
// Task 7 — E6 Collection index companion browser smoke. `/collections/` is a
// direct domain listing, NOT a pilot placement: it must carry NO
// storefront_builder.css (no Builder render_items projected there). This is
// browser-level confirmation of the boundary Task 5's Python tests already
// characterize (test_page_shell E6 boundary) — companion evidence, and
// explicitly NOT a substitute for E4 Collection detail.
// ---------------------------------------------------------------------------
async function phase3CollectionIndexCompanion() {
  const origin = manifest.public_url.replace(/\/+$/, '');
  const url = `${origin}/collections/`;
  const ctx = await browser.newContext({ viewport: { width: PHASE3_VIEWPORTS[0].width, height: PHASE3_VIEWPORTS[0].height } });
  await ctx.addCookies([manifest.session]);
  const p = await ctx.newPage();
  try {
    const resp = await p.goto(url, { waitUntil: 'networkidle', timeout: 25000 });
    assert(resp && resp.status() < 400, `Collection index companion GET returned ${resp && resp.status()}`);
    const boundary = await p.evaluate(() => {
      const styles = Array.from(document.querySelectorAll('link[rel=stylesheet]')).map((l) => l.getAttribute('href') || '');
      return {
        sb_css: styles.filter((h) => /storefront_builder\.css/.test(h)).length,
        product_list_css: styles.filter((h) => /product_list\.css/.test(h)).length,
      };
    });
    assert(boundary.sb_css === 0, `Collection index companion must NOT load storefront_builder.css (E6 is a direct listing, no pilot placement) — found ${boundary.sb_css}`);
    const dir = mkReportDir('collection-index');
    const shotPath = path.join(dir, 'index-companion.png');
    await p.screenshot({ path: shotPath });
    phase3.collection.index_companion = {
      url, status: resp.status(), sb_css: boundary.sb_css, product_list_css: boundary.product_list_css,
      screenshot: shotPath, note: 'E6 companion — no pilot placement; does not substitute for E4 Collection detail.',
    };
    phase3.collection.screenshots.push(shotPath);
  } finally {
    try { await ctx.close(); } catch (_error) { /* best effort */ }
  }
}

async function phase3CollectionGate() {
  const c = phase3CollectionFixture();
  const envelopes = phase3CollectionEnvelopes(manifest.phase3_fixture, c);
  await phase3CollectionPublicMatrix(c, envelopes);
  await phase3CollectionPage2(c);
  await phase3CollectionCartHtmx(c);
  await phase3CollectionIndexCompanion();
  phase3.collection.finished_at = new Date().toISOString();
  // Deliberately NOT asserted here — a throw would abort phase3BrandGate()
  // before it reaches the combined-cart proof or writes metrics.json. The
  // gating assertion runs at the very end of phase3BrandGate(), inside a
  // try/finally that writes metrics.json regardless of outcome, so a known
  // RED finding still fails the overall scenario without losing evidence.
}

// ---------------------------------------------------------------------------
// Task 7 — Brand broken-image disposable fixture. Isolated on the SEARCH
// envelope (never visited by phase3PublicMatrix's five certified Brand
// envelopes: home/product_detail/listing/collection/cart), this proves the
// browser's DEFINED DEGRADED STATE for a logo <img> whose src resolves to a
// file never written to storage — distinct from the no-logo
// (`.brand-tile-name`) fallback already certified above. Recorded
// separately; not asserted to succeed (no onerror fallback exists per the
// inventory), and its request failure is excluded from the zero-error pools.
// ---------------------------------------------------------------------------
async function phase3BrandBrokenImage(fx) {
  const origin = manifest.public_url.replace(/\/+$/, '');
  const url = `${origin}/products/?q=${encodeURIComponent('کالا')}`;
  const ctx = await browser.newContext({ viewport: { width: PHASE3_VIEWPORTS[0].width, height: PHASE3_VIEWPORTS[0].height } });
  await ctx.addCookies([manifest.session]);
  const p = await ctx.newPage();
  const requestFailures = [];
  p.on('requestfailed', (r) => requestFailures.push(r.url()));
  try {
    const resp = await p.goto(url, { waitUntil: 'networkidle', timeout: 25000 });
    assert(resp && resp.status() < 400, `Brand broken-image search envelope GET returned ${resp && resp.status()}`);
    const tiles = p.locator('a.brand-tile');
    assert(await tiles.count() === 1, `Expected exactly one isolated broken-image brand tile on the search envelope, got ${await tiles.count()}`);
    const state = await tiles.first().evaluate((a) => {
      const img = a.querySelector('img');
      return img ? { hasImg: true, complete: img.complete, naturalWidth: img.naturalWidth, src: img.getAttribute('src') } : { hasImg: false };
    });
    const brokenRequestFailed = requestFailures.some((u) => /qa-broken-nonexistent/i.test(u));
    const dir = mkReportDir('brand', 'broken-image');
    const shotPath = path.join(dir, 'search.png');
    await p.screenshot({ path: shotPath });
    phase3.screenshots.push(shotPath);
    phase3.broken_image = {
      envelope: 'search', url,
      has_img_tag: state.hasImg, img_src: state.src ?? null,
      img_complete: state.complete ?? null, img_natural_width: state.naturalWidth ?? null,
      request_failed_observed: brokenRequestFailed,
      note: 'Disposable QA fixture: logo FieldFile points at a file never written to storage. No onerror fallback exists (per inventory); recorded separately, distinct from the no-image (.brand-tile-name) fallback case, and excluded from the zero-error assertion pools.',
    };
  } finally {
    try { await ctx.close(); } catch (_error) { /* best effort */ }
  }
}

// ---------------------------------------------------------------------------
// Task 7 — combined dual-pilot Cart proof. Brand (3 variants) and Collection
// (2 tile variants) are ALREADY placed together on the same published Cart
// page by the existing fixture (each in its own container/cell — every
// `place_variant`/`place_tiles_variant` call creates its own single-cell
// container), so this is a NEW verification pass over EXISTING data, not a
// fixture change. This is the canonical evidence at the exact paths Task 7
// names (`browser/fragments/cart/{viewport}/{before,update,remove}.png`),
// run AFTER the individual Brand-only (phase3CartHtmx) and Collection-only
// (phase3CollectionCartHtmx) flows, which remain unchanged and still pass.
// ---------------------------------------------------------------------------
async function phase3CombinedCartHtmx(fx, c) {
  const origin = manifest.public_url.replace(/\/+$/, '');
  for (const vp of PHASE3_VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
    await ctx.addCookies([manifest.session]);
    const cartPage = await ctx.newPage();
    const localErrors = [];
    cartPage.on('console', (m) => {
      if (m.type() !== 'error') return;
      const u = m.location()?.url || '';
      if (isExpectedBrokenImageNoise(u)) return; // Task 7 disposable broken-image fixture (auto-selected onto Cart too) — recorded separately
      localErrors.push({ text: m.text(), url: u, source: `combined-cart:${vp.name}` });
    });
    cartPage.on('pageerror', (e) => localErrors.push({ text: String(e.message || e), source: `combined-cart:${vp.name}` }));
    cartPage.on('requestfailed', (r) => {
      const u = r.url();
      if (u.startsWith('data:') || /\/favicon\.ico(\?|$)/i.test(u) || isExpectedBrokenImageNoise(u)) return;
      localErrors.push({ text: `requestfailed ${u}`, source: `combined-cart:${vp.name}` });
    });
    const dir = mkReportDir('fragments', 'cart', vp.name);
    try {
      const pdpUrl = `${origin}/products/${fx.product_slug}/`;
      await cartPage.goto(pdpUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });
      const added = await cartPage.evaluate(async (slug) => {
        const tokenEl = document.querySelector('input[name=csrfmiddlewaretoken]');
        const token = tokenEl ? tokenEl.value : (document.cookie.match(/csrftoken=([^;]+)/) || [])[1];
        const body = new URLSearchParams(); body.set('quantity', '1');
        const res = await fetch(`/cart/add/${slug}/`, {
          method: 'POST',
          headers: { 'X-CSRFToken': token || '', 'HX-Request': 'true', 'Content-Type': 'application/x-www-form-urlencoded' },
          credentials: 'same-origin',
          body: body.toString(),
        });
        return { status: res.status };
      }, fx.product_slug);
      assert(added.status < 400, `Combined cart add-to-cart failed with status ${added.status}`);

      await cartPage.goto(`${origin}/cart/`, { waitUntil: 'networkidle', timeout: 20000 });
      const readBoth = () => cartPage.evaluate(() => {
        const brand = Array.from(document.querySelectorAll('#cart-container a.brand-tile'));
        const coll = Array.from(document.querySelectorAll('#cart-container a.pcard[href*="/collections/"]'));
        // Structural distinctness (no editor container/cell hooks on Public,
        // by design): the Brand and Collection sections must be independent,
        // non-nested sibling <section> ancestors — proving distinct
        // placement without relying on any editor-only identity attribute.
        const brandSections = new Set(brand.map((a) => a.closest('section.section')));
        const collSections = new Set(coll.map((a) => a.closest('section.section')));
        const overlap = [...brandSections].some((s) => collSections.has(s));
        return {
          brandCount: brand.length, collCount: coll.length,
          brandHrefs: brand.map((a) => a.getAttribute('href')),
          collHrefs: coll.map((a) => a.getAttribute('href')),
          brandSectionCount: brandSections.size, collSectionCount: collSections.size,
          sectionsOverlap: overlap,
        };
      });

      const before = await readBoth();
      assert(before.brandCount >= 2, `Combined cart: expected Brand tiles present, got ${before.brandCount}`);
      assert(before.collCount >= 2, `Combined cart: expected Collection tiles present, got ${before.collCount}`);
      assert(before.brandSectionCount >= 1 && before.collSectionCount >= 1, 'Combined cart: expected at least one Brand section and one Collection section');
      assert(!before.sectionsOverlap, 'Combined cart: Brand and Collection tiles resolved to the SAME <section> — distinct container/cell placement violated');

      const cartDom = await cartPage.evaluate(() => {
        const items = Array.from(document.querySelectorAll('#cart-container .citem'));
        const first = items[0];
        const steppers = first ? Array.from(first.querySelectorAll('.stepper button[hx-post]')) : [];
        const incUrl = steppers.length ? steppers[steppers.length - 1].getAttribute('hx-post') : null;
        const removeBtn = first ? first.querySelector('button.rm') : null;
        return { itemCount: items.length, incUrl, removeUrl: removeBtn ? removeBtn.getAttribute('hx-post') : null };
      });
      assert(cartDom.incUrl && /\/cart\/items\/\d+\/update\/$/.test(cartDom.incUrl), `Combined cart: could not read a real quantity-update hx-post URL, got ${cartDom.incUrl}`);
      assert(cartDom.removeUrl && /\/cart\/items\/\d+\/remove\/$/.test(cartDom.removeUrl), `Combined cart: could not read a real item-remove hx-post URL, got ${cartDom.removeUrl}`);

      await cartPage.screenshot({ path: path.join(dir, 'before.png') });

      const applySwap = (html) => {
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const oob = doc.querySelector('#cart-count[hx-swap-oob]');
        const container = document.querySelector('#cart-container');
        Array.from(doc.body.querySelectorAll('[hx-swap-oob]')).forEach((n) => n.remove());
        container.innerHTML = doc.body.innerHTML;
        const badge = document.querySelector('#cart-count');
        if (oob && badge) badge.textContent = oob.textContent;
      };

      const updated = await cartPage.evaluate(async (args) => {
        const token = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1];
        const body = new URLSearchParams(); body.set('quantity', String(args.qty));
        const res = await fetch(args.url, {
          method: 'POST',
          headers: { 'X-CSRFToken': token || '', 'HX-Request': 'true', 'Content-Type': 'application/x-www-form-urlencoded' },
          credentials: 'same-origin',
          body: body.toString(),
        });
        return { status: res.status, html: await res.text() };
      }, { url: cartDom.incUrl, qty: 2 });
      assert(updated.status < 400, `Combined cart quantity update failed: ${updated.status}`);
      await cartPage.evaluate(applySwap, updated.html);

      const afterUpdate = await readBoth();
      assert(afterUpdate.brandCount === before.brandCount, `Combined cart: Brand tiles lost after HTMX update (before=${before.brandCount} after=${afterUpdate.brandCount})`);
      assert(afterUpdate.collCount === before.collCount, `Combined cart: Collection tiles lost after HTMX update (before=${before.collCount} after=${afterUpdate.collCount})`);
      assert(JSON.stringify(afterUpdate.brandHrefs) === JSON.stringify(before.brandHrefs), 'Combined cart: Brand order/source changed after HTMX update');
      assert(JSON.stringify(afterUpdate.collHrefs) === JSON.stringify(before.collHrefs), 'Combined cart: Collection order/source changed after HTMX update');
      await cartPage.screenshot({ path: path.join(dir, 'update.png') });

      const removed = await cartPage.evaluate(async (url) => {
        const token = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1];
        const res = await fetch(url, {
          method: 'POST',
          headers: { 'X-CSRFToken': token || '', 'HX-Request': 'true', 'Content-Type': 'application/x-www-form-urlencoded' },
          credentials: 'same-origin',
          body: '',
        });
        return { status: res.status, html: await res.text() };
      }, cartDom.removeUrl);
      assert(removed.status < 400, `Combined cart item remove failed: ${removed.status}`);
      await cartPage.evaluate(applySwap, removed.html);

      const afterRemove = await cartPage.evaluate(() => {
        const items = Array.from(document.querySelectorAll('#cart-container .citem'));
        const brand = document.querySelectorAll('#cart-container a.brand-tile').length;
        const coll = document.querySelectorAll('#cart-container a.pcard[href*="/collections/"]').length;
        return { itemCount: items.length, brandCount: brand, collCount: coll };
      });
      assert(afterRemove.itemCount === 0, `Combined cart: line item should be removed, still ${afterRemove.itemCount}`);
      assert(afterRemove.brandCount === before.brandCount, 'Combined cart: Brand sections must survive even an emptied cart');
      assert(afterRemove.collCount === before.collCount, 'Combined cart: Collection sections must survive even an emptied cart');
      await cartPage.screenshot({ path: path.join(dir, 'remove.png') });

      phase3.combined_cart_htmx.push({
        viewport: vp.name,
        brand_tiles_before: before.brandCount, brand_tiles_after_update: afterUpdate.brandCount, brand_tiles_after_remove: afterRemove.brandCount,
        collection_tiles_before: before.collCount, collection_tiles_after_update: afterUpdate.collCount, collection_tiles_after_remove: afterRemove.collCount,
        distinct_sections: !before.sectionsOverlap,
        brand_section_count: before.brandSectionCount, collection_section_count: before.collSectionCount,
        item_count_after_remove: afterRemove.itemCount,
      });
      phase3.screenshots.push(path.join(dir, 'before.png'), path.join(dir, 'update.png'), path.join(dir, 'remove.png'));
    } finally {
      if (localErrors.length) phase3.errors.push(...localErrors);
      assert(localErrors.length === 0, `Combined cart console/page/request errors @${vp.name}: ${JSON.stringify(localErrors.slice(0, 6))}`);
      try { await ctx.close(); } catch (_error) { /* best effort */ }
    }
  }
}

// ---------------------------------------------------------------------------
// Task 4 — per-family gate registration. `manifest.phase3` (the ONE opt-in
// flag threaded through the Python command) still gates whether ANY of this
// runs at all; each entry below owns its own fixture-derived run() and
// contributes its own known-red findings to the ONE combined gate assertion
// at the end of phase3BrandGate(). A Task 6 family registers here — supplying
// its own run()/knownRedFindings() — instead of piggybacking on the Brand/
// Collection flag or hand-writing a parallel gate function.
// ---------------------------------------------------------------------------
const PHASE3_FAMILIES = [
  {
    key: 'brand',
    run: async (fx) => {
      const envelopes = phase3Envelopes(fx);
      await phase3PublicMatrix(fx, envelopes);
      await phase3WrapperProjection();
      await phase3CartHtmx(fx);
      await phase3BrandBrokenImage(fx);
    },
    // Brand's layout checks assert (throw) rather than record — see
    // phase3PublicMatrix's onLayoutIssue — so there is nothing to gate here;
    // kept for a uniform per-family shape as more families register.
    knownRedFindings: () => [],
  },
  {
    key: 'collection',
    run: async () => { await phase3CollectionGate(); },
    knownRedFindings: () => phase3.collection.known_red_findings,
  },
];

async function phase3BrandGate() {
  try {
    // The Python command writes tenant_negatives.json (the unauthenticated
    // Preview negative, via Django's test Client) into the report dir before
    // the browser even launches. Embed it into metrics.json too, rather than
    // leaving this field permanently null — the file itself remains the
    // authoritative copy.
    const tenantNegativesPath = path.join(manifest.report_dir, 'tenant_negatives.json');
    if (fs.existsSync(tenantNegativesPath)) {
      try { phase3.tenant_negatives = JSON.parse(fs.readFileSync(tenantNegativesPath, 'utf8')); } catch (_error) { /* best effort */ }
    }

    const fx = phase3Fixture();
    for (const family of PHASE3_FAMILIES) {
      await family.run(fx);
    }

    // Task 7 — combined dual-pilot Cart proof, run last so it is the
    // canonical evidence at the exact `browser/fragments/cart/{viewport}/*`
    // paths Task 7 names. Spans multiple families by design (proves they
    // coexist on one Cart page), so it stays outside the per-family loop.
    await phase3CombinedCartHtmx(fx, phase3CollectionFixture());
  } finally {
    // Metrics JSON alongside the browser result (screenshots ALONE
    // insufficient) — written even if a gating assertion below (or
    // anything above) throws, so a FAILED run still leaves full evidence.
    phase3.finished_at = new Date().toISOString();
    result.phase3_brand = phase3;
    fs.writeFileSync(path.join(manifest.report_dir, 'metrics.json'), JSON.stringify(phase3, null, 2), 'utf8');
  }

  // Gate the overall scenario on any known-red finding recorded by ANY
  // registered family above (non-fatally, so the try block could finish
  // collecting every other envelope/viewport/screenshot first). A Task 7
  // harness finding, not production code, decides PASS/FAIL here — see
  // phase3.collection.known_red_findings in metrics.json for the exact rows.
  const knownRed = PHASE3_FAMILIES.flatMap((family) => family.knownRedFindings());
  assert(
    knownRed.length === 0,
    `Task 7 found ${knownRed.length} known RED finding(s) across registered families — see metrics.json: ${JSON.stringify(knownRed.slice(0, 3))}`,
  );
}

async function main() {
  deleteStaleScreenshots();

  browser = await launchSystemBrowser();
  context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.addCookies([manifest.session]);
  page = await context.newPage();

  attachNetworkInstrumentation(page, { source: 'admin' });
  page.on('framenavigated', (frame) => {
    if (page && frame === page.mainFrame()) result.main_frame_navigations.push({ url: frame.url(), at: new Date().toISOString() });
  });

  await withExpectedNavigation(() => page.goto(manifest.builder_url, { waitUntil: 'domcontentloaded', timeout: 20000 }));

  await scenario('01-initial-r4', scenario01InitialR4);
  await scenario('02-hero-basic-autosave', scenario02HeroBasic);
  await scenario('03-hero-advanced-typography-override', scenario03HeroAdvancedTypography);
  await scenario('04-add-product-and-reorder', scenario04AddProductAndReorder);
  await scenario('05-product-auto-and-persian-digit-limit', scenario05ProductAutoAndPersianDigits);
  await scenario('06-product-manual-picker', scenario06ProductManualPicker);
  await scenario('07-brand-same-picker', scenario07BrandManualPicker);
  await scenario('08-undo-redo', scenario08UndoRedo);
  await scenario('09-real-stale-conflict', scenario09StaleConflict);
  await scenario('10-publish', scenario10Publish);
  await scenario('11-public-storefront-parity', scenario11PublicParity);
  await scenario('12-new-draft-only-change', scenario12NewDraftOnlyChange);
  await scenario('13-public-must-remain-unchanged', scenario13PublicUnchanged);
  await scenario('final-instrumentation-assertions', finalInstrumentationAssertions);
  await scenario('final-screenshot-verification', verifyScreenshots);

  // Opt-in Phase 3 — Task 3 "Brand gate" browser certification. Additive
  // only; never runs by default, so scenarios 01-13 and their behavior are
  // completely unchanged.
  if (manifest.phase3) {
    await scenario('phase3-brand-gate', phase3BrandGate);
  }
}

try {
  await main();
} catch (error) {
  result.summary.failed += 1;
  result.scenarios.push({ name: 'qa-runner:fatal', status: 'FAIL', error: error.stack || error.message || String(error) });
  console.error(error.stack || error);
} finally {
  result.finished_at = new Date().toISOString();
  if (publicPage) { try { await publicPage.close(); } catch (_error) {} }
  if (browser) { try { await browser.close(); } catch (_error) {} }

  fs.writeFileSync(path.join(manifest.report_dir, 'r4-browser-result.json'), JSON.stringify(result, null, 2), 'utf8');
  console.log('\n=== R4 Task 12 result summary ===');
  console.log(`Passed: ${result.summary.passed}  Failed: ${result.summary.failed}`);
  for (const row of result.scenarios) console.log(`${row.status.padEnd(5)} ${row.name}`);
}

process.exit(result.summary.failed > 0 ? 1 : 0);
