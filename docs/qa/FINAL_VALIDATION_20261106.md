# Final remediation validation before Windows QA — 2026-11-06

Branch `qa/final-validation-20261106`, based on `qa/integrated-remediation-20261106` (`424cef91446af2cc422512979e5c2fa32c97cfdf`). **Local only: nothing pushed, merged, deployed, migrated or backfilled.**
Production server and every existing Windows QA directory/database were never touched. **Windows QA was not performed.** The full 13,787-test regression is **NOT COMPLETE** (see §7).

| # | Item | Result |
|---|---|---|
| FV1 | Zero-price SMS packages | FIXED_AND_VERIFIED — one free grant per store; **owner decision recorded** |
| FV2 | Custom industry name for «سایر» | IMPLEMENTED_AND_VERIFIED (backend + Chromium) |
| FV3 | Cross-tenant evidence | scenario 1 & 2 NOT_REPRODUCED (control + mutation proves sensitivity); scenario 3 REPRODUCED on pre-fix code, FIXED |
| FV4 | Transactions pagination, 640 rows | VERIFIED — no missing/duplicate rows; tie-break made explicit (hardening, not a bug fix) |
| FV5 | Integration integrity | VERIFIED (ancestry, single migration leaf per app, upgrade path) |
| FV6 | Windows hand-off | prepared; see `WINDOWS_QA_REMEDIATION_20261106.md` and the hand-off message |

## FV1 — zero-price SMS packages
Details: `docs/billing/SMS_FREE_PACKAGE_POLICY_20261106.md`. Summary: before the fix a price-0 package could be bought repeatedly, each time granting credits (reproduced: 100 → 400 credits).
Now `request_purchase`, `settle_free_purchase`, the unified-checkout state and the merchant view all use the same locked-balance check (`free_package_already_redeemed`): the first redemption grants the credits once;
later attempts are refused (audit `billing.sms_free_purchase_blocked`). Existing completed purchases are unchanged (no backfill, no data migration). PostgreSQL: 8 concurrent redemptions grant once; two stores each get exactly one.
**Owner decision (documented):** the safe default is *one free redemption per store per package*. If you want periodic/promotional repeats, that needs an explicit policy (limit, period, eligibility) — repeats stay disabled until then.

## FV2 — custom industry name
* Selecting «سایر (صنف آزاد)» now requires the seller's real industry name. The server validates (NFKC, Arabic→Persian letters, whitespace/ZWNJ normalisation, 2–80 characters, letters/digits/space and `( ) - . , ، & /` only, at least one letter; markup, control and bidi-override characters rejected). JS only shows/hides the field and disables the button.
* Storage: `StoreIndustryInstallation.custom_industry_name` (`CharField(80, blank, default="")`), additive migration `catalog.0043`. Existing installs keep a blank name and keep showing the template name; ordinary templates ignore a forged name (stored blank).
* Entry points: onboarding step and merchant-admin settings install; both pass the name only for the `other` template. Installed summaries show the name (and the base template on the onboarding summary).
* Tenant isolation: the name lives on the store's own installation row; another owner gets 404 on this store's onboarding URL.
* Tests: `apps/portal/tests/test_custom_industry_name.py` (28) + dashboard settings tests (+4) + opt-in Chromium `test_custom_industry_browser.py` (4: field follows the selected card, button disabled until a valid name, ordinary industry needs no name, server rejects a bad name when the client check is bypassed and keeps the typed value without injecting markup).

