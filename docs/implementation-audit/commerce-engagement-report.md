# Commerce & Engagement Systems — Implementation Report (temporary, living document)

> Do **not** delete this file until the owner explicitly authorises it (Phase 15).

## 1. Environment & Git

| Item | Value |
|---|---|
| Repository | `manouchehr94-ux/Rastisi6-14040616` (Django 5.2, SQLite dev/test, Postgres prod) |
| Base branch / commit | The cloud session started directly on `feature/commerce-engagement-system` at `185166a` ("docs: close storefront vertical slice phase3"). That branch already existed on `origin` and was identical to the project head. |
| Feature branch | `feature/commerce-engagement-system` |
| Worktree | **Deviation:** the task asks for `../commerce-engagement-worktree`. This session is an isolated, ephemeral cloud container whose only checkout already has the feature branch checked out (git refuses a second worktree on the same branch). The container itself is the isolation: no other working tree exists, no shared DB (SQLite test DB is created per run), no real SMS/email/payment providers are configured. Work happens in `/home/user/Rastisi6-14040616`. |
| Initial git status | clean, no pre-existing partial work for these features (verified with `git status`, `grep` for birthday/campaign; `.graphify-venv/` and `graphify-out/` are untracked/ignored and must never be committed) |
| Remote | `origin` (CLAUDE.md mentions canonical remote `rastisi5`; in this container only `origin` exists and the session instructions require pushing to `origin feature/commerce-engagement-system`) |
| Python | use `/usr/local/bin/python` (the `.graphify-venv` python on PATH has no Django) |
| Test command | `/usr/local/bin/python manage.py test apps.<app> --parallel 4` |

Isolation/safety: tests use per-run SQLite DBs, SMS goes through `SmsLog`/backends stubs, email uses Django's locmem backend under test. No migrations are applied to any shared DB. No secrets committed.

## 2. Initial audit (before this task)

### 2.1 Discount / campaign engine
* **Exists (Category B — basic):** `apps.cart.models.Coupon` (store-owned; percent / fixed / free_ship; `min_order`, `usage_limit`, `used_count`, `expires_at`, `is_active`), `apps.cart.services.coupon_service` (CRUD + audit), `pricing.coupon_is_applicable` / `cart_totals`, dashboard coupon CRUD pages, checkout apply/remove, `order_service.create_order_from_cart` increments `used_count` (non-atomic, never released on cancel / failed payment).
* **Exists (Category B):** dynamic customer segments (`CustomerSegment*`, `dashboard/services/segment_service.py`) – flat rule list, no nesting, no product attribute / brand / colour / shipping-destination rules, no Jalali periods.
* **Missing (C):** campaigns, rule trees (AND/OR/nesting/scopes), personalised/owned coupons, max-discount cap, activation date, per-customer limit, redemption ledger, campaign execution/idempotency, issuance tracking, historical product-attribute snapshots on order items, Jalali period utility.
* Bugs found: coupon `used_count` race (read-modify-write), no release on cancel/failure, `Order.coupon` SET_NULL loses history, no owner restriction.

### 2.2 Birthday / occasions / rewards
* Nothing exists: no birth-date field on `Customer`, no checkout field, no occasion scheduler, no consent flags. Category C.

### 2.3 Gift wrapping
* **Category B:** global switch + single price in `ShopSettings` (`gift_wrap_available`, `gift_wrap_price`), per-cart-line selection + price snapshot (`CartItem` / `OrderItem`), `gift_wrap_service`, `cart_totals()["gift_wrap_total"]` (no discount, no tax), storefront-builder cart/product templates and checkout summary mention it, dashboard settings toggle.
* Missing: per-product eligibility/price, pricing scope (unit/line/order), title/description/image config, gift message, separate `Order.gift_wrap_total`, invoice / admin order display, fulfilment visibility, discount-applies-to-wrap rule, cancellation/refund semantics.

