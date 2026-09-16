# P5-W4A — Public Storefront Shell Convergence — Implementation Report

## Provenance

- **Certified starting checkpoint:** `5628d6ee31e177d0b4fa1dddad550f894bca540a`
  (the merged, certified P5-W3 official checkpoint).
- **Design spec (repaired):** `docs/superpowers/specs/2026-09-16-phase5-w4a-public-shell-convergence-design.md` (head `5d09bf44`).
- **Implementation plan:** `docs/superpowers/plans/2026-09-16-phase5-w4a-public-shell-convergence-implementation.md`.
- **Implementation branch:** `feature/phase5-w4a-public-shell-convergence`, created exactly from the certified checkpoint (`git merge-base` verified).
- **Runtime:** Python 3.12.3, Django 5.2.17.
- **First implementation head (independently reviewed):** `73eb41c4860e79b0a786573152387d609d398f7a`.
- **This document covers the review-repair round** on top of that head, addressing Independent Architect review findings on PR #10 (CRITICAL: 0, IMPORTANT: 4, MINOR: 1, verdict: NOT READY FOR MERGE).

## What changed (exactly the approved scope)

### Original implementation (head `73eb41c4`)

- `apps/storefront_builder/services/storefront_context_service.py` — added
  the explicit `shell_only=False` keyword to `build_universal_storefront_context`;
  factored the existing body into two private helpers
  (`_unresolved_context`, `_build_published_shell_context`) shared by the
  normal and `shell_only=True` paths — one assembly path, not two.
- `apps/customers/views.py` — `wishlist_list` resolves the current Store,
  scopes the Wishlist query to it (`product__store=store`), and merges the
  `shell_only=True` universal context.
- `apps/customers/templates/customers/wishlist.html` — extends
  `storefront_shell.html` instead of `base.html`.
- `apps/content/views.py` — `page_detail` merges the `shell_only=True`
  universal context (Store resolution/scoping was already correct).
- `apps/content/templates/content/page_detail.html` — extends
  `storefront_shell.html` instead of `base.html`.

### Review-repair round (this document)

- `apps/cart/context_processors.py::cart_badge` — **IMPORTANT 1**:
  `wishlist_count` is now scoped to the current request's Store
  (`product__store=store`), fixing a cross-Store leak in the canonical
  Header's Wishlist count (the Wishlist *body* was already Store-scoped by
  the original implementation; the Header *count* was not). Fails closed to
  `0` when `request.store` is `None`, matching the fail-closed pattern used
  by `apps.content.context_processors.footer_pages`/`navigation_menus`.
- `apps/customers/templates/customers/wishlist.html` — **IMPORTANT 4
  follow-up**: added the missing `<link rel="stylesheet" href="…/css/storefront_builder.css">`
  to the existing `{% block extra_css %}`.
- `apps/content/templates/content/page_detail.html` — **IMPORTANT 4
  follow-up**: same missing stylesheet link added (plus `{% load static %}`).
- `apps/customers/tests/test_wishlist_shell_convergence.py` — new
  `WishlistHeaderCountShellConvergenceTests` (2 tests, IMPORTANT 1) +
  `test_canonical_shell_stylesheet_linked` (IMPORTANT 4 follow-up).
- `apps/content/tests/test_page_shell_convergence.py` — new
  `test_canonical_shell_stylesheet_linked` (IMPORTANT 4 follow-up).
- `tools/storefront_builder_r4_qa/w4a_public_shell_qa.mjs` — **IMPORTANT
  4**: strengthened per-viewport/scenario acceptance contract (see below).

No other production file changed in either round. **Zero migrations.**

## Why the stylesheet fix was necessary (discovered by the strengthened Browser QA)

