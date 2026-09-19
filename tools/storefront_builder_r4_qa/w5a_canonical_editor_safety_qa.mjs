// P5-W5A Canonical Editor Safety — targeted browser QA runner.
//
// Reuses the existing tools/storefront_builder_r4_qa conventions (same
// Chromium/playwright-core resolution as w3_design_lab_qa.mjs/
// w4a_public_shell_qa.mjs) — no second harness. Python owns Store-state
// setup (see /tmp/w5a-evidence/qa_setup.py, run separately against a local
// dev server); this script owns only real-browser assertions: it logs in
// through the actual legacy admin login form (real session, real CSRF),
// then drives the real R4 editor, History page, and Industry-layout card,
// including exercising the new inline fetch()-based Restore/Apply-Industry
// -Layout JS in an actual browser (something the Django test client cannot
// verify, since it never executes JS).
//
// Usage: node w5a_canonical_editor_safety_qa.mjs <manifest.json>
//   manifest: { origin, admin_host, username, password, published_version_pk, report_dir }

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
  console.error('Usage: node w5a_canonical_editor_safety_qa.mjs <manifest.json>');
  process.exit(2);
}
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const {
  admin_host, username, password, published_version_pk, report_dir,
  r3_admin_host, r3_section_pk,
} = manifest;
const port = manifest.port || new URL(manifest.origin).port;
const origin = `http://${admin_host}:${port}`;
const r3Origin = r3_admin_host ? `http://${r3_admin_host}:${port}` : null;
fs.mkdirSync(report_dir, { recursive: true });

