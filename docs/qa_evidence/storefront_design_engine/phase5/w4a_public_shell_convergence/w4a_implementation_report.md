# P5-W4A — Public Storefront Shell Convergence — Implementation Report

## Provenance

- **Certified starting checkpoint:** `5628d6ee31e177d0b4fa1dddad550f894bca540a`
  (the merged, certified P5-W3 official checkpoint).
- **Design spec (repaired):** `docs/superpowers/specs/2026-09-16-phase5-w4a-public-shell-convergence-design.md` (head `5d09bf44`).
- **Implementation plan:** `docs/superpowers/plans/2026-09-16-phase5-w4a-public-shell-convergence-implementation.md`.
- **Implementation branch:** `feature/phase5-w4a-public-shell-convergence`, created exactly from the certified checkpoint (`git merge-base` verified).
- **Runtime:** Python 3.12.3, Django 5.2.17.

## What changed (exactly the approved scope)

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

No other production file changed. **Zero migrations.**

## TDD proof (genuine RED before the fix, GREEN after)

| Task | Test file | RED evidence | GREEN evidence |
|---|---|---|---|
| 1 — shell-only contract | `apps/storefront_builder/tests/test_w4a_shell_only_context.py` (6 tests) | `01_red_task1_shell_only_context.txt` — 4 genuine `TypeError: unexpected keyword argument 'shell_only'` | `02_green_task1_shell_only_context.txt` — 6/6 OK, plus `test_page_shell`/`test_render_service` (147) unaffected |
| 2 — Wishlist | `apps/customers/tests/test_wishlist_shell_convergence.py` (7 tests) | `03_red_task2_wishlist.txt` — genuine failures: shell template absent, cross-Store product leak | `04_green_task2_wishlist.txt` — 7/7 OK |
| 3 — CMS | `apps/content/tests/test_page_shell_convergence.py` (8 tests) | `05_red_task3_cms.txt` — genuine failures: shell template/header-variant absent | `06_green_task3_cms.txt` — 8/8 OK |

Each RED was captured by reverting only the relevant production file(s) to
the pre-fix commit (`git show <commit>:<path>`) while keeping the new test
file in place, running the suite, then restoring the fix — never by writing
assertions after the fact.

## Focused tests

`apps.storefront_builder.tests.test_w4a_shell_only_context` (6) +
`apps.customers.tests.test_wishlist_shell_convergence` (7) +
`apps.content.tests.test_page_shell_convergence` (8) = **21 tests, all PASS**.

## Regression

- `apps.customers.tests`: **81 tests, 2 pre-existing errors**
  (`test_otp_login_merges_guest_cart`, `test_signup_merges_guest_cart` — an
  unrelated guest-cart-merge-on-login `AttributeError`; confirmed identical
  on a clean worktree at the pre-Wishlist-change commit, i.e. genuinely
  pre-existing, not introduced by this change). Evidence:
  `08_regression_customers_full.txt`.
- `apps.content.tests`: **466 tests, OK**. Evidence: `07_regression_content_full.txt`.
- `apps.storefront_builder.tests.test_page_shell` + `test_render_service`:
  **147 tests, OK** (1 pre-existing skip). Evidence: `02_green_task1_shell_only_context.txt`.
- `apps.stores.tests.test_resolution` + catalog/cart shell-adjacent suites
  (`test_collection_public_views`, `test_u5_listing_filter_search`,
  `test_cart_views`, `test_g2_listing_context_and_chips`): **170 tests, OK**.
  Evidence: `10_regression_shell_render_tenant_catalog_cart.txt`.
- `apps.catalog.tests` + `apps.cart.tests` (full): **1007 tests, OK**.
  Evidence: `11_full_catalog_cart_regression.txt`.
- `apps.storefront_builder.tests` (full): **3216 tests, 30 failures, 2
  errors, 4 skipped** — see base comparison below. Evidence:
  `09_full_storefront_builder_suite.txt`.

## Full-suite base comparison

See `12_full_suite_base_comparison.md`. **W4A-only failures = 0. Changed
pre-existing failure reasons = 0.** The certified base's own 30F+2E+4skip
(reused directly from the W3 evidence, since the certified checkpoint IS
that exact commit) match identity-for-identity and byte-for-byte
(after masking CSRF-token-shaped noise) against the final W4A run.

## Browser QA

`tools/storefront_builder_r4_qa/w4a_public_shell_qa.mjs` (reuses the same
Chromium/playwright-core resolution convention as `w3_design_lab_qa.mjs` —
no second harness). Templates: `dark_digital`, `warm_boutique`. Viewports:
1440×900, 768×1024, 390×844. All 12 viewport/scenario combinations per
template: RTL intact, no horizontal overflow, canonical header present, 0
console errors, 0 failed requests.

Scenarios (desktop, both templates): Wishlist anonymous (login prompt
visible) — PASS; Wishlist empty authenticated (empty-state markup) — PASS;
Wishlist populated (`article.pcard` — the canonical ProductCard root —
visible) — PASS; CMS published page (body text visible) — PASS.

Evidence: `browser_qa/dark_digital/`, `browser_qa/warm_boutique/`
(`w4a_browser_qa_result.json` + 12 screenshots each).

## System / migration gates

- `python manage.py check`: 0 issues.
- `python manage.py makemigrations --check --dry-run`: No changes detected.
- **Migrations: 0.**
- `git diff --check`: clean.
- `git status --short`: clean after this evidence commit.

## Architecture / duplication gate

- One `build_universal_storefront_context` (plus two PRIVATE helpers in the
  same module — `_unresolved_context`, `_build_published_shell_context` —
  not a second authority).
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
- No migration files created.
- **Gate: PASS.**

## Known limitations / deferred items

- The two pre-existing `apps.customers.tests` cart-merge-on-login errors
  are unrelated to this workstream and were not fixed here (out of scope;
  confirmed pre-existing on the base).
- P5-W4B (50-Template Curation) and P5-W4C (All-50 Browser Certification)
  remain frozen — not started.
