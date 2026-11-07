# Initial Trial engine and in-panel subscription purchase — audit, implementation, evidence (2026-11-07)

Branch `dev/trial-purchase-20261107` (worktree `/home/user/rastisi-trial`), based on `qa/final-validation-20261106` = `976e45003f65ace2ae1ecb1809868aada0d7f470`.
**Local only — nothing pushed, merged, deployed, migrated on any existing database or backfilled.** All tests use PostgreSQL 16 test databases, in-process fake gateways and dummy credentials; no SMS, e-mail or bank was contacted; the QA database `rastisi_qa_final_validation_20261106`, the production server and every older branch were not touched.

## A. Audit of the existing engine and the gaps it had

| # | Finding (with where) | Consequence | Status |
|---|---|---|---|
| G1 | `PlatformConfiguration.default_trial_days` was only a *display token* (`public_site/services._tokens`) and a one-off input to the seed command. A new store's trial length came from the plan version's `trial_days`. | Changing the platform default changed nothing for real stores. | **Fixed** — read live at store creation, frozen into `trial_end_at` |
| G2 | `RASTISI_DEFAULT_PLAN_CODE` is empty by default ⇒ `provision_default_subscription` returned `None` ⇒ **a new store had no subscription = unlimited fail-open entitlements**. Reproduced on a fresh database (`probe`: subscription `None`, products limit `None`). | No Trial and no limits unless an operator knew to set an env var. | **Fixed** — empty means «initial Trial» |
| G3 | The seeded `trial` plan was `is_publicly_selectable=True`: it appeared on `/plans/` and in the merchant plan list. | The internal plan was shown/purchasable. | **Fixed** — internal (data migration `subscriptions.0015` + enforced by `ensure_trial_plan`) |
| G4 | Choosing a plan on `/plans/` then registering started a trial **on that plan** if its version had `trial_days` (`provision_default_subscription(plan_version=…)`). | A second/different trial path; paid plans could carry their own trial. | **Fixed** — the choice is only remembered for the purchase |
| G5 | `trial_eligible` was «once per *plan*». | A store could receive another trial from a different plan/version. | **Fixed** — once per store, any plan, row-locked |
| G6 | `portal.billing_checkout` loaded `PlanVersion` by id with only `status=published` (no public/active/latest filter). | A client could POST the internal Trial, Legacy, archived or older version id. | **Fixed** — `is_purchasable_version` (latest published, active, public); dashboard list uses it too |
| G7 | A store whose trial ended into a **terminal** `expired` state had no current subscription, and both purchase flows refuse «no current subscription». | An expired-trial store could not buy. (Reachable when the trial plan has no grace period.) | **Fixed** — the Trial ends into non-terminal `suspended`; a verified payment reactivates it |
| G8 | Public `/plans/` CTAs for visitors went to `/register/`; for a logged-in owner to the billing page **without plan/period**; no path for «I already have a store» when logged out. | Existing sellers were pushed to sign up; the chosen plan/period was lost. | **Fixed** |
| G9 | No merchant-facing trial status (days left, end date, limits) and no clear «buy» entry; plan page used a `<select>` and showed a raw price. | The seller could not tell they were on a trial. | **Fixed** (card, banner, limits, buy button, period radios with server prices) |
| G10 | No Platform Admin place to manage the Trial (enabled, days, limits, history). | Owner could only edit generic plans. | **Fixed** — «دوره‌ی آزمایشی (Trial)» page |
| G11 | `PENDING` subscriptions give FULL access (`_STATE_POLICY`) and an invoice needs a subscription row. | A «reactivation purchase» that created a pending paid subscription would grant paid entitlements before payment. | **Avoided by design** (G7 fix keeps the existing subscription instead) |

Verified as already correct and reused unchanged: unified platform checkout, invoice/attempt/confirmation services (amount check, idempotent `confirm_payment`, `select_for_update`), callback by public token, `plan_change_billing_service` (idempotent invoice per decision, single competing-invoice invariant), enforcement gates in the service layer (`enforcement.py`), expired/suspended access states (growth closed, reads open, nothing deleted).

## B. What was built