Independent Architect finding IMPORTANT 4 asked for the Browser QA runner to
also assert canonical Footer presence, Bottom-Nav presence/health, and
absence of duplicates — not just RTL/overflow/header-present. Implementing
those checks against real source-discovered selectors (`header.header`,
`footer.gf, footer.footer`, `[data-mobile-nav]`) surfaced a genuine,
previously-undetected defect: `catalog/product_list.html`,
`product_detail.html`, `home_visual.html`, `collection_detail.html`, and
`cart/cart_detail.html` each explicitly link `css/storefront_builder.css`
themselves (every template that renders the canonical global Header/Footer/
Bottom-Nav chrome must, since `base.html`/`storefront_shell.html` never link
it implicitly) — but `wishlist.html`/`page_detail.html` never did, neither
before W4A (when they extended `base.html` directly and never rendered that
chrome at all) nor after the original W4A convergence (when they started
rendering that chrome via `storefront_shell.html` but the corresponding
stylesheet link was never added). The practical effect: the Wishlist/CMS
Header/Footer/Bottom-Nav rendered with zero CSS — most visibly, the Bottom
Nav's mobile-only `@media(max-width:680px)` visibility rule never applied,
so it would incorrectly render as an unstyled, always-visible in-flow block
at every viewport instead of a `position:fixed` bar hidden on desktop/tablet.
Fixed by adding the same stylesheet link the other converged templates
already use. Both templates were already inside this repair's exact
approved production-file scope.

## TDD proof (genuine RED before the fix, GREEN after)

