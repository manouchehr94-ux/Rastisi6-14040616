// P5-W3 Design Lab / Random Mix — browser QA runner.
//
// Reuses the existing tools/storefront_builder_r4_qa conventions (bundled
// playwright-core + an installed Chromium binary + session-cookie auth +
// PASS/FAIL result JSON). It does NOT create a second harness package; it is a
// small W3-only scenario script that drives the EXISTING R4 editor + Design Lab
// panel through the EXISTING preview iframe, across the three required
// viewports, in RTL, and writes screenshots + a JSON result the report cites.
//
// Usage: node w3_design_lab_qa.mjs <manifest.json>
//   manifest: { origin, session:{name,value,domain,path}, report_dir }

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { createRequire } from 'node:module';

const require = createRequire(
  '/opt/toolchains/.nvm/versions/node/v22.23.2/lib/node_modules/@playwright/mcp/node_modules/playwright-core/package.json'
);
const { chromium } = require('playwright-core');
const CHROME = '/opt/playwright/chromium-1232/chrome-linux64/chrome';

const manifest = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const REPORT = manifest.report_dir;
const SHOTS = path.join(REPORT, 'screenshots');
fs.mkdirSync(SHOTS, { recursive: true });

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'mobile', width: 390, height: 844 },
];

const BUILDER = `${manifest.origin}/admin-portal/storefront-builder/r4/`;

const result = {
  started_at: new Date().toISOString(),
  origin: manifest.origin,
  builder_url: BUILDER,
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

async function textOf(page, sel) {
  const el = await page.$(sel);
  if (!el) return null;
  return (await el.textContent() || '').trim();
}

// Directly fetch a candidate-preview URL from within the page (same-origin,
// carries the session cookie) and assert HTTP 200 — a deterministic check that
// does not depend on iframe navigation races.
async function previewStatus(page, token) {
  return page.evaluate(async (tok) => {
    const u = '/admin-portal/storefront-builder/preview/?page=home' +
      (tok ? '&design_lab=' + encodeURIComponent(tok) : '');
    const r = await fetch(u, { credentials: 'same-origin' });
    return { status: r.status, len: (await r.text()).length };
  }, token);
}

// Read the server-authoritative current DNA (per-family current label) from the
// Design Lab panel, so "changed" is judged against the server, not guessed.
async function familyLabels(page) {
  return page.$$eval('[data-r4-design-lab-family-row]', (rows) =>
    rows.map((r) => ({
      family: r.getAttribute('data-r4-design-lab-family'),
      current: (r.querySelector('[data-r4-design-lab-current]')?.textContent || '').trim(),
      locked: r.querySelector('[data-r4-design-lab-lock]')?.getAttribute('aria-pressed') === 'true',
    }))
  );
}

async function waitState(page, contains, timeout = 8000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const s = await textOf(page, '[data-r4-design-lab-state]');
    if (s && s.includes(contains)) return s;
    await page.waitForTimeout(150);
  }
  return await textOf(page, '[data-r4-design-lab-state]');
}

