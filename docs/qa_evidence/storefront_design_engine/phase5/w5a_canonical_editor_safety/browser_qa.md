# W5A — Targeted Browser QA

Per the master plan's directive (do NOT run the full 704 Ready-Template campaign; reuse existing browser/QA infrastructure, no second harness), a workstream-scoped Playwright script was added at `tools/storefront_builder_r4_qa/w5a_canonical_editor_safety_qa.mjs`, following the exact same pattern already established by `w3_design_lab_qa.mjs`/`w4a_public_shell_qa.mjs` (same Chromium/`playwright-core` resolution, same `--host-resolver-rules=MAP * 127.0.0.1` approach, same "Python owns Store-state setup, Node owns only browser assertions" convention — this is a workstream-scoped sibling script within the *existing* infrastructure, not a second harness).

## Independent-Review repair (round 2)

The Independent Architect found the round-1 evidence insufficient on one required scenario: item 3 (R3-pinned rollback editor) had been recorded as "verified via the Django test suite, not re-driven in browser" — the master plan explicitly required this scenario in **real** browser QA, and Django-only verification does not satisfy that requirement. This round adds a real second Store fixture (`w5a-qa-r3-store`, `r4_editor_enabled=False`, same owner user) and drives an actual legacy Class-A write against it through the real browser. The Class-C wire-contract change (Finding 5 in `code_review.md` — the precondition now binds to Draft identity, not revision alone) also required updating every JSON payload this script sends, and the History/Industry-Apply buttons' new `data-r4-base-draft-id` attribute.

## Setup