**Policy (single source: `apps/subscriptions/services/trial_service.py`)**
* `PlatformConfiguration.trial_enabled` (new, default ON) and `default_trial_days` (validated 1–365). Both read **straight from the database** when a store is created (an enforcement decision, not a cached display value) and the length is frozen into that store's `trial_end_at`. Changing the default never rewrites a running trial.
* Internal plan `Plan.code="trial"`: `ensure_trial_plan()` is idempotent, never edits an existing version, only enforces «internal (not publicly selectable) and active»; a missing plan/version is created with default limits through the official `plan_service` (products 20, variants 60, team 1, warehouses 1, segments 1, import rows 100/month, exports 5/month, import/export/custom-domain off).
* `grant_initial_trial(store)`: locks the `Store` row, is idempotent, refuses when the store already used a trial (any subscription with `trial_start_at`), disabled ⇒ the store is created on the Trial plan *never started* and `suspended` (restricted, non-terminal, can still buy). Audit entries `trial.granted` / `trial.not_granted_disabled`.
* `RASTISI_DEFAULT_PLAN_CODE`: empty or `trial` ⇒ initial Trial; `none`/`off`/`-` ⇒ no automatic subscription (the old fail-open); any other `Plan.code` ⇒ operator override exactly as before.
* After the Trial: `trialing → suspended` (no grace) or `→ grace_period → suspended` (if the owner configured grace days). Growth (new products/staff/…) is closed with a precise Persian message; data stays readable and is never deleted. A verified payment (`PLAN_CHANGE` invoice from the Trial plan) moves it to `active`.
* Trial and paid period are independent: unused trial days are **not** added to the paid period; `trial_start_at` stays as history so no second trial is ever possible.

**Platform Admin → «دوره‌ی آزمایشی (Trial)»** (`/trial/`, superusers only, nav item under «اشتراک و قیمت‌گذاری»): policy form (enabled, days with validation), limits/feature table for every registered entitlement (numeric: enabled/unlimited/limit; boolean: enabled), grace days, «apply to running trials» (needs a reason; uses `plan_service.migrate_subscribers`), usage summary and paginated history (store, start, end, state, current plan, days left). Every save validates, creates an **immutable plan version** only if something changed, and writes a platform audit entry (`platform_configuration.updated`, `platform_admin.trial_limits_updated`).

**Merchant panel («اشتراک و صورتحساب»)**: trial card (days left, end date, limits with usage, explanation), global trial banner, ended-trial card, a clear **«خرید اشتراک»** button (owner only; other roles see «only the store owner buys»), plans page with only purchasable paid plans, period radios (1/3/6/12 months) with server prices and discount badges, `?plan=&period=` preselection from the public page (validated), preview (amount, effect), invoice, unified checkout, activation after verified payment.

**Public pricing**: the Trial plan is not listed; every card advertises the platform trial length (hidden when the Trial is off); visitors get «شروع N روز دوره آزمایشی» (register keeps plan+period) **and** «قبلاً فروشگاه دارم؛ ورود و خرید» (login `next` keeps plan+period); a logged-in owner gets a buy link to their store's billing page with plan+period and is never sent to `/register/`; the period selector script updates every CTA.

**Roles** (unchanged permission model, now explicit in tests): choosing/buying a plan = `subscription.change` (**Owner only**); paying an *existing* invoice = `billing.payment_manage` (Owner + Administrator); viewing status = `subscription.view` (Owner + Administrator). Analyst/Order/Catalog/Content roles get 403 on plan pages and endpoints and cannot create an invoice.

**Migrations (additive, non-destructive):** `portal.0020_platformconfiguration_trial_enabled` (new boolean default true; help-text alter), `subscriptions.0015_trial_plan_is_internal` (data: sets `is_publicly_selectable=False` for the plan coded `trial` only; reverse is a no-op). No version, price, subscription or invoice is modified. Existing stores are **not** backfilled and keep their current subscription.

## C. Acceptance matrix (your list F)