### 2.4 Notifications
* **Category B:** `apps.notifications.NotificationOutbox` (+`process_notification_outbox` command), `apps.sms` (templates per event, logs, backends, billing, OTP; events: welcome, otp, order placed, payment success/failed, processing, shipped, delivered, canceled). SMS sent inline via `transaction.on_commit` for order events.
* Missing: email templates/events, per-event channel toggles, unified event registry with variable allow-lists, dedupe keys, retry limits/backoff, promotional-consent handling, history UI w/ filters, manual retry, preview/test-send, return/refund/campaign/occasion events.

### 2.5 Infrastructure facts
* No Celery/Redis: background work is cron-driven management commands (pattern: `process_notification_outbox`). New jobs follow this pattern.
* Multi-tenant: every query must be Store-scoped; `Customer` is global, `CustomerProfile` store-scoped.
* Money: `DecimalField(decimal_places=0)` = **tomans**, no floats.
* TZ: `TIME_ZONE = Asia/Tehran`; no per-store timezone field.
* Orders snapshot address JSON (`province`, `city`) and item name/sku/variant label only → brand/category/colour snapshot needed.
* Test base: existing tests rely on seeded Store `akhlaghi` (migration-seeded).

### 2.6 Baseline test results
See section 5.

## 3. Implementation checklist (actual status)

Legend: **CT** = COMPLETED AND TESTED · **IN** = IMPLEMENTED — NOT TESTED · **NS** = NOT STARTED/NOT IMPLEMENTED (needs decision)

| # | Task | Status | Evidence |
|---|---|---|---|
| 0 | Git/env isolation, report | CT (worktree deviation, see §1) | — |
| 1 | Baseline | CT | 664 tests; 3 pre-existing errors (guest-cart merge → store without ShopSettings) |
| 2 | Jalali utilities (month ranges, Esfand-30 policy) | CT | `apps/core/tests/test_jalali_utils.py` (13) |
| 3 | Order-item historical snapshot | CT | engagement scenario tests (snapshot vs changed catalogue, legacy fallback) |
| 4 | Coupon extensions, redemption ledger, atomic limits | CT | `test_coupon_engine.py` (24); PostgreSQL concurrency `test_coupon_concurrency.py` (3, real threads) |
| 5 | Rules engine (AND/OR/nested/NOT, scopes, validation, cross-store id checks) | CT | `test_campaign_scenario.py` |
| 6 | Campaign services (preview, activate, run, idempotent issuance, capacity, expiry, event/scheduled triggers) | CT | `test_campaign_scenario.py`, `test_integration_scenarios.py` |
| 7 | Mandatory Mehr–Aban 1405 scenario | CT | `MandatoryCampaignTests` (OR≠AND, >10M strict, Shiraz, whole-month boundaries in Asia/Tehran, cancelled/refunded excluded, same_order scope, personal 30%/4M-cap coupon, expiry, notifications, idempotency) |
| 8 | Birth date + consent + checkout/account UI | CT | `test_checkout_birth_date.py` (13), `test_occasions.py::ProfileBirthDateTests` |
| 9 | Occasion engine (birthday before/on/after, anniversaries, milestones, reactivation, holiday, custom) | CT | `test_occasions.py` (22) |
| 10 | Gift wrap (per-product, scope, message, order total, invoice/admin/fulfilment, discount, refund) | CT | `test_gift_wrap_engine.py`, `test_gift_wrap_views.py`, integration scenarios C/D |
| 11 | Notification registry/templates/dispatcher/outbox/retry/consent | CT | `test_dispatcher.py` (32) |
| 12 | Notification admin UI (templates, preview, test send, history, retry) | CT | `test_engagement_views.py::NotificationAdminTests` |
| 13 | Campaign / occasion admin UI + rule builder + coupon form | CT (server side). The JavaScript rule builder (`rule_builder.js`) has **no automated browser test**; it was not exercised in a browser. | `test_engagement_views.py` |
| 14 | Integration: order/cancel/payment-failure/return/refund/events | CT | scenarios A–E |
| 15 | Scheduler `run_engagement_jobs` | CT | `test_command.py` + `run_due_campaigns` idempotency tests |
| 16 | Regression + security/perf review | see §5 | — |
| 17 | Redemption limit within a period (`per_customer_period_days`) | CT | `PeriodLimitTests` |
| 18 | Code validity from delivery (`validity_from_delivery`) | CT | `DeliveryValidityTests` |
| 19 | Free product / gift-with-purchase rewards | NS — optional, needs a product decision (reward model is `coupon | none`) | — |
| 20 | Latitude/longitude targeting | NS — no such data exists in the project | — |
| 21 | Password-recovery / e-mail verification / support-ticket notifications | NS — those workflows do not exist in the project | — |
| 22 | Customer-list birthday column / export | NS — optional (birthday is visible on customer detail) | — |