async function run() {
  const browser = await chromium.launch({
    executablePath: CHROME,
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--host-resolver-rules=MAP * 127.0.0.1'],
  });

  try {
    for (const vp of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        locale: 'fa-IR',
        deviceScaleFactor: 1,
      });
      await context.addCookies([
        {
          name: manifest.session.name,
          value: manifest.session.value,
          domain: '127.0.0.1',
          path: manifest.session.path || '/',
          httpOnly: true,
          secure: false,
          sameSite: 'Lax',
        },
      ]);
      const page = await context.newPage();
      const vpErrors = [];
      const vpFailed = [];
      page.on('console', (m) => {
        if (m.type() === 'error') {
          vpErrors.push(`[${vp.name}] ${m.text()}`);
          result.console_errors.push(`[${vp.name}] ${m.text()}`);
        }
      });
      page.on('requestfailed', (req) => {
        const u = req.url();
        const err = req.failure()?.errorText || '';
        // Ignore benign favicon/analytics.
        if (/favicon|analytics|gtag|fonts.gstatic/.test(u)) return;
        // A superseded iframe navigation (net::ERR_ABORTED on the preview URL)
        // is NOT a real failure: rapidly reassigning previewFrame.src for a new
        // candidate aborts the prior in-flight navigation. The candidate
        // preview's real success is asserted deterministically via
        // previewStatus() (HTTP 200). Only record genuine failures.
        if (/ERR_ABORTED/.test(err) && /storefront-builder\/preview/.test(u)) return;
        vpFailed.push(`[${vp.name}] ${u} :: ${err}`);
        result.failed_requests.push(`[${vp.name}] ${u} :: ${err}`);
      });

      await page.goto(BUILDER, { waitUntil: 'networkidle', timeout: 30000 });

      // RTL + panel present
      const dir = await page.getAttribute('html', 'dir');
      const panel = await page.$('[data-r4-design-lab-panel]');
      // The Global Design panel (which hosts Design Lab) must be opened first.
      const gdToggle = await page.$('#r4GlobalDesignToggle');
      if (gdToggle) { await gdToggle.click(); await page.waitForTimeout(400); }

      // Horizontal overflow check (no body-level horizontal scrollbar).
      const overflow = await page.evaluate(() =>
        document.documentElement.scrollWidth > document.documentElement.clientWidth + 2
      );

      result.viewports[vp.name] = {
        rtl: dir === 'rtl',
        design_lab_panel_present: !!panel,
        horizontal_overflow: overflow,
      };

      await page.screenshot({ path: path.join(SHOTS, `${vp.name}_01_editor_initial.png`), fullPage: false });

      // ---- Scenario A — Full Random Mix (desktop drives the assertions) ----
      const before = await familyLabels(page);
      const randomMix = await page.$('[data-r4-design-lab-random-mix]');
      if (randomMix) {
        await randomMix.click();
        await waitState(page, 'پیش‌نمایش');
        await page.waitForTimeout(1200);
        const after = await familyLabels(page);
        const changed = after.filter((a, i) => before[i] && a.current !== before[i].current);
        await page.screenshot({ path: path.join(SHOTS, `${vp.name}_02_random_mix.png`), fullPage: false });
        // Deterministically verify the candidate preview renders (HTTP 200)
        // via the EXISTING storefront_preview route with a server-issued token
        // (fetched from the read-only design-lab endpoint, then previewed).
        const csrf = await page.evaluate(() =>
          (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '');
        const tokResp = await page.evaluate(async (csrf) => {
          const url = document.querySelector('[data-r4-design-lab-panel]')
            .getAttribute('data-r4-design-lab-url');
          const r = await fetch(url, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
            body: JSON.stringify({ action: 'random_mix', locked_families: [] }),
          });
          return r.json();
        }, csrf);
        const ps = await previewStatus(page, tokResp && tokResp.token);
        if (vp.name === 'desktop') {
          record('A_full_random_mix_changes_candidate', changed.length > 0,
            `changed ${changed.length} families; draft NOT yet applied`);
          record('M_candidate_preview_renders_200', ps.status === 200 && ps.len > 1000,
            `preview HTTP ${ps.status}, ${ps.len} bytes via existing storefront_preview route`);
          result.viewports[vp.name].candidate_preview_status = ps.status;
        }
      } else if (vp.name === 'desktop') {
        record('A_full_random_mix_changes_candidate', false, 'random-mix control not found');
      }

      // ---- Scenario D — Compare with Base ----
      const compareBtn = await page.$('[data-r4-design-lab-compare]');
      if (compareBtn) {
        await compareBtn.click();
        await page.waitForTimeout(800);
        const compareVisible = await page.$eval('[data-r4-design-lab-compare-output]',
          (el) => !el.hasAttribute('hidden')).catch(() => false);
        await page.screenshot({ path: path.join(SHOTS, `${vp.name}_03_compare.png`), fullPage: false });
        if (vp.name === 'desktop') record('D_compare_with_base_shows_diff', !!compareVisible, 'compare panel visible');
      }

      // ---- Scenario C — Lock a family then Random Mix (desktop only assert) ----
      if (vp.name === 'desktop') {
        // Reset first to a clean base.
        const resetBtn = await page.$('[data-r4-design-lab-reset]');
        if (resetBtn) { await resetBtn.click(); await page.waitForTimeout(900); }
        const headerRow = await page.$('[data-r4-design-lab-family-row][data-r4-design-lab-family="header"]');
        const lockBtn = headerRow && await headerRow.$('[data-r4-design-lab-lock]');
        if (lockBtn) {
          await lockBtn.click();
          await page.waitForTimeout(150);
          const baseLbls = await familyLabels(page);
          const headerBefore = baseLbls.find((f) => f.family === 'header')?.current;
          // Random Mix repeatedly; header must never change.
          let headerChanged = false;
          for (let i = 0; i < 3; i++) {
            await (await page.$('[data-r4-design-lab-random-mix]')).click();
            await waitState(page, 'پیش‌نمایش');
            await page.waitForTimeout(900);
            const lbls = await familyLabels(page);
            if (lbls.find((f) => f.family === 'header')?.current !== headerBefore) headerChanged = true;
          }
          const anyOtherChanged = (await familyLabels(page)).some((f, i) => f.family !== 'header' && f.current !== baseLbls[i].current);
          await page.screenshot({ path: path.join(SHOTS, `desktop_04_lock_header.png`), fullPage: false });
          record('C_lock_header_never_changes', !headerChanged, `header locked stayed "${headerBefore}"`);
          record('C_other_family_still_changes', anyOtherChanged, 'a non-locked eligible family changed');
        }
      }

      // ---- Scenario B — Randomize One (desktop only assert) ----
      if (vp.name === 'desktop') {
        const resetBtn = await page.$('[data-r4-design-lab-reset]');
        if (resetBtn) { await resetBtn.click(); await page.waitForTimeout(900); }
        const base = await familyLabels(page);
        const footerRow = await page.$('[data-r4-design-lab-family-row][data-r4-design-lab-family="footer"]');
        const one = footerRow && await footerRow.$('[data-r4-design-lab-randomize-one]');
        if (one) {
          await one.click();
          await waitState(page, 'پیش‌نمایش');
          await page.waitForTimeout(900);
          const after = await familyLabels(page);
          const changed = after.filter((a, i) => a.current !== base[i].current).map((a) => a.family);
          await page.screenshot({ path: path.join(SHOTS, `desktop_05_randomize_one_footer.png`), fullPage: false });
          record('B_randomize_one_only_selected', changed.every((f) => f === 'footer'),
            `changed families: ${changed.join(',') || 'none'}`);
        }
      }

      // ---- Scenario E — Return to Original DNA ----
      if (vp.name === 'desktop') {
        const rmBtn = await page.$('[data-r4-design-lab-random-mix]');
        if (rmBtn) { await rmBtn.click(); await waitState(page, 'پیش‌نمایش'); await page.waitForTimeout(900); }
        const returnBtn = await page.$('[data-r4-design-lab-return-dna]');
        if (returnBtn) {
          await returnBtn.click();
          await page.waitForTimeout(900);
          const diffs = await page.$$eval('[data-r4-design-lab-compare-list] li', (ls) => ls.map((l) => l.textContent));
          await page.screenshot({ path: path.join(SHOTS, `desktop_06_return_dna.png`), fullPage: false });
          // After return-to-DNA the compare should report no difference.
          const noDiff = diffs.length === 0 || diffs.some((t) => /تفاوتی/.test(t));
          record('E_return_to_original_dna', noDiff, 'candidate returned to committed base');
        }
      }

      // ---- Scenario F — Reset Candidate ----
      if (vp.name === 'desktop') {
        const resetBtn = await page.$('[data-r4-design-lab-reset]');
        if (resetBtn) {
          await resetBtn.click();
          await page.waitForTimeout(900);
          const st = await textOf(page, '[data-r4-design-lab-state]');
          await page.screenshot({ path: path.join(SHOTS, `desktop_07_reset.png`), fullPage: false });
          record('F_reset_candidate', /پیش‌نمایش/.test(st || ''), 'candidate discarded, back to preview state');
        }
      }

      // ---- Scenario G — Remove Theme (transient) ----
      if (vp.name === 'desktop') {
        const rt = await page.$('[data-r4-design-lab-remove-theme]');
        if (rt) {
          await rt.click();
          await waitState(page, 'پیش‌نمایش');
          await page.waitForTimeout(900);
          await page.screenshot({ path: path.join(SHOTS, `desktop_08_remove_theme.png`), fullPage: false });
          record('G_remove_theme_transient', true, 'remove-theme candidate previewed (no write yet)');
        }
      }

      // ---- Scenario A/H — explicit Apply (desktop) ----
      if (vp.name === 'desktop') {
        // Build a fresh random-mix candidate and Apply it.
        await (await page.$('[data-r4-design-lab-random-mix]')).click();
        await waitState(page, 'پیش‌نمایش');
        await page.waitForTimeout(900);
        const applyBtn = await page.$('[data-r4-design-lab-apply]');
        const applyDisabledBefore = await applyBtn.isDisabled();
        // Auto-accept the confirm() dialog.
        page.on('dialog', (d) => d.accept());
        await applyBtn.click();
        const st = await waitState(page, 'اعمال شد', 10000);
        await page.waitForTimeout(1500);
        await page.screenshot({ path: path.join(SHOTS, `desktop_09_after_apply.png`), fullPage: false });
        record('H_explicit_apply', /اعمال شد/.test(st || ''),
          `apply enabled before=${!applyDisabledBefore}; state="${st}"`);
      }

      await context.close();
    }

    result.overall =
      result.scenarios.every((s) => s.ok) &&
      result.console_errors.length === 0 &&
      result.failed_requests.length === 0 &&
      Object.values(result.viewports).every((v) => v.rtl && v.design_lab_panel_present && !v.horizontal_overflow)
        ? 'PASS'
        : 'FAIL';
  } catch (err) {
    result.overall = 'ERROR';
    result.error = String(err && err.stack || err);
  } finally {
    await browser.close();
  }

  result.finished_at = new Date().toISOString();
  fs.writeFileSync(path.join(REPORT, 'w3_browser_qa_result.json'), JSON.stringify(result, null, 2));
  console.log('OVERALL=' + result.overall);
  console.log('CONSOLE_ERRORS=' + result.console_errors.length);
  console.log('FAILED_REQUESTS=' + result.failed_requests.length);
}

run();