| # | Requirement | Automated evidence | Real-browser evidence (`tools/trial_qa/e2e_trial.js`) |
|---|---|---|---|
| 1 | New store gets the 30-day Trial | `InitialTrialGrantTests.test_a_new_store_gets_the_default_30_day_trial…` | registered through the real form + OTP: plan `trial`, `trialing`, 30 days, one subscription |
| 2 | Platform owner changes the length → only new stores | `PolicyTests.test_changing_the_default…`, `…read_live…` | changed to 14 in the UI → next store gets 14 |
| 3 | Existing trials keep their length | same + `…limits…old_trials_keep_theirs` | first store still 30 |
| 4 | No second trial | `test_one_trial_per_store_even_after_it_ends…`, `…converted_store…`, `…chosen_paid_plan_never_grants…`, PG race ×8 | paid plan chosen at sign-up ⇒ still exactly 1 subscription |
| 5 | Trial plan hidden from public pricing | `InternalTrialPlanTests`, `PublicPricingSplitTests` | not in `/plans/` cards |
| 6 | Limits enforced in the backend | `TrialLimitsAreEnforcedTests` (product cap, staff, warehouse, feature off, after-expiry growth closed, data kept) | caps shown to the merchant |
| 7 | Trial status visible to the seller | `TrialStatusVisibleToTheMerchantTests` | card, days left, banner, buy button |
| 8 | Buy from an existing store's panel | `PurchaseBase` flows | full flow through the panel |
| 9 | Prices of 1/3/6/12 months = published version | `test_preview_and_invoice_match_the_published_price…` (1,000,000 / 2,850,000 / 5,400,000 / 10,200,000), gateway amount ×10 | page prices, preview, invoice and gateway amount asserted for yearly |
| 10 | Failed/unknown payment never activates | `PaymentOutcomeTests` (cancel, «not paid», unknown code, wrong amount) | cancelled payment leaves `trial|trialing` |
| 11 | Successful (simulated) payment activates | `…activates_exactly_once_for_each_period`, ended-trial and trial-disabled stores | `e2e-pro|active|yearly`, trial history kept, invoice paid |
| 12 | No duplicate subscription/payment under concurrency | `ConcurrentPurchaseTests` (PostgreSQL: 8 simultaneous purchases ⇒ 1 invoice; 6 simultaneous verified callbacks ⇒ 1 activation) | replayed gateway returns ⇒ 1 `activated` event |
| 13 | No other-store purchase/visibility | `AuthorizationAndIsolationTests` | owner 2 gets 404 for store 1's handoff, invoice and data |
| 14 | Legacy compatibility | `test_ensure_hides_a_previously_public_trial_plan_without_touching_versions`, opt-out tests, full existing suites | legacy store's page and subscription unchanged |
| 15 | Responsive | — | 1440 / 768 / 390: no horizontal overflow, RTL, on every page (public plans ×2, platform trial page, merchant overview ×3 states, plans, preview, checkout) |

Screenshots: 12 key images + the full 71-check `results.json` in `docs/qa/trial_purchase_shots_20261107/` (the complete set of 28 — three widths per page — is delivered with this report).

## D. Decisions you may want to change
1. Trial defaults for a *newly created* Trial plan: custom domain, import/export **off**; the seeded Trial plan of an existing database keeps whatever the owner already configured (the page marks keys a version does not define as «not defined ⇒ unlimited/default»).
2. After the Trial, access is *restricted* (suspended: reads open, growth closed), not terminal — chosen so the store can still buy. A grace period can be configured on the Trial page (0–60 days).
3. Per-plan `trial_days` / `trial_once_per_store` on paid plans are now **inert** for registration (they remain editable and stored; the public pages no longer advertise them).
4. Only the Owner can choose/buy a plan (existing permission model). Administrators can pay an invoice the Owner created.
5. A store with a *terminal* (cancelled/expired) subscription still needs a platform-admin reactivation; this work does not add a self-service reactivation (it would have to create a pending subscription, which grants access before payment — see G11).

## E. Limits and unresolved items
* The full 13,787-test regression is **NOT COMPLETE** (same as before) — section F lists exactly what was run; `apps.stores` was only run for the modules touching subscriptions.
* Pre-existing failures reproduced at the base `976e4500` and unrelated: `test_seo.test_terms_and_privacy_are_indexable`, `test_terms_page…cache_busted`, `test_public_site_theme_contract…literal_colors` (privacy-draft/public CSS work), `InFlightDeliveryConcurrencyTests` (3) and the transaction-test-case `setUpClass` artifacts in a full portal run.
* Chromium only; real gateways, SMS and e-mail never contacted; Windows QA not performed.
* The Trial plan page edits `registered` entitlements only (planned features are managed in the assignment matrix, by design).

## F. Test evidence (PostgreSQL 16, disposable databases)

**New tests (68 automated + 71 browser checks)**

