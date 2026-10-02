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

## 3. Implementation checklist

(Statuses: NOT STARTED / IN PROGRESS / IMPLEMENTED — NOT TESTED / COMPLETED AND TESTED / BLOCKED)

| # | Task | Status |
|---|---|---|
| 0 | Git/environment isolation, report | COMPLETED AND TESTED (see deviation) |
| 1 | Baseline tests for cart/orders/notifications/sms/customers | IN PROGRESS |
| 2 | Jalali utilities (month ranges, birthday cycle, Esfand 30 policy) | NOT STARTED |
| 3 | Order item historical snapshot (brand/category/colour/size/attributes) | NOT STARTED |
| 4 | Coupon extensions + redemption ledger + checkout enforcement | NOT STARTED |
| 5 | Rules engine (AND/OR/nesting/scopes/leaf registry/validation) | NOT STARTED |
| 6 | Campaign models/services (preview, activate, run, idempotent issuance) | NOT STARTED |
| 7 | Mandatory Mehr–Aban 1405 scenario test | NOT STARTED |
| 8 | Customer birth date + consent + checkout/account UI | NOT STARTED |
| 9 | Occasion engine (birthday, anniversaries, milestones, custom) | NOT STARTED |
| 10 | Gift wrapping: per-product, scope, message, order total, invoice, admin | NOT STARTED |
| 11 | Notification event registry/templates/dispatcher/outbox hardening | NOT STARTED |
| 12 | Notification admin UI (templates, preview, test, history, retry) | NOT STARTED |
| 13 | Campaign / occasion admin UI | NOT STARTED |
| 14 | Order/cancel/payment-failure/return integration | NOT STARTED |
| 15 | Scheduler command (`run_engagement_jobs`) | NOT STARTED |
| 16 | Regression run + security/perf review | NOT STARTED |

## 4. Change log
(see bottom; appended per milestone)

## 5. Test log
* Baseline (pre-change): pending.

## 6. Continuation instructions
* Working directory: `/home/user/Rastisi6-14040616`, branch `feature/commerce-engagement-system`.
* Run tests with `/usr/local/bin/python manage.py test apps.<app> --parallel 4`.
* Read this file, run `git log --oneline -15`, `git status`, then pick the first non-completed item in the checklist.
* Never commit `graphify-out/` or `.graphify-venv/`.