| Task | Test file | RED evidence | GREEN evidence |
|---|---|---|---|
| 1 — shell-only contract | `apps/storefront_builder/tests/test_w4a_shell_only_context.py` (6 tests) | `01_red_task1_shell_only_context.txt` — 4 genuine `TypeError: unexpected keyword argument 'shell_only'` | `02_green_task1_shell_only_context.txt` — 6/6 OK, plus `test_page_shell`/`test_render_service` (147) unaffected |
| 2 — Wishlist | `apps/customers/tests/test_wishlist_shell_convergence.py` | `19_reconstructed_red_task2_wishlist.txt` — **RECONSTRUCTED RED VERIFICATION AGAINST THE EXACT PRE-WISHLIST PRODUCTION COMMIT** (`c4dc37e9`, isolated `git worktree`, current test module incl. this repair's header-count tests): 9 tests, 7 genuine failures. See "Review-repair finding 2" below — the originally-committed `03_red_task2_wishlist.txt` did **not** contain genuine RED evidence. | `04_green_task2_wishlist.txt` (original 7/7) + `15_green_important1_header_count.txt` (full 9/9 module) |
| 3 — CMS | `apps/content/tests/test_page_shell_convergence.py` (8 tests) | `05_red_task3_cms.txt` — genuine failures: shell template/header-variant absent | `06_green_task3_cms.txt` — 8/8 OK |
| Repair — IMPORTANT 1 (Header wishlist count Store isolation) | `WishlistHeaderCountShellConvergenceTests` (2 tests) | `14_red_important1_header_count.txt` — genuine `AssertionError: 2 != 1` on both Stores (real_exit_code=1) | `15_green_important1_header_count.txt` — 9/9 OK (real_exit_code=0) |
| Repair — IMPORTANT 4 follow-up (missing `storefront_builder.css` link) | `test_canonical_shell_stylesheet_linked` (Wishlist + CMS) | `20_red_important4_css_link.txt` — genuine `AssertionError: Couldn't find 'css/storefront_builder.css'` (both, real_exit_code=1) | `21_green_important4_css_link.txt` — 19/19 OK (real_exit_code=0) |

Each RED was captured either by reverting only the relevant production
file(s) to the pre-fix commit (`git show <commit>:<path>`) while keeping the
new test file in place, or (for task 2's reconstruction and both repair
items) by running the current test module against the exact pre-fix
production state — never by writing assertions after the fact, and never
using `git stash`/`git reset`/`git clean` on the active worktree.

## Review-repair finding 2 — invalid original Task-2 RED evidence, corrected

The originally-committed `03_red_task2_wishlist.txt` actually contained a
GREEN result (`Ran 7 tests ... OK`), not RED, contradicting this report's
earlier claim. Root cause: almost certainly the unintended `git stash`/
`git stash pop` cycle during the original Task-2 RED capture (see "Process
deviation" below) — the file was most likely captured after the stash was
popped and the fix restored, not before. `03_red_task2_wishlist.txt` has
been replaced with a transparent notice (no git history rewritten — a
normal new commit, not an amend/rebase/force-push) pointing to the genuine
reconstructed evidence: `19_reconstructed_red_task2_wishlist.txt`, labeled
**RECONSTRUCTED RED VERIFICATION AGAINST THE EXACT PRE-WISHLIST PRODUCTION
COMMIT** (`c4dc37e9` — has the `shell_only` contract but not yet the
Wishlist convergence changes), captured via an isolated `git worktree`
(never stash/reset on the active worktree), running the **current** Wishlist
test module (9 tests, including this repair's 2 new header-count tests)
against that exact pre-fix state: `FAILED (failures=7)`, real exit code 1.
The 2 passing tests (`test_wishlist_renders_without_published_layout`,
`test_product_card_partial_reused`) legitimately pass pre-fix too — neither
depends on the Wishlist convergence changes.

## Focused tests

`apps.storefront_builder.tests.test_w4a_shell_only_context` (6) +
`apps.customers.tests.test_wishlist_shell_convergence` (11, was 7) +
`apps.content.tests.test_page_shell_convergence` (9, was 8) = **26 tests,
all PASS**.

## Regression

### Corrected: `apps.customers.tests` count was wrong in the original report

Independent Architect finding IMPORTANT 3: the original report claimed
"81 tests / 2 pre-existing errors", but the actually-committed
`08_regression_customers_full.txt` showed `Ran 81 tests ... FAILED
(errors=3)`, and its `[exited with code 0]` marker masked the real (nonzero)
process exit status. Corrected, honestly captured with the real exit code:

- **Certified base** (`5628d6ee31e177d0b4fa1dddad550f894bca540a`, isolated
  `git worktree`, `python manage.py test apps.customers.tests`):
  **74 tests, 3 errors, real_exit_code=1**. Evidence: `17_customers_base_honest.txt`.
- **Final repaired W4A head** (same command, working tree):
  **83 tests (74 + 9 new Wishlist-convergence tests), 3 errors,
  real_exit_code=1**. Evidence: `18_customers_final_honest.txt`.
- **Error identities, base vs. final — identical, 3/3**:
  `test_login_merges_guest_cart`, `test_otp_login_merges_guest_cart`,
  `test_signup_merges_guest_cart` (all `apps.customers.tests.test_auth_views`,
  all `AttributeError: 'NoneType' object has no attribute 'quantity'` — an
  unrelated guest-cart-merge-on-login defect, confirmed genuinely
  pre-existing on the certified base, not introduced by W4A).
- **W4A-only customer errors: 0.**

CUSTOMERS REGRESSION: 83 tests, **3 PRE-EXISTING ERRORS**, **0 W4A-ONLY
ERRORS** (never "2" and never described as PASS).

### Other regression (unaffected by the repair round's production changes,
but re-run at the final head for completeness)

- `apps.cart.tests` + `apps.customers.tests` combined (final head, includes
  the `cart_badge` fix): **232 tests, 3 errors** (the same 3 pre-existing
  identities above), real_exit_code=1. Evidence:
  `16_green_cart_customers_after_important1.txt`.
- `apps.content.tests` (final head): see `23_full_content_regression_final.txt`.
- `apps.storefront_builder.tests.test_page_shell` + `test_render_service`:
  **147 tests, OK** (1 pre-existing skip). Evidence: `02_green_task1_shell_only_context.txt`.
- `apps.stores.tests.test_resolution` + catalog/cart shell-adjacent suites
  (`test_collection_public_views`, `test_u5_listing_filter_search`,
  `test_cart_views`, `test_g2_listing_context_and_chips`): **170 tests, OK**.
  Evidence: `10_regression_shell_render_tenant_catalog_cart.txt`.
- `apps.catalog.tests` + `apps.cart.tests` (full, pre-repair-round head):
  **1007 tests, OK**. Evidence: `11_full_catalog_cart_regression.txt`.
- `apps.storefront_builder.tests` (full, **re-run at the final repaired
  production head** per the review's explicit instruction not to reuse
  pre-repair evidence): **3216 tests, 30 failures, 2 errors, 4 skipped**
  (real_exit_code=1). Evidence: `22_full_storefront_builder_suite_final.txt`.

## Full-suite base comparison (refreshed at the final repaired head)

See `24_final_full_suite_base_comparison.md`. **W4A-only failures = 0.
Changed pre-existing failure reasons = 0.** Identity set identical, 32/32,
against the certified base (`w3_design_lab/19_final_full_storefront_builder_suite.txt`,
3210 tests, 30 failures, 2 errors, 4 skipped — the +6 test-count delta is
exactly the `test_w4a_shell_only_context` module from the original
implementation round); content byte-identical after masking, with the one
apparent diff on a naive substring compare traced to trailing per-run
summary text on the last block, not the failure itself (see the comparison
doc for detail).

## Browser QA (strengthened — IMPORTANT 4)

`tools/storefront_builder_r4_qa/w4a_public_shell_qa.mjs` (reuses the same
Chromium/playwright-core resolution convention as `w3_design_lab_qa.mjs` —
no second harness). Templates: `dark_digital`, `warm_boutique`. Viewports:
1440×900 (desktop), 768×1024 (tablet), 390×844 (mobile). Scenarios:
Wishlist anonymous, Wishlist empty authenticated, Wishlist populated, CMS
published page — **run on all 3 viewports each** (12 combinations per
template, 24 total; the original round only asserted domain-state on
desktop).

Per viewport × scenario, the strengthened runner now asserts, using
canonical markers source-discovered from the actual variant templates (never
a broad `[class*="header"]` guess):

- `response_status == 200` (navigation response status, not just the
  absence of a Playwright `requestfailed` event — a 4xx/5xx same-origin
  document response does not fire `requestfailed`);
- `rtl == true`, `horizontal_overflow == false` (unchanged from the
  original round);
- exactly one canonical Header (`header.header` — the class token shared by
  every Header variant, including the pre-U2A "legacy-alias" variants like
  `compact_menu` that are thin `{% include %}`s of `page_shell_header.html`)
  — proves presence **and** absence of duplicates;
- exactly one canonical Footer (`footer.gf, footer.footer` — same U2A /
  legacy-alias split) — presence and no duplicates;
- Bottom Nav count matches what the Store actually has configured
  (`[data-mobile-nav]`; the `hidden` variant renders nothing, so an
  unconfigured Store correctly yields count 0) — no duplicates either way;
- when a Bottom Nav is configured, it is visible/healthy specifically on the
  390px **mobile** viewport (`display !== 'none'` and a nonzero bounding
  rect) per the canonical `@media(max-width:680px)` rule in
  `storefront_builder.css`, and correctly *not* visible at desktop/tablet;
- the scenario's own domain-state assertion (login prompt / empty state /
  `article.pcard` ProductCard / CMS body text) — now checked at **every**
  viewport, not just desktop.

Console errors and unexpected failed requests continue to be tracked
globally per run.

**Result: 12/12 combinations PASS for `dark_digital`, 12/12 PASS for
`warm_boutique`. `CONSOLE_ERRORS=0`, `FAILED_REQUESTS=0`, both templates.**
`dark_digital`'s actually-applied Store Appearance resolves a configured
Bottom Nav (`expect_bottom_nav=true`); `warm_boutique`'s also resolves one
in this QA run (the Ready-Template manifest's structural-DNA token
resolution is a pre-existing, unrelated mechanism — this QA setup reads the
*actually-applied* `mobile_nav_variant` back from the published layout
rather than assuming the literal preset-registry string, specifically so
this kind of resolution detail can never desync the QA's expectation from
reality).

Evidence: `browser_qa/dark_digital/`, `browser_qa/warm_boutique/`
(`w4a_browser_qa_result.json` + 12 screenshots each, all regenerated by this
repair round).

## Process deviation

During the original Task-2 (Wishlist) RED-evidence capture, an unintended
`git stash` command was executed even though the task brief explicitly
prohibited `git stash`. It was immediately restored (`git stash pop`)
within the same turn, and verified via `head`/`grep` to exactly match the
pre-stash state. No work was intentionally discarded, and no `git reset`,
`git clean`, `git rebase`, or force-push occurred at any point. This is very
likely the actual root cause of Review-repair finding 2 above (the
originally-committed "RED" evidence file for Task 2 in fact containing a
GREEN result) — the file was most likely written from the post-stash-pop
(i.e. fix-restored) working tree rather than the intended genuinely-broken
pre-fix state. This is not being characterized as acceptable practice; it
is recorded here factually, and the affected evidence has been corrected
(see above) rather than left uncorrected or silently re-labeled.

## System / migration gates (final repaired head)

- `python --version`: 3.12.3; `django.get_version()`: 5.2.17.
- `python manage.py check`: 0 issues.
- `python manage.py makemigrations --check --dry-run`: No changes detected.
- **Migrations: 0.**
- `git diff --check`: clean.
- `git status --short`: clean after the repair-round commits.

Raw evidence: `13_final_repair_repo_gates.txt`.

## Architecture / duplication gate (re-confirmed after the repair round)

- One `build_universal_storefront_context` (plus two PRIVATE helpers in the
  same module — `_unresolved_context`, `_build_published_shell_context` —
  not a second authority). Unchanged by this repair round.
- No second Store resolver — `cart_badge`'s fix reuses `request.store`
  (the existing `StoreResolutionMiddleware`-set attribute), the same
  fail-closed pattern already used by
  `apps.content.context_processors.footer_pages`/`navigation_menus`. No new
  resolver function was added.
- No second Wishlist-count authority — the fix is a one-line filter change
  inside the existing, sole `cart_badge` context processor; no new service
  module was created.
- No `wishlist_storefront_context`/`content_storefront_context`/
  `public_shell_context_service` or any parallel context builder exists
  anywhere in the tree.
- `StorefrontPage.PageType` unchanged — still exactly the original six
  values (`home`, `product_detail`, `listing`, `collection`, `search`,
  `cart`).
- No second ProductCard template — Wishlist still `{% include
  "catalog/partials/product_card.html" %}` (proven by
  `test_product_card_partial_reused`).
- No new Wishlist service module.
- No new model.
- No migration files created.
- Wishlist body Store-scoped: YES (original round). Wishlist Header count
  Store-scoped: YES (this repair round, IMPORTANT 1).
- CMS tenant isolation: YES (unchanged, already correct pre-W4A).
- Header/Footer/Bottom-Nav canonical owners reused: YES — the repair
  round's Browser QA strengthening and CSS-link fix both consume the
  existing `global_region_registry`/`storefront_builder.css` authorities,
  never a parallel one.
- **Gate: PASS.**

## Known limitations / deferred items

- The 3 pre-existing `apps.customers.tests` cart-merge-on-login errors
  (corrected count — see IMPORTANT 3 above) are unrelated to this
  workstream and were not fixed here (out of scope; confirmed pre-existing,
  identical identities, on the certified base).
- P5-W4B (50-Template Curation) and P5-W4C (All-50 Browser Certification)
  remain frozen — not started.