## 4. Change log (commits on the branch)

1. `226d5cf` Jalali utilities + report.
2. `a62eedc` Coupon engine, ledger, gift wrap, order snapshot, notification core; refunds net of coupon share and gift wrap.
3. `379c38f` engagement app (campaigns, rules, occasions), birth date/consent, my-coupons.
4. `4614f6b` Admin UI (campaigns/occasions/notifications/coupon form), integration scenarios, order indexes.
5. `82e1e1a` Architecture doc `docs/architecture/COMMERCE_ENGAGEMENT_SYSTEM.md`.
6. `f0386e5` Redemption window, delivery-anchored validity, PostgreSQL `FOR UPDATE … of=("self",)` fixes, concurrency tests.
7. `1238c21` Backward-compatible gift-wrap settings POST.

Migrations added: cart 0008+period, catalog 0039, core 0017, customers 0004, notifications 0002, orders 0011–0015 (0013 backfills `Order.gift_wrap_total`), engagement 0001–0002.

Defects found and fixed along the way (pre-existing): `OrderItem.discount_allocation` was never populated; refunds ignored the coupon discount (could exceed what was paid); order cancellation crashed on PostgreSQL (`restock_order` locked a nullable outer join); coupon `used_count` was a racy read-modify-write and never released.

## 5. Test results (actual)

SQLite (default dev/test DB), full suite split into 5 parallel groups on the final code:

| Group | Tests | Result |
|---|---|---|
| dashboard | 1479 | 2 failures (gift-wrap settings POST compatibility) — **fixed**, 119 settings/gift-wrap dashboard tests re-run green |
| storefront_builder | 2617 | 30 failures + 2 errors — **identical set fails on an untouched export of base commit 185166a** (pre-existing, unrelated: template-recipe contract tests) |
| catalog, billing, blog, content | 1394 | OK (1 skipped) |
| core, customers, cart, sms, notifications, engagement, orders | 947 | 3 errors — the same 3 baseline guest-cart errors |
| portal, stores, subscriptions, shop_core | 1284 | 1 failure + 1 error in `test_refresh_rasti_mode_demo_visuals_command` — also fails on base (§5.1) |

PostgreSQL 16 (local, `DATABASE_URL`): orders + cart gift-wrap + engagement + notifications = **495 tests OK, none skipped**, including the 3 concurrent-redemption tests.

Not re-run after the final two small commits: the complete suite as one run (the dashboard group was re-run only for the settings/gift-wrap modules).

### 5.1 Baseline comparison for the stores failures
`test_refresh_rasti_mode_demo_visuals_command` (1 failure + 1 error) fails identically on the untouched base export (pre-existing; demo media files absent). Net result: **no regression attributable to this implementation** in any group; the only regression found (gift-wrap settings POST) was fixed.

## 6. Continuation instructions
* Directory `/home/user/Rastisi6-14040616`, branch `feature/commerce-engagement-system`.
* SQLite: `python manage.py test apps.<app>`; PostgreSQL: set `DATABASE_URL=postgres://user@host:port/db` (the concurrency tests only run there).
* Use `/usr/local/bin/python` (the graphify venv python on PATH lacks Django). `--parallel` crashes on any failing test (traceback pickling) — run groups as separate processes instead.
* Remaining optional decisions: items 19–22 above; browser-level test of the rule builder; dedicated test for the management command.
* Never commit `graphify-out/` or `.graphify-venv/`.