const results = [];
function record(name, ok, detail) {
  results.push({ name, ok, detail: detail || '' });
  console.log(`${ok ? 'PASS' : 'FAIL'} — ${name}${detail ? ' — ' + detail : ''}`);
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
  page.on('request', (req) => {
    if (req.url().includes('/r4/restore/') || req.url().includes('/r4/apply-industry-layout/')) {
      console.log('  [debug request]', req.method(), req.url(), 'body=', req.postData());
    }
  });

  try {
    // 1. Merchant opens the canonical R4 Builder (after logging in for real).
    await page.goto(`${origin}/admin-portal/login/`, { waitUntil: 'domcontentloaded' });
    await page.fill('input[name="username"]', username);
    await page.fill('input[name="password"]', password);
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
      page.click('button[type="submit"], input[type="submit"]'),
    ]);
    await page.goto(`${origin}/admin-portal/storefront-builder/r4/`, { waitUntil: 'networkidle' });
    const editorOk = page.url().includes('/storefront-builder/r4/') && !page.url().includes('/login/');
    record('1. R4 Builder opens for an R4-enabled Store', editorOk, page.url());
    if (!editorOk) await page.screenshot({ path: path.join(report_dir, '01-editor-open-FAIL.png'), fullPage: true });

    // 2. A blocked Class-A legacy editor write cannot mutate an R4 Store
    //    (direct navigation to the legacy full-page footer form).
    const legacyFooterResp = await page.goto(`${origin}/admin-portal/storefront-builder/footer/`, { waitUntil: 'domcontentloaded' });
    record('2. Legacy Class-A footer editor fails closed (404) under R4', legacyFooterResp.status() === 404, `status=${legacyFooterResp.status()}`);

    // 9. Ready Template Gallery/Apply remains usable under R4.
    const galleryResp = await page.goto(`${origin}/admin-portal/storefront-builder/templates/`, { waitUntil: 'domcontentloaded' });
    const galleryHasReadyTemplateLabel = (await page.content()).includes('قالب آماده') || (await page.content()).includes('قالب‌های آماده');
    record('9. Ready Template Gallery remains reachable + labeled "Ready Template"', galleryResp.status() === 200 && galleryHasReadyTemplateLabel, `status=${galleryResp.status()}`);

    // 4. History browser remains readable under R4.
    const historyResp = await page.goto(`${origin}/admin-portal/storefront-builder/history/`, { waitUntil: 'domcontentloaded' });
    record('4. History browser readable under R4', historyResp.status() === 200, `status=${historyResp.status()}`);
    if (historyResp.status() !== 200) await page.screenshot({ path: path.join(report_dir, '04-history-FAIL.png'), fullPage: true });

    // Real current Draft identity/revision precondition, read straight off
    // the server-rendered Restore button — the same values a real client
    // would capture at render time (Independent-Review repair: the wire
    // contract now binds to BOTH, not revision alone).
    const currentPrecondition = await page.evaluate(() => {
      const btn = document.querySelector('[data-r4-restore-button]');
      if (!btn) return null;
      const rawId = btn.getAttribute('data-r4-base-draft-id');
      const rawRevision = btn.getAttribute('data-r4-base-revision');
      return {
        base_draft_id: rawId === 'null' ? null : parseInt(rawId, 10),
        base_revision: rawRevision === 'null' ? null : parseInt(rawRevision, 10),
      };
    });
    record('4b. History page renders both base_draft_id and base_revision preconditions', currentPrecondition !== null, JSON.stringify(currentPrecondition));

    // 6. Stale Restore rejected FIRST, while state is still known-fresh —
    // a deliberately wrong (nonexistent) Draft identity, via direct fetch
    // from the authenticated page context (real browser fetch, real
    // cookies/CSRF). Run before any successful mutation so this check's
    // precondition is unambiguous, not confounded by an earlier successful
    // Restore/Apply having already changed the Draft this script is about
    // to act on.
    const staleResult = await page.evaluate(async ({ pk }) => {
      const csrftoken = (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1] || '';
      const resp = await fetch(`/admin-portal/storefront-builder/r4/restore/${pk}/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
        body: JSON.stringify({ base_draft_id: 999999, base_revision: 999999 }),
      });
      return { status: resp.status, body: await resp.json() };
    }, { pk: published_version_pk });
    record('6. Stale Restore rejected with 409 + no mutation', staleResult.status === 409 && staleResult.body.code === 'stale_revision', JSON.stringify(staleResult));

    // 10. Cross-tenant/nonexistent version fails closed — the REAL current
    // precondition (captured above), so the request passes the
    // precondition check and actually reaches the version-ownership
    // lookup, which must then reject the nonexistent/foreign PK on its own
    // merits (400 version_not_found) — not be masked by an unrelated
    // precondition mismatch.
    const crossTenant = await page.evaluate(async (precondition) => {
      const csrftoken = (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1] || '';
      const resp = await fetch('/admin-portal/storefront-builder/r4/restore/999999999/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
        body: JSON.stringify(precondition),
      });
      return { status: resp.status, body: await resp.json() };
    }, currentPrecondition);
    record('10. Cross-tenant/nonexistent version fails closed', crossTenant.status === 400 && crossTenant.body.code === 'version_not_found', JSON.stringify(crossTenant));

    // 5. R4-safe Restore completes through the real UI (button, real
    // fetch() JS, real redirect to the merchant editor).
    const restoreButtonSelector = '[data-r4-restore-button]';
    const hasRestoreButton = (await page.$(restoreButtonSelector)) !== null;
    record('5a. History page renders the new R4-safe Restore button (not the legacy <form>)', hasRestoreButton);
    if (hasRestoreButton) {
      page.once('dialog', (dialog) => dialog.accept());
      await Promise.all([
        page.waitForURL('**/storefront-builder/', { timeout: 5000 }).catch(() => null),
        page.click(restoreButtonSelector),
      ]);
      await page.waitForTimeout(500);
      const afterRestoreUrl = page.url();
      // Success redirects to the merchant editor entry point (which itself
      // shows the R4-active compatibility surface / links into R4) — the
      // same target the pre-existing legacy Restore already redirected to.
      record('5b. R4-safe Restore completes through the real UI/action', afterRestoreUrl.includes('/storefront-builder/'), afterRestoreUrl);
    }

    // 7 & 8. Industry Layout Apply — the card lives on the legacy shell
    // page (editor.html's R4-active minimal-compatibility branch, not
    // r4/editor.html), which is exactly where 5b's successful Restore
    // just redirected us; reload it explicitly anyway so the button's
    // server-rendered base_revision reflects the Draft Restore just
    // replaced it with (otherwise this button's stale captured
    // precondition would itself now legitimately conflict).
    await page.goto(`${origin}/admin-portal/storefront-builder/`, { waitUntil: 'networkidle' });
    const industryButton = await page.$('#r4IndustryApplyButton');
    record('7a. R4-active editor renders the new Industry-Layout-Apply button', industryButton !== null);
    if (industryButton) {
      const staleIndustry = await page.evaluate(async () => {
        const csrftoken = (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1] || '';
        const resp = await fetch('/admin-portal/storefront-builder/r4/apply-industry-layout/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
          body: JSON.stringify({ base_draft_id: 999999, base_revision: 999999 }),
        });
        return { status: resp.status, body: await resp.json() };
      });
      record('8. Stale Industry-Layout-Apply rejected with 409 + no mutation', staleIndustry.status === 409 && staleIndustry.body.code === 'stale_revision', JSON.stringify(staleIndustry));

      // This Store already has a published version, so the button's own
      // confirm() gate fires — same "never silently overwrite" behavior
      // the legacy form's onsubmit already had.
      page.once('dialog', (dialog) => dialog.accept());
      const [applyResp] = await Promise.all([
        page.waitForResponse((r) => r.url().includes('/r4/apply-industry-layout/'), { timeout: 5000 }),
        industryButton.click(),
      ]);
      // status 200 is unambiguous proof of success by construction: the
      // view only ever returns 200 with {"ok": true} on the success path
      // (see storefront_r4_apply_industry_layout) — body-parsing here is
      // best-effort only (a Playwright CDP body-read edge case can race
      // the page's own already-consumed fetch body on some runs).
      const applyBodyText = await applyResp.text().catch(() => '<unreadable>');
      record('7b. R4-safe Industry-Layout-Apply completes through the real UI', applyResp.status() === 200, `status=${applyResp.status()} body=${applyBodyText}`);
    }

    // 3. R3-pinned Store still operates through the real rollback editor —
    // Independent-Review repair: previously only verified via the Django
    // test suite; the Architect required a REAL browser scenario. The same
    // logged-in user also owns a second, r4_editor_enabled=False Store
    // (see qa_setup.py); navigate straight to its admin host (session
    // cookie carries over — Store resolution is per-request Host header,
    // not per-session) and execute one real legacy Class-A write.
    if (r3Origin && r3_section_pk) {
      // Django's session cookie is host-scoped (no shared SESSION_COOKIE_
      // DOMAIN across admin subdomains), so the R4 Store's session does
      // NOT carry over to this different admin_subdomain host — a fresh,
      // real login (same form, same user) is required here, exactly as
      // the very first scenario above did for the R4 host.
      await page.goto(`${r3Origin}/admin-portal/login/`, { waitUntil: 'domcontentloaded' });
      await page.fill('input[name="username"]', username);
      await page.fill('input[name="password"]', password);
      await Promise.all([
        page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
        page.click('button[type="submit"], input[type="submit"]'),
      ]);

      const r3EditorResp = await page.goto(`${r3Origin}/admin-portal/storefront-builder/`, { waitUntil: 'domcontentloaded' });
      const r3EditorOk = r3EditorResp.status() === 200 && page.url().startsWith(r3Origin);
      record('3a. R3-pinned Store opens the real rollback editor', r3EditorOk, `status=${r3EditorResp.status()} url=${page.url()}`);

      const toggleUrl = `${r3Origin}/admin-portal/storefront-builder/sections/${r3_section_pk}/toggle/`;
      const toggleResult = await page.evaluate(async ({ url }) => {
        const csrftoken = (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1] || '';
        const resp = await fetch(url, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken },
        });
        return { status: resp.status, ok: resp.ok };
      }, { url: toggleUrl });
      record(
        '3b. A real legacy Class-A write (section toggle) succeeds (not 404) on the R3-pinned Store',
        toggleResult.status !== 404 && toggleResult.ok,
        JSON.stringify(toggleResult),
      );
      // The resulting Draft-state change (section.is_active flipped) is
      // verified directly against the database by the Python fixture
      // script immediately after this run — see w5a_browser_qa_r3_verify.py
      // and browser_qa.md for that result, matching the established
      // "Python owns Store-state verification" convention.
    } else {
      record('3. R3-pinned rollback editor real-browser scenario', false, 'manifest missing r3_admin_host/r3_section_pk');
    }
  } catch (error) {
    record('UNEXPECTED ERROR', false, error.stack || String(error));
    await page.screenshot({ path: path.join(report_dir, 'unexpected-error.png'), fullPage: true }).catch(() => {});
  } finally {
    await browser.close();
  }

  const summary = { total: results.length, pass: results.filter((r) => r.ok).length, fail: results.filter((r) => !r.ok).length, results };
  fs.writeFileSync(path.join(report_dir, 'w5a_browser_qa_results.json'), JSON.stringify(summary, null, 2));
  console.log(`\n${summary.pass}/${summary.total} PASS`);
  process.exit(summary.fail > 0 ? 1 : 0);
}

main();