| Module | Tests | Covers |
|---|---|---|
| `apps/subscriptions/tests/test_trial_engine.py` | 23 | grant, 30-day default, live read of the setting, disabled Trial, once-per-store (cancelled / converted / chosen paid plan), internal plan (idempotent, hidden, not purchasable), limits enforced (products, staff, warehouse, feature off), after-trial restriction with data kept, grace, merchant `trial_info`, tenant scoping, **PostgreSQL: 8 concurrent grants ⇒ 1 trial** |
| `apps/billing/tests/test_trial_purchase_flow.py` | 23 | merchant status/banner, plan list, 1/3/6/12-month prices vs the published version, gateway amount, failed/unknown/abandoned/wrong-amount payments, activation per period, replay, competing invoices, ended-trial and trial-disabled stores can buy, roles (Owner/Administrator/Order/Catalog/Content/Analyst), cross-store isolation, **PostgreSQL: 8 concurrent purchases ⇒ 1 invoice; 6 concurrent verified callbacks ⇒ 1 activation** |
| `apps/portal/tests/test_trial_admin_and_public.py` | 22 | Platform Admin Trial page (superuser-only, merchants 404, validation, audit, only-new-stores, disable, limits as immutable versions, apply-to-running needs a reason, unchanged save ⇒ no version, history/summary), public pricing split, preselection, portal checkout refuses the Trial plan/older versions, `/register/` for an existing owner |
| `tools/trial_qa/e2e_trial.js` (Chromium) | 71 checks, 71 passed | full flow register (real form + OTP) → Trial → platform owner changes the length → buy from the panel → fake gateway cancel then success → activation → replay → public page as existing merchant → legacy store → other-store isolation → trial end; 1440/768/390 overflow + RTL on every page; no console errors |

**Regression on the final tree**

| Suite | Result |
|---|---|
| `apps.subscriptions` | 222 OK |
| `apps.billing` | 511 OK |
| `apps.portal` | 1437 run: **3 failures, 3 errors — all pre-existing / artifacts** (see below) |
| `apps.dashboard` subscription + industry settings views | 36 OK |
| `apps.notifications` | 465 OK |
| `apps.core` + every `apps.stores` module that touches subscriptions/entitlements/provisioning | 641 run, 30 skipped: OK except 1 setUpClass error (`test_purchase_tracking.ConcurrentRenderTests`, a TransactionTestCase flush artifact — passes alone) |
| `apps.stores` as a whole | **not run to completion** (it exceeded 30 minutes; only the relevant modules above were run) |

Portal leftovers, none caused by this work: `test_seo.test_terms_and_privacy_are_indexable`, `test_terms_page…cache_busted`, `test_public_site_theme_contract…literal_colors` (reproduced identically at `976e4500` in a separate worktree); the three `setUpClass` errors are the known TransactionTestCase flush artifact — `ConcurrencyTests` + `PhoneRequestBudgetConcurrencyTests` pass alone (15 OK); `InFlightDeliveryConcurrencyTests` (3) is the known pre-existing failure.

During this work the regression run found and I fixed: the portal checkout accepted any published version id (G6), a free selectable plan must stay a valid downgrade target (my first gate was too strict), colour literals / inline styles that existing UI guards rejected, and 3 test modules that still encoded the old «no subscription at registration» state (updated to the new contract; opt-outs use `RASTISI_DEFAULT_PLAN_CODE="none"`).

## G. Changed files and commits
44 files changed (+2,143 / −121), commits on `dev/trial-purchase-20261107`:
`6ab79ed6` engine + admin page + merchant/public UI · `e8f682b8` tests + CTA fix · `eabea4ad` browser acceptance, regression fixes, responsive limits list (+ this report in the final docs commit).

Main code: `apps/subscriptions/services/trial_service.py` (new), `subscription_service.py` (initial-Trial provisioning, start_trial(days), two legal transitions), `pricing_page_service.py` (purchase gate, platform trial on cards), `entitlement_service.py` (post-trial message), `apps/billing/services/confirmation_service.py` (reactivate a Trial store on verified payment), `apps/portal/platform_admin_trial.py` + template + nav + urls, `apps/portal/models.py` + migration, `apps/dashboard/*` (overview, plans, preview, banner), public pricing templates/JS/CSS, `shop_core/settings.py` (documentation of `RASTISI_DEFAULT_PLAN_CODE`). Tools: `tools/trial_qa/*`.

