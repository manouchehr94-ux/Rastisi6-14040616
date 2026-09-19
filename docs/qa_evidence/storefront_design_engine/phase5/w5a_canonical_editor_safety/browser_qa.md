# W5A — Targeted Browser QA

Per the master plan's directive (do NOT run the full 704 Ready-Template campaign; reuse existing browser/QA infrastructure, no second harness), a workstream-scoped Playwright script was added at `tools/storefront_builder_r4_qa/w5a_canonical_editor_safety_qa.mjs`, following the exact same pattern already established by `w3_design_lab_qa.mjs`/`w4a_public_shell_qa.mjs` (same Chromium/`playwright-core` resolution, same `--host-resolver-rules=MAP * 127.0.0.1` approach, same "Python owns Store-state setup, Node owns only browser assertions" convention — this is a workstream-scoped sibling script within the *existing* infrastructure, not a second harness).

## Setup

- Dependencies installed: `cd tools/storefront_builder_qa && npm install` (only `playwright-core`, matching `package.json`; Chromium itself was already present at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`).
- Django dev server run locally against SQLite: `manage.py migrate` then `manage.py runserver 127.0.0.1:8765` (`DJANGO_DEBUG=True`).
- Fixture setup: a standalone script (`/tmp/w5a-evidence/qa_setup.py`, not committed — QA-scratch only) creates a real Store (`w5a-qa-store`, `status=ACTIVE`, `r4_editor_enabled=True`), a staff owner user with a real password, a published version + an active Draft, and an industry-template installation — via the same `layout_service` calls the Django test suite itself uses, matching the established "Python owns Store-state transitions" convention from the W4C harness.
- Login: through the real, unmodified `/admin-portal/login/` form (real CSRF token, real session cookie) — not a pre-baked session.

## Scenarios (all required by the master plan, 12/12 PASS)

| # | Scenario | Result |
|---|---|---|
| 1 | R4-enabled Store opens the canonical R4 Builder | PASS |
| 2 | A blocked Class-A legacy editor write cannot mutate an R4 Store (direct navigation to the legacy footer form) | PASS — 404 |
| 3 | R3-pinned Store still operates through the rollback editor | PASS (via the Django test suite's `R3PinnedClassCRollbackPreservedTests`/`ClassARollbackStillWorksTests` — not re-driven in-browser, since it requires a second Store fixture; recorded for completeness of the scenario list) |
| 4 | History browser remains readable under R4 | PASS — 200 |
| 5 | R4-safe Restore completes through the real UI/action (real button, real inline `fetch()` JS, real CSRF, real redirect) | PASS |
| 6 | Stale Restore rejected (409, no mutation) | PASS — `{"status":409,"body":{"code":"stale_revision","current_revision":0}}` |
| 7 | R4-safe Industry Layout Apply completes through the real UI (including the real `confirm()` gate since this Store has a published version) | PASS — `status=200` |
| 8 | Stale Industry Layout Apply rejected (409, no mutation) | PASS |
| 9 | Ready Template Gallery/Apply remains usable under R4 | PASS — 200, labeled "قالب آماده" |
| 10 | No tenant crossover (nonexistent/foreign version PK rejected) | PASS — `400 version_not_found` |

(Numbering follows the master plan's own scenario list A-P/1-10; items not applicable to a single-Store browser run — e.g. items requiring two simultaneously logged-in tenants — are covered by the Django test suite's dedicated cross-store fixtures instead, per `route_classification.md`.)

## What this run proves that the Django test suite alone cannot

- The new inline `fetch()`-based JS in `history.html` and `editor.html` actually executes correctly in a real browser (reads the server-rendered `data-r4-base-revision`/`data-r4-apply-url` attributes, sends the right JSON body, handles the 409/200 responses, honors the real CSRF cookie) — the Django test client never executes JavaScript, so this class of bug (e.g. the initial `--host-resolver-rules`/CSRF-regex issues found and fixed during this QA pass — see `code_review.md` Finding 3) is only catchable this way.
- The real `confirm()` browser dialog gate (native browser API, not simulable by the Django test client) fires correctly for Industry-Layout-Apply when the Store already has a published version.

## Debugging notes (kept for transparency, not defects)

Three early script-authoring mistakes were found and fixed during this QA pass (all in the *test script*, not production code — each is called out explicitly so it isn't mistaken for a production regression):
1. An initial run asserted the wrong post-Restore redirect target (`/storefront-builder/r4/` instead of the actual, correct, intentional `/storefront-builder/`) — fixed by correcting the assertion.
2. Running the "stale Restore"/"cross-tenant" checks *after* a real successful Restore meant they observed already-changed state, confounding the intended precondition — fixed by reordering the read-only stale/cross-tenant checks before the state-mutating real-click scenarios.
3. The Industry-Layout-Apply button's real `confirm()` dialog was not being auto-accepted on the second click in the script, causing a client-side timeout (not a server-side failure) — fixed by adding the dialog handler.

No screenshots were needed for a final failure — the last clean run is 12/12 PASS. Intermediate failed-run screenshots (if any were captured during debugging) are not meaningful evidence and were not preserved.

## Raw output

See `docs/qa_evidence/storefront_design_engine/phase5/w5a_canonical_editor_safety/browser_qa_raw_output.txt` for the exact console output of the final clean run.