## FV3 — cross-tenant evidence
Full tables, fixtures and limits: `docs/security/TENANT_ISOLATION_EVIDENCE_20261106.md`; raw JSON in `docs/security/evidence/`.
The same-user/other-store payment-result scenario returns 404 (generic page, no code/amount/name) for result/start/initiate on every code state tried; with the store filter deliberately removed it returns 200 and leaks the order, so the test would catch it.
The cross-store refund-key scenario fails on the reverted code (Store B refused because of Store A's key) and passes on the fixed code; PostgreSQL races ran on distinct backend pids. **Not proven:** other cross-tenant paths, production data, other proxy/host setups.

## FV4 — transactions pagination
`apps/portal/tests/test_transactions_pagination_large.py`: 640 rows (330 subscription + 310 SMS, 3 stores, 6 statuses, 3 providers) in groups of 7 rows sharing one timestamp (mixing both kinds). Through the real view: 26 pages (25 × 25 + 15), every row on exactly one page, concatenation equals the independently computed total order; tie groups straddling page boundaries lose/duplicate nothing; nine filters/combinations walk cleanly; two walks are identical and an older insert does not reorder newer rows; a page costs a constant number of queries; anonymous/non-staff get nothing.
The previous implementation passed the same test, so this was **not a defect**; the tie-break order (created_at desc, subscription before SMS, pk desc) is now explicit and documented. Not covered: inserts between two page requests (offset pagination can shift by design).

## FV5 — integration integrity
* Ancestry of the final tip (`git merge-base --is-ancestor`): checkout `8ad4b6879859cc97b854108a7436f5d5fc026a8d` ✔, security `c435803724003d7c7ae97311f28696167bbd987e` ✔, pricing `4c6066bd75a5a75aa82bcbbf65b276087fc9e81a` ✔, UI/public-site `a5496e44fa3556be026a65decf4649c543758fc8` ✔, integrated QA `424cef91446af2cc422512979e5c2fa32c97cfdf` ✔.
* Migrations: exactly one leaf per app (19 apps, no conflicts). New relative to the pushed checkout branch: `catalog.0043`, `orders.0022`, `subscriptions.0014` (all additive/weaker). A database migrated at `8ad4b687` upgrades cleanly with these three, `migrate --check` clean; `makemigrations --check` clean.
* `graphify-out/` and `.graphify-venv/` are not tracked; working tree clean.

## 6. Exact targeted tests run on the final tree (PostgreSQL 16.15, all OK)
| Group | Tests |
|---|---|
| FV1 `apps.billing.tests.test_sms_free_package_policy` (policy 13 + PG concurrency 2) | 15 |
| FV2 `apps.portal.tests.test_custom_industry_name`, `apps.dashboard.tests.test_industry_settings_views` | 34 |
| FV2 Chromium `apps.portal.tests.test_custom_industry_browser` (`SFB_BROWSER_TESTS=1`) | 4 |
| FV3 `test_tenant_isolation_regression` (non-PG 10) + `test_strix_scenario_evidence` (HTTP + refund 2) | 14 |
| FV3 PostgreSQL concurrency: regression class 2 + evidence class 2 (each run alone) | 4 |
| FV4 `test_transactions_pagination_large` (9) + `test_platform_admin_tables` (13) | 22 |
| FV5/regression `test_payment_migration_compat`, `test_onboarding_journey`, `test_mandatory_industry`, `test_onboarding_industry_ux`, catalog industry service + registry readiness | 91 |
Earlier in this round: the broader onboarding/industry/owner-registration set (502 tests) ran with 5 problems — 2 caused by this work and fixed (an onboarding colour-literal guard and a legacy test mock signature), and 3 × `InFlightDeliveryConcurrencyTests`, which fail identically on the unmodified pushed checkout commit `8ad4b687` (**pre-existing baseline**, unrelated).

## 7. Remaining blockers and caveats
1. **Full 13,787-test regression: NOT COMPLETE.** Not run to the end in any session; do not read this report as a full-suite pass.
2. Pre-existing baseline failures: `InFlightDeliveryConcurrencyTests` (3, OTP resend) and `test_coupon_concurrency` (1).
3. Windows QA not performed; Chromium only; OTP-gated browser journeys not driven.
4. Owner decisions pending: privacy-policy legal approval; free SMS package policy beyond "once per store"; wording/limits of the custom industry name.
5. The original external-audit test ids are unavailable; scenarios were reconstructed from their descriptions.