## H. Safe transfer to the current QA (PowerShell) — nothing here touches production or any other directory/database
Assumes the QA clone is on `qa/final-validation-20261106` at `976e45003f65ace2ae1ecb1809868aada0d7f470` with a clean tree, PostgreSQL 16 on port 5433, database `rastisi_qa_final_validation_20261106`, web on 18091. The commands only **add** a branch, take a **backup first**, and apply **two additive migrations**.

```powershell
$QA     = "D:\Projects\RastiSi\QA_FINAL_VALIDATION_20261106"      # the existing QA clone (adjust if different)
$BUNDLE = "D:\Projects\RastiSi\_incoming\rastisi_trial_purchase_20261107.bundle"
$PY     = "D:\Projects\RastiSi\V5_VENV\Scripts\python.exe"
Set-Location $QA
git status --short                      # must be empty
git rev-parse HEAD                      # must print 976e45003f65ace2ae1ecb1809868aada0d7f470
(Get-FileHash $BUNDLE -Algorithm SHA256).Hash       # must equal the SHA-256 in the hand-off message
git bundle verify $BUNDLE               # must say "is okay"
```
1. **Stop** the running server on 18091 (Ctrl+C).
2. **Back up the QA database** (outside the repo):
```powershell
$env:PGPASSWORD = "<your QA postgres password>"
& "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe" -h localhost -p 5433 -U <user> -Fc -f "D:\Projects\RastiSi\_backups\qa_before_trial_20261107.dump" rastisi_qa_final_validation_20261106
```
3. **Add the branch and switch** (the old branch is untouched and stays your rollback point):
```powershell
git fetch $BUNDLE "dev/trial-purchase-20261107:dev/trial-purchase-20261107"
git checkout dev/trial-purchase-20261107
git rev-parse HEAD                      # must equal the full tip SHA in the hand-off message
```
4. **Migrate** (exactly two new migrations: `portal.0020`, `subscriptions.0015`) and check:
```powershell
$env:DATABASE_URL = "postgres://<user>:<password>@localhost:5433/rastisi_qa_final_validation_20261106"
$env:DJANGO_DEBUG = "True"
& $PY manage.py showmigrations portal subscriptions | Select-String "\[ \]"     # lists only portal 0020 and subscriptions 0015
& $PY manage.py migrate
& $PY manage.py makemigrations --check --dry-run                                  # No changes detected
```
5. **Start** on the QA port: `& $PY manage.py runserver 127.0.0.1:18091`.
6. **Verify** (synthetic data only; no real bank/SMS/e-mail):
   * Platform Admin → «اشتراک و قیمت‌گذاری ‹ دوره‌ی آزمایشی (Trial)» (`/trial/`) opens; the Trial plan appears there and **no longer** on the public `/plans/`.
   * Create a **new** store through the normal sign-up: its «اشتراک و صورتحساب» shows the 30-day Trial, days left and «خرید اشتراک». Existing QA stores are **not** changed (no backfill).
   * Change the default days in the Trial page, create another store ⇒ it gets the new length; the first keeps its own.
   * Buy a paid plan from the store panel with the **fake/disabled** gateway configuration of your QA (no real merchant id): the invoice amount must equal the published price of the chosen period.
7. **Optional targeted tests** (needs a role allowed to create a *test* database, uses a throw-away name):
```powershell
$env:DATABASE_URL = "postgres://<user>:<password>@localhost:5433/rastisi_trial_tests_20261107"
& $PY manage.py test apps.subscriptions.tests.test_trial_engine apps.billing.tests.test_trial_purchase_flow apps.portal.tests.test_trial_admin_and_public --noinput
```
8. **Browser acceptance (optional, disposable)**: `tools/trial_qa/reset_and_start.sh` is a bash script (Linux/WSL); on Windows run `seed.py` against a *new* database and `server.py` on a *new* port instead of the QA ones (see the file headers). It must never be pointed at the QA database.

**Rollback** (either way restores the previous behaviour; the migrations are additive):
```powershell
# stop the server, then
git checkout qa/final-validation-20261106
& $PY manage.py migrate portal 0019
& $PY manage.py migrate subscriptions 0014
# or restore the backup: pg_restore -h localhost -p 5433 -U <user> -d <db> --clean D:\Projects\RastiSi\_backups\qa_before_trial_20261107.dump
```
