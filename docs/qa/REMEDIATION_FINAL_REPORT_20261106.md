# RastiSi remediation program — final delivery report (2026-11-06)

Nothing in this report was pushed, merged or deployed, except what is stated in S1/S3 (Checkout, pushed earlier under its own authorization). No Windows QA was performed.
Evidence labels: `FIXED_AND_VERIFIED`, `ALREADY_FIXED` (verified), `REPRODUCED`, `NOT_REPRODUCED`, `BLOCKED`, `NEEDS_MANUAL_VALIDATION`, `NEEDS_OWNER_DECISION`.

## S1. Baseline
| | |
|---|---|
| Repository | `manouchehr94-ux/Rastisi6-14040616` (remote `origin`, unchanged) |
| Checkout (already pushed, Draft PR #44 → `integration/admin-ux-finance-20261105`) | `dev/platform-checkout-unify-20261106` = `8ad4b6879859cc97b854108a7436f5d5fc026a8d` (== remote). The `6f2c6c4f…` in the brief is an ancestor of it |
| Integrated base earlier reported | `integration/admin-ux-finance-20261105` = `d08dbe91…` (== remote) |
| Working trees | every branch below is a clean separate worktree; `feature/gemini-dev-20261102` (3 unpushed commits) was **not touched** |
| Database for all tests | PostgreSQL 16.15 (disposable databases); browser QA on isolated databases |

## S3. Git delivery (all LOCAL, unpushed unless stated)
| Branch | Full tip SHA | Purpose |
|---|---|---|
| `dev/platform-checkout-unify-20261106` | `8ad4b6879859cc97b854108a7436f5d5fc026a8d` | **pushed earlier**; Draft PR #44 |
| `security/tenant-isolation-20261106` | `c435803724003d7c7ae97311f28696167bbd987e` | tenant-isolation verification + refund-key fix |
| `dev/pricing-simplify-20261106` | `4c6066bd75a5a75aa82bcbbf65b276087fc9e81a` | monthly price + 3/6/12-month discounts |
| `ux/platform-merchant-remediation-20261106` | `a5496e44fa3556be026a65decf4649c543758fc8` | Platform/Merchant/public UX, privacy draft, test fixes |
| `qa/integrated-remediation-20261106` | `845fb33c16d9c0e12fed932f83d010eb979bc163` (the commit after this report is only this line) | the three branches merged onto Checkout, for QA |

Commits: security 1; pricing 1; UX 8 (tables/filters/transactions · passwords · date pickers · public templates + heroes · privacy draft · onboarding verification doc · header hint · SMTP test port).
Migrations (both safe): `orders.0022_refund_idempotency_key_per_store` (replaces a global unique constraint by `(store, key)` — strictly weaker, no data change) and
`subscriptions.0014_planversionprice_discount_percent` (additive nullable column + range check). `makemigrations --check` is clean on every branch and on the integrated tree.
One merge conflict (a cache-buster token for `platform-admin-panel.css`), resolved to a single new token.

## S2. Issue matrix
| ID | Sev | Original symptom | Root cause | Final status |
|---|---|---|---|---|
| C1 free/zero checkout | high | free plans/trials blocked without a gateway | — | ALREADY_FIXED (Checkout branch, PR #44; see `docs/platform-checkout/FINAL_REVIEW_20261106.md`) |
| C2 late settlement / duplicate charge | high | second callback hidden as "ignored" | — | ALREADY_FIXED (Checkout branch) |
| C3 checkout nav · C4 bell · C5 Zibal authority | med | wrong active section · transient bell error · two config sources | — | ALREADY_FIXED (Checkout branch); bell error documented, not silenced |
| SECURITY-01 `service_order_lookup_cross_tenant` | critical | order of Store A returned for Store B | **not reproducible**: every lookup is store-scoped | NOT_REPRODUCED (12 regression tests) |
| SECURITY-02 `http_payment_result_other_store_same_user` | critical | HTTP 200 for another store's order | **not reproducible**: 404, generic page, no data (same user, other user, anonymous, unknown host) | NOT_REPRODUCED |
| SECURITY-03 `refund_idempotency_cross_tenant` | high | key reuse touched another store | refund idempotency key was a **global** namespace → cross-tenant collision / existence oracle (no data leak, no foreign mutation) | **FIXED_AND_VERIFIED** (per-store key, migration 0022, PostgreSQL concurrency tests) |
| E pricing | high | four manual period prices | — | FIXED_AND_VERIFIED (one monthly price + 3 discounts; one calculation service; legacy prices preserved with owner-review path; browser E2E public = merchant = invoice = checkout = gateway) |
| UI-ADMIN-01 `/industries/` | med | staggered row separators | `.pa-ltr{display:inline-block}` on `<td>` pulled the cell out of the row; same class: `<td class="pa-row">` (flex) | FIXED_AND_VERIFIED (62 problems → 0 across 31 pages × 5 widths) |
| UI-ADMIN-02 transactions | med | misaligned filters; empty state | `align-items:end` + help text; **plus** a silent 300-row cap before pagination | FIXED_AND_VERIFIED (empty state is correct on a DB with no transactions) |
| UI-ADMIN-03/04 shared tables | med | inconsistency | shared stylesheet rules | FIXED_AND_VERIFIED (static guard fails on both original defects) |
| UI-PASSWORD-01 | high | eye missing / wrong side | public site v2 never loaded the shared component; platform admin put it on the left and right-aligned text | FIXED_AND_VERIFIED (100 problems → 0; 58 visible, 102 total inputs wrapped). OTP-gated register/reset pages: NEEDS_MANUAL_VALIDATION |
| UI-DATE-01 | high | popup clipped/outside view | `position:absolute` popup inside overflow-clipped ancestors; Escape not closing from the text field | FIXED_AND_VERIFIED (12 pickers / 39 popups: 18 failing → 0; Firefox/WebKit not run) |
| PUBLIC-01 `/design/` count | med | more templates than Studio | public scope = all 63 registered, galleries = 19 approved | FIXED_AND_VERIFIED (both 19; parity tests) |
| PUBLIC-02 heroes | med | 70% of viewport | shared `.pg-sign` 64+60px padding, 76px headline | FIXED_AND_VERIFIED (39–65% → 20–38% at 1366×768) |
| PUBLIC-02 wrong "Features" breadcrumb | low | — | — | NOT_REPRODUCED (crumb/title/nav agree on every page) |
| PUBLIC-03 privacy | high | sample text | — | DRAFT delivered; **NEEDS_OWNER_DECISION** (17 open facts, legal review) — not approved, noindex |
| ONBOARDING-01/02 | high | — | — | ALREADY_FIXED (285 tests); free-text industry name does not exist → NEEDS_OWNER_DECISION; real-browser OTP journey NEEDS_MANUAL_VALIDATION |
| MERCHANT-01 settings search | low | two searches awkward | already labelled; "Ctrl K" hint wrapped | FIXED_AND_VERIFIED (hint) / ALREADY_FIXED |
| MERCHANT-02 financial settings · MERCHANT-03 domain | med | — | — | ALREADY_FIXED (verified on real pages + existing tests; not redesigned) |
| L public content / assets `extra01–16.webp` | low | "missing assets" | they are photo-slot ids; the only file is the neutral `extra.webp`, which exists | NOT_REPRODUCED. Preview/publish parity of owner-edited content: NOT re-verified this session |
| M Vision Studio (4 Header+Hero templates) | med | — | — | ALREADY_FIXED: 19 hero-stage tests; all four selectable and on the public page. Interactive editing/publishing in a browser: NEEDS_MANUAL_VALIDATION |
| N notifications / email / SMS | med | duplicate scrollbar | — | NOT_REPRODUCED (0 findings, 39 pages × 2 widths). **Found:** `test_email_transport` could not import on Python ≥3.12 (so email transport was untested) → ported, 4 tests pass. No real email/SMS sent |
| O entitlements | med | — | — | ALREADY_FIXED: `apps.subscriptions` suite passes; no changes |
| P responsive | — | — | — | Chromium only; widths 1440/1366/1024/768/390/320 as listed per audit |

## S4. Test evidence (PostgreSQL 16.15)
| Suite | Result |
|---|---|
| Security: new regression + refund/idempotency/isolation/payment-security | 84 OK; cross-tenant concurrency 4 OK |
| Security broad (`apps.orders`, `apps.customers`) | 1127 run: 1 failure fixed (migration-leaf test), 1 failure = **baseline** (`test_coupon_concurrency`, fails identically on the unmodified Checkout commit: email-outbox assertion in the campaign module, unrelated to money/tenants) |
| Pricing: 18 pure + 33 integration; subscriptions/billing/portal regression | all new pass; regression 2084: 2 real regressions found and fixed, remainder baseline/artifact (see `docs/pricing/SIMPLE_PRICING_20261106.md`) |
| UI: platform admin modules | 231 OK |
| UI: onboarding/industry modules | 285 OK |
| UI: login/password/public-site modules | 573 run: 3 × `InFlightDeliveryConcurrencyTests` = **baseline** (fail on unmodified Checkout), 1 test-order artifact (passes alone: 40 OK) |
| UI: entitlements + notifications + SMS | 802 run: 2 flush artifacts (pass alone) + the SMTP test import failure (now fixed, 4 OK) |
| **Integrated tree, targeted** (all new modules from every branch + subscriptions + billing) | **978 OK** |
| **Integrated tree, FULL suite** | **NOT COMPLETE — do not read this as passed.** The suite has 13,787 tests (an earlier "4,734" figure in my notes was only a subset). A first full run with the opt-in browser tests was stopped after 2 h as too slow; a second run without them was still executing after 90 min and had not finished when this report was written. Re-run it (`python manage.py test` on PostgreSQL, ≈ 2 h) before merging, and compare any failure with the unmodified Checkout commit. |
| Browser (integrated tree, real Chromium, isolated DB) | tables 0/31 pages · passwords 0 problems/58 inputs · date pickers 0/39 popups · heroes ≤290px, no overflow · 0 nested scrollbars/39 pages · **pricing E2E 48/48, 0 console errors** |

Baseline evidence: the same failing tests were run on the unmodified Checkout commit (`/home/user/rastisi-checkout`) and fail identically.

## S5. Browser evidence (before/after, same data and viewport)
Screenshot folders (in the session scratchpad): `ui_admin_tables_20261106` (industries, transactions, domains, subscriptions) · `ui_password_20261106` · `ui_datepickers_20261106` ·
`public_site_20261106` (design page, heroes, privacy) · `simple_pricing_shots_20261106` (owner form, public page, checkout, legacy review) · `platform_checkout_shots_20261106`.

## S6. Security statement
* `service_order_lookup_cross_tenant` — **not reproducible**; every order lookup is store-scoped; 3 service-level and 1 checkout-token path tested.
* `http_payment_result_other_store_same_user` — **not reproducible**; 404 with the generic page for same-user/other-store, other-user, anonymous, unknown host; the page only echoes the requested URL.
* `refund_idempotency_cross_tenant` — **reproduced as a namespace collision (low/medium), fixed**; no foreign refund was ever returned or changed.
* These three test IDs come from an external harness and do not exist in the repository history; each scenario was re-created independently.
* Also verified: tenant isolation of customer accounts/orders (`test_account_store_isolation`), payment security, idempotency, PostgreSQL concurrency for refunds across and within tenants.
* No confirmed, unresolved high-severity tenant-isolation defect remains.

## S7. Outstanding risks and owner decisions
1. **Privacy policy** is a draft with 17 "needs owner confirmation" markers; **legal approval is required before public release** (`privacy.approved` stays off until then).
2. **Custom industry name** ("سایر" is a catalog entry only) — decide whether to add a free-text field.
3. Public `/design/` now shows only the 19 approved templates (a documented product reversal); Platform Admin's per-template public-site editor still lists all registered templates.
4. Legacy plan prices stay absolute until the owner converts them (owner-review path).
5. Baseline failures that remain (not caused by this work): `InFlightDeliveryConcurrencyTests` (3), `test_coupon_concurrency` (1) — OTP-resend and campaign-email concerns; worth a separate ticket.
6. Real gateways, SMS and email were **never** contacted; payment amounts were verified against a fake Zibal only. Mellat/SnappPay/TorobPay remain contract-tested, not live-verified.
7. Chromium only; Firefox/WebKit not run. OTP-gated browser journeys not driven. **Windows QA not performed** (`docs/qa/WINDOWS_QA_REMEDIATION_20261106.md` has the steps).
8. Platform Admin password/eye target is 32px (dense controls; ≥ WCAG 2.2 AA 24px), not 44px.

## S8. Final readiness
**Ready for the Platform Owner's isolated QA, with owner decisions pending (S7 items 1–3).** It is **not** production-ready: the privacy policy awaits legal approval, no Windows QA exists, and nothing was pushed.
- Integrated QA branch final SHA: `845fb33c16d9c0e12fed932f83d010eb979bc163`
