# PR #36 — final acceptance gate (2026-11-04)

Read-only verification of the draft PR (no persistent database touched, nothing merged, nothing deployed). One defect found and fixed (§6).

## 1. Exact PR scope (verified locally and against GitHub)
Base `main@7d31155`; merge-base `676d609` ("sync(r4): publish QA-verified R4-14b source"). **182 commits · 3,129 files · +133,209 / −2,122** (identical to GitHub's PR numbers).

## 2. It contains the ENTIRE prior development history of `feature/gemini-dev-20261102` — not only payments
| Part | Commits | What |
|---|---|---|
| dev lineage (`origin/main..ae8008d`) | 175 | Studio / Storefront Builder, templates, admin modernization, integrations redesign, notification engine, checklist/domain work, SEO/IndexNow, tracking & consent, refund P0 … (2,487 of the 3,129 files are docs; 331 are `storefront_builder`) |
| payment integration (`ae8008d..HEAD`) | 8 | the payment engine, canonical card-transfer, settlement-uncertainty, Purchase tracking, docs, this gate's fix |
Review the payment work with `git log ae8008d..integration/payment-engine-unified-20261104` (≈ 85 files).

## 3. `main`'s two landing-site commits (`e02b63f`, `7d31155`) are not lost or reverted
Simulated merge of the branch into `main` (object-database only; a temporary local detached worktree, removed afterwards):
* `git merge-tree` → **clean, 0 conflicts**.
* The 65 files the landing commits touched: **61 are byte-identical** to `main` in the merged result; the 4 overlapping files (`platform_admin_urls.py`, `platform_admin/base.html`, `portal/views.py`, `shop_core/settings.py`) auto-merge and **all 23 lines the landing commits added are present**. (11 lines of `main`'s older `portal/views.py` that disappear are the dev lineage's own earlier refactors, not landing code.)
* Migrations: landing adds `portal 0013/0014`; the branch's last portal migration is `0012` ⇒ sequential, no clash.
* **Finding (not payment-related, owner decision):** 3 of `main`'s own landing tests fail on the merged result — `test_public_site_v2.DemoStoreAndTemplateCatalogTests` (`templates page lists every real ready template` etc.). They pass on `main` alone (8/8) and fail identically when only the *pre-payment* baseline `ae8008d` is merged into `main`. Cause: the landing templates page reads `ready_template_card_service`, which honors the dev lineage's gallery policy (`RASTISI_TEMPLATE_GALLERY_RESTRICTED`, default restricted to 19 templates) while the landing tests expect the full list (63). Decide: show the full catalog on the public page, or have those tests set `RASTISI_TEMPLATE_GALLERY_RESTRICTED=False`. Not changed here (outside the payment scope).

## 4. Migration graph and how to prove the historical payment migrations were never applied (read-only)
Merged-tree graph (235 migrations): **no conflicts, one leaf per app** — `orders 0021_payment_engine_unified`, `core 0024_tracking_emission`, `portal 0014_public_photo_extra_slots`, `notifications 0004_inbox_engine`, `stores 0020`, `storefront_builder 0022`; `makemigrations --check` clean; a from-scratch migrate of the merged tree and the upgrade of a pre-integration schema with legacy data (PostgreSQL, incl. down/up) pass.
The only risk is a database that ever applied PR #35's migrations (`0020_alter_paymentattempt_status_paymenttransactionevent`, `0021_alter_paymentgatewayconfig_gateway_code`, `0022_alter_paymentgatewayconfig_gateway_code`, `0023_paymentattempt_gateway_redirect_url`). **Owner/DBA read-only check, per persistent database (validated on a scratch DB):**
```sql
-- must return 0 rows
SELECT name FROM django_migrations WHERE app='orders'
 AND name IN ('0020_alter_paymentattempt_status_paymenttransactionevent','0021_alter_paymentgatewayconfig_gateway_code',
              '0022_alter_paymentgatewayconfig_gateway_code','0023_paymentattempt_gateway_redirect_url');
-- expected tail on a pre-integration DB: only 0020_card_transfer
SELECT name FROM django_migrations WHERE app='orders' AND name >= '0020' ORDER BY name;
-- schema fingerprints (PostgreSQL): both must be ABSENT before 0021 is applied
SELECT 1 FROM information_schema.columns WHERE table_name='orders_paymentattempt' AND column_name='gateway_redirect_url';
SELECT to_regclass('orders_paymenttransactionevent');
SELECT character_maximum_length FROM information_schema.columns WHERE table_name='orders_paymentattempt' AND column_name='status'; -- 15 before, 20 after
```
Django-level, also read-only: `python manage.py showmigrations orders`, `python manage.py migrate --plan`, `python manage.py sqlmigrate orders 0021` (and `--backwards`). **If the first query returns rows, STOP** — that database follows PR #35's lineage and needs a hand-written reconciliation (owner-approved) before `0021`.

## 5. Protected features at final HEAD
Ancestors of HEAD: `22ce6d8` (Refund P0), `a1c954f` (snooze), `6ce0649`, `3426352`, `ae8008d`. Refund code and tests are **byte-identical to 22ce6d8** (`git diff` empty). Focused run at final HEAD (refund ×4 modules, card-transfer + consolidation, BNPL UNKNOWN recovery, expiry guard, notification payment/producer/snooze/subscription, tracking/preview/purchase/consent): **263 tests, OK** (5 PostgreSQL-gated skips; they ran on PostgreSQL earlier).

## 6. New providers stay disabled unless legitimately configured and ready
A brand-new `PaymentGatewayConfig` is `is_active=False`, `is_sandbox=False`; no migration or provisioning code creates provider configs or rows (only admin actions and the dev-only `seed_shop`); a fresh migrated DB has 0 configs. Forcing `is_active=True` without credentials ⇒ `not_configured`, never selectable; the five blocked providers stay `documentation_blocked` even with credentials; only Zarinpal/Pasargad/SnappPay/TorobPay with complete credentials in live mode become selectable.
**Defect found and fixed:** a legacy payment-method row whose slug is a registered provider code (e.g. `seed_shop` creates `mellat`; a bare `snappay` row) and that has NO config was still offered at checkout, so a customer could choose a method that has no payment path. `active_payment_gateways` now offers such a row only while a ready config of the same store backs it (`zibal`/`cod` and unrelated slugs keep their legacy behaviour). Regression tests: `test_provider_catalog_checkout` (4 new), `test_feat005…CrossTenantTests` updated to its tenant-isolation intent.
**Non-critical wording finding (left to the owner):** the readiness label `connected` = "متصل و آماده" means *fully configured*, not *proven by a live call* (no live call is authorized). Consider renaming it to "پیکربندی کامل" until a credential-verification call exists.

## 7. Acceptance statement
| Level | Status |
|---|---|
| **Code integration** | Complete: payment engine + canonical card-transfer + settlement-uncertainty + redirect safety + Purchase tracking integrated; merge into `main` is textually clean and landing-site content is preserved |
| **Mocked integration tests** | Complete and green except the documented pre-existing/environment items (30 builder, 2 demo-visuals, coupon-concurrency on PG, `asyncore`); 3 landing tests fail only on the merged tree (§3, unrelated) |
| **Sandbox verification** | **None.** No provider sandbox was exercised (no credentials) |
| **Live provider verification** | **None.** Every provider remains unverified live; five need official contracts |