- Dependencies: `tools/storefront_builder_qa/node_modules/playwright-core` (already present from round 1; Chromium at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`).
- Django dev server run locally against a fresh SQLite database: `manage.py migrate` then `manage.py runserver 127.0.0.1:8765` (`DJANGO_DEBUG=True`).
- Fixture setup: `/tmp/w5a-evidence/qa_setup.py` (QA-scratch, not committed) creates:
  - `w5a-qa-store` (`r4_editor_enabled=True`) — the R4-active fixture from round 1, unchanged: published version + active Draft + industry-template installation.
  - **New this round**: `w5a-qa-r3-store` (`r4_editor_enabled=False`), owned by the SAME user (`w5a_qa_owner`), with one active Draft carrying one `rich_text` section, for the real rollback-editor scenario.
- Login: through the real, unmodified `/admin-portal/login/` form (real CSRF token, real session cookie) — not a pre-baked session. Because Django's session cookie is host-scoped (no shared `SESSION_COOKIE_DOMAIN`), a **second** real login is performed on the R3 Store's own admin host before scenario 3 (the R4 Store's session does not carry over to a different `admin_subdomain`).

## Scenarios (all required by the master plan, 14/14 PASS)

| # | Scenario | Result |
|---|---|---|
| 1 | R4-enabled Store opens the canonical R4 Builder | PASS |
| 2 | A blocked Class-A legacy editor write cannot mutate an R4 Store (direct navigation to the legacy footer form) | PASS — 404 |
| 3a | R3-pinned Store opens the real rollback editor (real second login, real Host-resolved page) | PASS — 200 |
| 3b | A real legacy Class-A write (section toggle) succeeds (not 404) on the R3-pinned Store, through a real browser `fetch()` with real CSRF | PASS — `{"status":200,"ok":true}` |
| 3c | The resulting Draft-state change is real, verified directly against the database (`StorefrontSection.is_active`) immediately after the browser run | PASS — `True → False` |
| 4 | History browser remains readable under R4 | PASS — 200 |
| 4b | History page renders both `base_draft_id` and `base_revision` preconditions (Finding 5 wire-contract change) | PASS — `{"base_draft_id":5,"base_revision":0}` |
| 5 | R4-safe Restore completes through the real UI/action (real button, real inline `fetch()` JS, real CSRF, real redirect) | PASS |
| 6 | Stale Restore rejected (409, no mutation) — now a deliberately wrong Draft identity, not just a wrong revision | PASS — `{"status":409,"body":{"code":"stale_revision","current_revision":0,"current_draft_id":5}}` |
| 7 | R4-safe Industry Layout Apply completes through the real UI (including the real `confirm()` gate since this Store has a published version) | PASS — `status=200` |
| 8 | Stale Industry Layout Apply rejected (409, no mutation) | PASS — `{"status":409,"body":{"code":"stale_revision","current_revision":0,"current_draft_id":6}}` |
| 9 | Ready Template Gallery/Apply remains usable under R4 | PASS — 200, labeled "قالب آماده" |
| 10 | No tenant crossover (nonexistent/foreign version PK rejected) — now using the real captured `{base_draft_id, base_revision}` precondition so the request reaches the version-ownership check | PASS — `400 version_not_found` |

(Numbering follows the master plan's own scenario list A-P/1-10; item 3 is now split into 3a/3b/3c to show the open/write/verify sequence explicitly.)

## What this run proves that the Django test suite alone cannot

- The new inline `fetch()`-based JS in `history.html` and `editor.html` actually executes correctly in a real browser (reads the server-rendered `data-r4-base-draft-id`/`data-r4-base-revision`/`data-r4-apply-url` attributes, sends the right JSON body, handles the 409/200/429 responses, honors the real CSRF cookie) — the Django test client never executes JavaScript.
- The real `confirm()` browser dialog gate (native browser API, not simulable by the Django test client) fires correctly for Industry-Layout-Apply when the Store already has a published version.
- **New this round**: that the legacy rollback editor is reachable and functional through an actual second real login + real Host-resolved navigation to a genuinely different Store's admin subdomain, and that a real legacy Class-A POST from that real browser session actually flips the persisted `is_active` flag in the database — not merely that the Django test client's simulated request/response cycle behaves correctly in isolation.

## Debugging notes (kept for transparency, not defects)

Round 1 (three script-authoring mistakes, all in the *test script*, not production code):
1. An initial run asserted the wrong post-Restore redirect target (`/storefront-builder/r4/` instead of the actual, correct, intentional `/storefront-builder/`) — fixed by correcting the assertion.
2. Running the "stale Restore"/"cross-tenant" checks *after* a real successful Restore meant they observed already-changed state, confounding the intended precondition — fixed by reordering the read-only stale/cross-tenant checks before the state-mutating real-click scenarios.
3. The Industry-Layout-Apply button's real `confirm()` dialog was not being auto-accepted on the second click in the script, causing a client-side timeout (not a server-side failure) — fixed by adding the dialog handler.

Round 2 (one script-authoring mistake, found and fixed while adding scenario 3):
4. The first attempt at scenario 3 assumed the R4 Store's session cookie would carry over to the R3 Store's different admin-subdomain host (`w5a-qa-r3.rastisi.localhost`) since Store resolution is per-request Host header, not per-session — this is true for *Store resolution*, but Django's session **cookie** itself is host-scoped (no `SESSION_COOKIE_DOMAIN` spanning subdomains configured), so the browser sent no cookie at all to the new host, `staff_required` treated the request as unauthenticated, and it redirected to the central login on a third, bare `rastisi.localhost` origin — which then made the follow-up in-page `fetch()` to the R3 host a genuine cross-origin request, rejected by the browser's own CORS policy (`net::ERR_FAILED`). Fixed by performing a second, real login on the R3 host before navigating to its rollback editor, exactly mirroring how scenario 1 already logs in for the R4 host. This was a test-script gap, not a production defect — no application code changes came out of it.

No screenshots were needed for a final failure — the last clean run is 14/14 PASS. Intermediate failed-run screenshots/output (round 1 and the round-2 CORS failure) are not meaningful evidence and were not preserved as images, though the round-2 raw console output showing the CORS failure and its subsequent fix is kept in `/tmp/w5a-evidence/browser_qa_raw_output_v2.txt` (QA-scratch) for transparency of the debugging path.

## Raw output

See `docs/qa_evidence/storefront_design_engine/phase5/w5a_canonical_editor_safety/browser_qa_raw_output.txt` for the exact console output of the final clean (14/14 PASS) round-2 run.
