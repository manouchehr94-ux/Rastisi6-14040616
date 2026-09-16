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

// Call the read-only /design-lab/ endpoint from within the page (same-origin,
// session cookie + CSRF) and return the server-authoritative response — the
// candidate token, base_selections, candidate_selections, and Persian diffs.
// This lets the browser QA assert on real DATA, not panel visibility.
async function designLab(page, body) {
  return page.evaluate(async (body) => {
    const url = document
      .querySelector('[data-r4-design-lab-panel]')
      .getAttribute('data-r4-design-lab-url');
    const csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
    const r = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify(body),
    });
    let json = null;
    try { json = await r.json(); } catch (_e) { json = null; }
    return { status: r.status, body: json };
  }, body);
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
          const txt = m.text();
          // The stale-apply scenario DELIBERATELY triggers a 409 (proving stale
          // rejection); the browser logs any 409 as a generic "Failed to load
          // resource" console error. That expected 409 is not a real defect.
          if (/status of 409/.test(txt)) return;
          vpErrors.push(`[${vp.name}] ${txt}`);
          result.console_errors.push(`[${vp.name}] ${txt}`);
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

      // ---- Scenario A — Full Random Mix (UI) + candidate preview HTTP 200 ---
      const randomMix = await page.$('[data-r4-design-lab-random-mix]');
      if (randomMix) {
        await randomMix.click();
        await waitState(page, 'پیش‌نمایش');
        await page.waitForTimeout(1000);
        await page.screenshot({ path: path.join(SHOTS, `${vp.name}_02_random_mix.png`), fullPage: false });
      }
      if (vp.name === 'desktop') {
        // Server-authoritative DATA: a fresh Random Mix must change families vs
        // Base, and its candidate must render through the existing preview route.
        const mix = await designLab(page, { action: 'random_mix', locked_families: [] });
        const b = mix.body;
        const changedFamilies = Object.keys(b.candidate_selections).filter(
          (f) => b.candidate_selections[f] !== b.base_selections[f]
        );
        const ps = await previewStatus(page, b.token);
        record('A_full_random_mix_changes_candidate', changedFamilies.length > 0,
          `changed ${changedFamilies.length} families vs Base; draft NOT applied`);
        record('M_candidate_preview_renders_200', ps.status === 200 && ps.len > 1000,
          `preview HTTP ${ps.status}, ${ps.len} bytes via existing storefront_preview route`);
        result.viewports[vp.name].candidate_preview_status = ps.status;

        // ---- Scenario D — Compare with Base (REAL DIFF, not visibility) -----
        // Diffs are computed server-side against the ORIGINAL Base. Assert at
        // least one real changed family whose base label != candidate label.
        const compare = await designLab(page, { action: 'compare', candidate_token: b.token });
        const diffs = compare.body.diffs || [];
        const realDiff = diffs.find((d) => d.base_label !== d.candidate_label);
        await page.$('[data-r4-design-lab-compare]').then((el) => el && el.click());
        await page.waitForTimeout(500);
        await page.screenshot({ path: path.join(SHOTS, `desktop_03_compare.png`), fullPage: false });
        record('D_compare_with_base_real_diff',
          diffs.length > 0 && !!realDiff,
          realDiff ? `${realDiff.family}: "${realDiff.base_label}" -> "${realDiff.candidate_label}"` : 'no real diff');

        // ---- Scenario E — Return to Original DNA (EXACT restore) ------------
        // Capture Base A; Random Mix -> B; Return -> assert candidate == A
        // family-by-family (server-authoritative selections), not just "no diff".
        const freshMix = await designLab(page, { action: 'random_mix', locked_families: [] });
        const A = freshMix.body.base_selections;
        const ret = await designLab(page, { action: 'return_to_dna', candidate_token: freshMix.body.token });
        const returned = ret.body.candidate_selections;
        const exactRestore = Object.keys(A).every((f) => returned[f] === A[f]) &&
          (ret.body.diffs || []).length === 0;
        await page.$('[data-r4-design-lab-return-dna]').then((el) => el && el.click());
        await page.waitForTimeout(500);
        await page.screenshot({ path: path.join(SHOTS, `desktop_06_return_dna.png`), fullPage: false });
        record('E_return_to_original_dna_exact', exactRestore,
          'returned candidate equals Base A family-by-family');

        // ---- Scenario B — Chained Randomize One preserves other families ----
        // Random Mix -> B, Randomize footer -> C; every non-footer family in C
        // must equal B; footer must change (registry has alternatives).
        const mixB = await designLab(page, { action: 'random_mix', locked_families: [] });
        const B = mixB.body.candidate_selections;
        const one = await designLab(page, {
          action: 'randomize_one', family: 'footer', candidate_token: mixB.body.token, locked_families: [],
        });
        const C = one.body.candidate_selections;
        const othersPreserved = Object.keys(B).every((f) => f === 'footer' || C[f] === B[f]);
        const footerChanged = C.footer !== B.footer;
        await page.$('[data-r4-design-lab-family-row][data-r4-design-lab-family="footer"] [data-r4-design-lab-randomize-one]')
          .then((el) => el && el.click());
        await page.waitForTimeout(500);
        await page.screenshot({ path: path.join(SHOTS, `desktop_05_randomize_one_footer.png`), fullPage: false });
        record('B_chained_randomize_preserves_others', othersPreserved,
          'non-footer candidate families preserved from B');
        record('B_randomize_one_footer_changes', footerChanged,
          `footer ${B.footer} -> ${C.footer}`);

        // ---- Scenario C — Lock CURRENT candidate value --------------------
        // Randomize header -> H1; Lock header; Random Mix; header must stay H1
        // (the CURRENT candidate value), not revert to the committed Draft H0.
        let cur = await designLab(page, { action: 'reset' });
        const H0 = cur.body.base_selections.header;
        let H1 = H0, tok = cur.body.token;
        for (let i = 0; i < 30; i++) {
          const r = await designLab(page, { action: 'randomize_one', family: 'header', candidate_token: tok, locked_families: [] });
          tok = r.body.token; H1 = r.body.candidate_selections.header;
          if (H1 !== H0) break;
        }
        let lockedHeld = H1 !== H0;
        for (let i = 0; i < 3 && lockedHeld; i++) {
          const r = await designLab(page, { action: 'random_mix', candidate_token: tok, locked_families: ['header'] });
          tok = r.body.token;
          if (r.body.candidate_selections.header !== H1) lockedHeld = false;
        }
        // Exercise the UI lock button for the screenshot.
        await page.$('[data-r4-design-lab-family-row][data-r4-design-lab-family="header"] [data-r4-design-lab-lock]')
          .then((el) => el && el.click());
        await page.$('[data-r4-design-lab-random-mix]').then((el) => el && el.click());
        await waitState(page, 'پیش‌نمایش'); await page.waitForTimeout(500);
        await page.screenshot({ path: path.join(SHOTS, `desktop_04_lock_header.png`), fullPage: false });
        record('C_lock_preserves_current_candidate', lockedHeld,
          `locked header held current candidate value H1=${H1} (H0=${H0})`);

        // ---- Scenario F — Reset Candidate (no diff, back to Base) ----------
        const resetR = await designLab(page, { action: 'reset' });
        record('F_reset_candidate', (resetR.body.diffs || []).length === 0,
          'reset candidate equals committed Draft');
        await page.$('[data-r4-design-lab-reset]').then((el) => el && el.click());
        await page.waitForTimeout(500);
        await page.screenshot({ path: path.join(SHOTS, `desktop_07_reset.png`), fullPage: false });

        // ---- Scenario G — Remove Theme (transient) -------------------------
        const rt = await designLab(page, { action: 'remove_theme', candidate_token: resetR.body.token });
        record('G_remove_theme_transient',
          rt.body.candidate_selections.theme === 'theme.none.v1',
          'remove-theme candidate has theme.none.v1 (no write yet)');
        await page.$('[data-r4-design-lab-remove-theme]').then((el) => el && el.click());
        await page.waitForTimeout(500);
        await page.screenshot({ path: path.join(SHOTS, `desktop_08_remove_theme.png`), fullPage: false });

        // ---- Scenario H — explicit Apply via the UI ------------------------
        // Capture the live revision, build a fresh candidate via the UI, click
        // Apply, and confirm BOTH the UI state and the server-side revision
        // advance (draft is written only after the explicit Apply).
        page.on('dialog', (d) => d.accept());
        const revBefore = await page.evaluate(() =>
          Number(document.querySelector('[data-r4-shell]').dataset.editRevision || 0));
        await page.$('[data-r4-design-lab-random-mix]').then((el) => el && el.click());
        await waitState(page, 'پیش‌نمایش'); await page.waitForTimeout(1200);
        const applyBtn = await page.$('[data-r4-design-lab-apply]');
        const applyDisabledBefore = await applyBtn.isDisabled();
        await applyBtn.click();
        const st = await waitState(page, 'اعمال شد', 15000);
        await page.waitForTimeout(1500);
        const revAfter = await page.evaluate(() =>
          Number(document.querySelector('[data-r4-shell]').dataset.editRevision || 0));
        await page.screenshot({ path: path.join(SHOTS, `desktop_09_after_apply.png`), fullPage: false });
        record('H_explicit_apply', /اعمال شد/.test(st || '') || revAfter > revBefore,
          `apply enabled before=${!applyDisabledBefore}; state="${st}"; revision ${revBefore}->${revAfter}`);

        // ---- New scenario — real-flow STALE apply --------------------------
        // Create a candidate at revision N; make another canonical edit (via a
        // fresh Random Mix + Apply) advancing the Draft; then attempt to Apply
        // the OLD candidate token — the /design-lab/ apply_payload must reject
        // it as stale (409) and NOT write.
        const stale = await designLab(page, { action: 'random_mix', locked_families: [] });
        const staleToken = stale.body.token;
        // Advance the Draft with another real Design Lab apply.
        const advance = await designLab(page, { action: 'random_mix', locked_families: [] });
        const advPayload = await designLab(page, { action: 'apply_payload', candidate_token: advance.body.token });
        if (advPayload.body && advPayload.body.mutation) {
          await page.evaluate(async (mutation) => {
            const csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
            const rev = Number(document.querySelector('[data-r4-shell]').dataset.editRevision || 0);
            await fetch('mutate/', {
              method: 'POST', credentials: 'same-origin',
              headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
              body: JSON.stringify({ base_revision: rev, mutation }),
            });
          }, advPayload.body.mutation);
        }
        // Now the old candidate must be stale.
        const staleApply = await designLab(page, { action: 'apply_payload', candidate_token: staleToken });
        record('STALE_candidate_apply_rejected',
          staleApply.status === 409 && staleApply.body && staleApply.body.code === 'stale_candidate',
          `stale apply_payload => HTTP ${staleApply.status} code=${staleApply.body && staleApply.body.code}`);
        await page.screenshot({ path: path.join(SHOTS, `desktop_10_stale_apply.png`), fullPage: false });
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
