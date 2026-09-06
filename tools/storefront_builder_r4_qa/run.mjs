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
  const before = result.main_frame_navigations.length;
  await actionFn();
  const gained = result.main_frame_navigations.length - before;
  assert(gained === count, `Expected exactly ${count} main-frame navigation(s) from this action, got ${gained}`);
  for (let i = before; i < result.main_frame_navigations.length; i += 1) {
    result.main_frame_navigations[i].expected = true;
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
    if (url.startsWith('data:')) return;
    result.request_failures.push({ url, method: request.method(), error: request.failure()?.errorText || '', source });
  });
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
    (e) => !isExpectedStaleConflictNoise(e) && !FAVICON_URL_PATTERN.test(e?.location?.url || ''),
  );
  assert(unexpectedConsoleErrors.length === 0, `Unexpected console errors: ${JSON.stringify(unexpectedConsoleErrors.slice(0, 5))}`);

  assert(result.page_errors.length === 0, `Page errors: ${JSON.stringify(result.page_errors.slice(0, 5))}`);

  const unexpectedRequestFailures = result.request_failures.filter((f) => !FAVICON_URL_PATTERN.test(f.url || ''));
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
  const unexpectedHttp = result.http_error_responses.filter((e) => !isExpectedStale409Response(e));
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
// Phase 3 (opt-in) — responsive capture across the three PHASE3_VIEWPORTS.
//
// Runs ONLY when manifest.phase3 is truthy. It is purely additive: a
// separate page/context is used so it never disturbs the admin `page`/
// `publicPage` state the scenarios above depend on, and every artifact is
// written under manifest.report_dir (never the committed evidence dir). The
// default (non-phase3) run never calls this, so existing scenarios and
// default behavior are completely unchanged.
// =============================================================================
async function phase3ResponsiveCapture() {
  const captures = [];
  for (const vp of PHASE3_VIEWPORTS) {
    const vpContext = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
    await vpContext.addCookies([manifest.session]);
    const vpPage = await vpContext.newPage();
    try {
      await vpPage.goto(manifest.public_url, { waitUntil: 'domcontentloaded', timeout: 20000 });
      const dest = path.join(manifest.report_dir, `phase3_${vp.name}_${vp.width}x${vp.height}.png`);
      await vpPage.screenshot({ path: dest, fullPage: true });
      captures.push({ viewport: vp.name, width: vp.width, height: vp.height, path: dest });
    } finally {
      try { await vpContext.close(); } catch (_error) { /* best effort */ }
    }
  }
  result.phase3_captures = captures;
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

  // Opt-in Phase 3 responsive capture — additive only, never runs by default.
  if (manifest.phase3) {
    await scenario('phase3-responsive-capture', phase3ResponsiveCapture);
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
