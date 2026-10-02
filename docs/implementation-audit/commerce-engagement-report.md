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
| 16 | Regression + security/perf review | CT — see §5 and §7 | — |
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


## 7. Final pre-merge verification (commit `8d1e08b` + report)

### 7.1 Evidence
* **Browser-level (Chromium via Playwright, PostgreSQL staging DB, `tools/engagement_e2e/`)**
  * Rule builder: **22/22** — nested AND/OR/NOT tree built through the UI, serialised JSON asserted, save, detail, HTMX preview (exactly the 2 expected customers; nothing issued), edit page re-hydrates 4 leaves/2 groups, edit + persist, leaf removal, invalid Jalali date and empty condition rejected with messages and builder state preserved, activate + run + issued-codes tab, no JS errors.
  * Customer/admin workflow: **27/27** — PDP gift-wrap option (price, message appears on select), cart toggle/remove/message edit, server-side invalid and valid coupon, checkout with Jalali birth date, order persisted (gift wrap 20,000, coupon 10 % on items only, edited message), account shows birthday in Jalali, my-coupons tab, admin order page packing instructions, invoice line, customer detail birthday, template edit/preview/unknown-variable rejection/test send, history filters, birthday occasion created in UI → manual run → one 20 % code → second run no duplicate, no JS errors.
* **Migrations (PostgreSQL 16, populated staging copies, never production)**
  * Base-commit schema populated (orders with/without gift wrap, used coupon, outbox rows) → forward migrate: counts equal, grand totals unchanged, `gift_wrap_total`/`scope` backfilled correctly, new columns default safely, legacy coupon `used_count` preserved, `makemigrations --check` clean.
  * Backward: migrated every touched app back to its base migration; **base code read the reverted DB correctly**; re-migrated forward.
  * Scale: 20,004 orders / 20,004 items / 10,002 coupon orders migrated in **15 s**; 10,002 redemption rows created, 0 coupon orders without one; idempotent re-apply verified.
  * New in this pass: `orders.0016_backfill_coupon_redemptions` (legacy orders get a ledger row so cancellation/refund after deployment releases capacity correctly; `used_count` untouched).
* **Regression on the latest code (SQLite, five parallel groups)**: dashboard 1479 OK · catalog/billing/blog/content 1394 OK · core/customers/cart/sms/notifications/engagement/orders 950 OK (4 skipped) · storefront_builder 2617: 30 failures + 2 errors, **identical to the untouched base commit** · portal/stores/subscriptions/shop_core 1284: 1 failure + 1 error, **identical on base** (missing demo media). **Zero regressions attributable to this branch.**
* **PostgreSQL**: orders/cart-gift-wrap/engagement/notifications 495 OK earlier; after the latest changes the 4 concurrency tests (total limit, per-customer limit, limit N, overlapping campaign runs) re-run OK.
* **The 3 baseline guest-cart errors** were a stale fixture (test products created with `stock=0`, so add-to-cart is rejected and the cart stays empty). Verified the merge itself works for stocked products (with gift wrap). They do not touch checkout/coupon/gift-wrap code. Fixtures fixed (`stock=10`); the module passes (22/22).

### 7.2 Security / financial-integrity review (summary)
Checked and covered by tests: server-side recomputation of every amount (client price/gift-wrap price never trusted); owner-only coupons with generic error for wrong customer; capacity via atomic conditional UPDATE + row lock (PG-verified under real threads); idempotent order creation (existing key returns existing order before reserving); redemption lifecycle for failed payment/cancel/refund/retry; refunds net of coupon share and gift wrap with exact-sum rounding across partial returns (per-unit/line/order); no negative totals; store scoping of every admin object and rule-referenced id; permission gating (analyst read-only, 403 on manage); CSRF on all POST actions; template-variable allow-list (no attribute access, HTML escaped in email); PII masked in stored errors; promotional consent vs transactional/security separation; admin audit events for campaign/coupon/template/retry actions.
Defects fixed during verification: PostgreSQL `FOR UPDATE` on outer join in `restock_order` (order cancellation crashed on PG — pre-existing), legacy gift-wrap settings POST regression, stale guest-cart fixtures.

### 7.3 Readiness matrix
| Area | Result |
|---|---|
| Discount engine (rules, scopes, Jalali periods, mandatory Mehr–Aban scenario) | **PASS** |
| Coupon redemption limits, ownership, expiry, windows | **PASS** |
| Concurrent redemption on PostgreSQL | **PASS** |
| Payment-failure / cancellation / refund / partial-return consistency | **PASS** |
| Birthday & other occasions (incl. Esfand-30, annual cycle, idempotency) | **PASS** |
| Birth-date capture (checkout/account) | **PASS** |
| Gift wrapping end-to-end (storefront → order → invoice → admin → refund) | **PASS** |
| Notification system (templates, outbox, retry, consent, history, test send) | **PASS** (see risks) |
| Admin UI incl. rule builder (Chromium) | **PASS** |
| Migrations (populated PG staging, forward/backward, 20k-order scale) | **PASS** |
| Regression vs base | **PASS** (no new failures; 32 + 2 pre-existing failures documented) |
| Security / financial review | **PASS** with the risks below |
| Real SMS/e-mail provider delivery (credentials/network) | **NOT VERIFIED** |
| Migration on the actual production dataset / production DB | **NOT VERIFIED** (by design, never touched) |
| Campaign evaluation performance at very large customer counts (> 100k customers) | **NOT VERIFIED** |
| Browsers other than Chromium; mobile viewport; screen-reader/keyboard audit of the rule builder | **NOT VERIFIED** |
| Optional features needing a product decision (free product / gift with purchase, lat/long targeting, unified history for legacy SMS, birthday column in customer list) | **NOT IMPLEMENTED** (awaiting approval) |

### 7.4 Remaining risks
1. **Legacy order SMS (welcome, placed, paid, status) are still sent by `apps.sms` and appear in the SMS logs, not in the new notification history** (history covers email for those events and everything for new events). Unifying needs an order FK on `SmsLog` or mirroring — decision required.
2. **Legacy `NotificationOutbox` rows**: rows `FAILED` with `attempts >= 5` are no longer retried automatically (new retry cap); an admin can retry them manually from history.
3. **Promotional consent defaults to opted-in** (`accepts_promotional_*` = true for existing customers). Confirm this meets your legal requirements before enabling promotional campaigns; flipping the default would need a migration decision.
4. **No per-store timezone** exists; all Jalali/period/birthday scheduling uses `settings.TIME_ZONE` (`Asia/Tehran`).
5. `CartItem.unit_price` is a snapshot while order lines re-price at order time (pre-existing); a price change between add-to-cart and order can make line totals differ from cart totals. Not changed here.
6. Scheduler requires a cron/job runner for `run_engagement_jobs` (documented); without it scheduled/occasion campaigns do not run.
7. `store_customer_ids` loads ids in memory; evaluation is chunked but very large stores should be measured before enabling heavy rule trees.
8. Pre-existing unrelated failures remain: 30 failures + 2 errors in `storefront_builder` template-recipe tests and 1 failure + 1 error in the `stores` demo-media command test.


## 8. Architecture audit & duplication review (pre-merge; **findings only — no code changed**)

Method: read-only inspection of every module on the five paths (grep of all call sites, model/field usage, event hooks), one executed probe (legacy SMS renderer, §8.2-A4), plus the test/E2E evidence from §7. Scope rule applied: *do not merge components merely because they look similar* — each overlap below is classified as **legitimate separation** or **actual duplication**.

### 8.1 Master table

Priority: **P1** = fix before/with merge (correctness, security, confusing behaviour) · **P2** = fix soon after merge (drift risk) · **P3** = hygiene / decision.

| # | Subsystem | Existing implementation | New implementation | Actual duplication / overlap | Risks | Recommended action | Pri |
|---|---|---|---|---|---|---|---|
| 1 | SMS **template configuration** | `apps.sms`: `SmsTemplate` (per store/event), `EVENT_VARIABLES`, `DEFAULT_TEMPLATES` (vars `order_code`, `amount`, `shop_name`, `tracking_code`); editor under Settings→SMS | `apps.notifications`: `NotificationTemplate`, `events.EVENTS` (vars `order_number`, `order_total`, `store_name`, `tracking_number`); editor under Notifications | **Real**: 8 events exist in both with two variable vocabularies, two default texts, two editors, two stores. For legacy events the SMS half of `NotificationTemplate` is **ignored at runtime** (dispatcher skips `legacy_sms_event`) — only a badge warns. | Merchant edits the wrong place and nothing changes; "test send" in the new editor renders the *new* template, not what customers receive; vocabulary drift | Make the new editor the single UI: for legacy events it reads/writes `SmsTemplate` through a variable-alias map; stop persisting `NotificationTemplate(sms)` for them. No change to runtime sending. (§8.3-S1) | P1 |
| 2 | **Delivery history** | `SmsLog` (provider, cost, billing; event choices fixed), no order/customer link | `NotificationOutbox` (customer, order, event, status, attempts) | **Real**: legacy order/welcome SMS never appear in the new history; new SMS appear twice (outbox row + `SmsLog` with generic event `notification`, no cross-link) | Admin cannot answer "was customer X told about order Y by SMS?" from one screen; spec §6.9 only partly met | Phase 0 *mirror*: wrap the 6 legacy call sites in one facade that records a `NotificationOutbox` row (status/provider from the returned `SmsLog`, `metadata.sms_log_id`) — **delivery untouched**. Add nullable `NotificationOutbox.sms_log` FK. (§8.3-S0) | P1 |
| 3 | SMS **delivery path** | `send_event_sms`/`send_raw_sms` → `_dispatch` → backend + credit reservation; legacy events sent **synchronously in `on_commit`** | Outbox → `deliver_pending` → `send_raw_sms` (same backend/billing) | Not duplicated: the new system **reuses** the legacy sender/billing correctly (single path to providers, single credit ledger). The *scheduling* differs (sync vs async+retry). | Legacy events still block the request thread on provider latency and have no retry; new events are async | Keep both for now (preserves behaviour). Optional Phase 2 migration of legacy events to the outbox behind a flag **only after** a ≤1-min cron is guaranteed in production. | P3 / decision |
| 4 | SMS/e-mail **template renderer** | `sms_service._render` uses `str.format`; validator regex `\{(\w+)\}` | `template_service.render_text` (strict regex substitution) | **Real + security**: legacy validator accepts `{customer_name.__class__.__name__}` and `.format` evaluates it (probe: validation passed, output `str`). Context values are strings so exposure is limited, but a merchant-authored template can introspect objects. | Format-string injection pattern (low-medium severity, pre-existing) | Replace legacy renderer/validator with the strict one (reject any brace that is not exactly `{allowed_var}`); regression: existing sms template tests + new injection tests. 1 file, no DB. | P1 |
| 5 | **Retry** | `SmsLog` retry (`retry_failed_log`), `SmsOutboxItem` gateway queue (SmsRasti device) | `NotificationOutbox` backoff + manual retry | Legitimate layering: provider/device queue vs notification queue. Cosmetic overlap: two "retry" buttons in two screens | Operator confusion only | Keep; document which retry applies; resolved by #2 | P3 |
| 6 | **Consent / categories** | Legacy SMS: transactional only, no consent concept | `PROMOTIONAL` events gated by `Customer.accepts_promotional_*` | None (legacy has no promotional SMS) | None | Keep | — |
| 7 | **E-mail** | `portal.owner_auth_service.send_mail` (platform owner login) | Outbox e-mail + RTL template | Legitimate separation (platform-level auth mail vs store customer mail) | None | Keep | — |
| 8 | **Customer segmentation vs campaign rules** | `customers.CustomerSegment*` + `dashboard/segment_service` (SQL, flat AND/OR, cached membership) | `engagement/services/rules` (Python, nested, scopes, snapshots) | **Partial**: 8 overlapping predicates (order count, spend, first/last purchase, inactivity, bought product/category, used coupon, tag) implemented twice with **different definitions** — segment `order_count`/first/last count *all* orders (incl. cancelled/unpaid); `total_spent` = PAID incl. cancelled; rules count valid (configurable statuses, non-cancelled, net of refunds). Rules reach segments only via `segment_ids` (cached, may be stale; refreshed by a different cron). | Same customer is "≥3 orders" in a segment and not in a rule; stale membership silently drives campaigns | **Do not merge engines** (different scopes: live SQL listing vs historical per-order evaluation). Extract shared *definitions* (valid-order queryset, lifetime stats) into one module used by rules and CRM refresh; relabel segment fields ("all orders"/"paid"); make `run_engagement_jobs` refresh segments referenced by active campaigns first. (§8.3-G1) | P2 |
| 9 | **Customer order statistics** | `Customer.orders_count/total_spent` (global, only `seed_shop` writes — dead), `CustomerProfile` cached stats (all orders count, paid sum) | `rule_data.load_facts` (valid orders) | **Four** sources of "orders/spent" | Wrong figure shown/used depending on screen | Document canonical definition; later drop the dead `Customer` fields (separate cleanup migration) | P2/P3 |
| 10 | **Coupon validity logic** | `pricing.coupon_is_applicable` (legacy, now used only by 2 old tests + an unused import in `coupon_service`) | `coupon_rules.evaluate_coupon`; `coupon_service.customer_coupons` recomputes status (expired/upcoming/used) | **Real**: 3 copies of "is this coupon usable now" (only `evaluate_coupon` is authoritative in checkout/order creation — verified) | Drift: a rule added to one copy is silently missing in the others (account tab could show "active" for a code checkout rejects) | Add `coupon_rules.coupon_state()` and use it in `customer_coupons`; delete `coupon_is_applicable` + unused import, repoint the 2 tests to `evaluate_coupon`. | P2 |
| 11 | **Coupon usage counters** | `Coupon.used_count` (was read-modify-write) | `CouponRedemption` ledger + atomic CAS | `used_count` is now a **derived cache** of RESERVED+REDEEMED rows; single writer (`coupon_redemption_service`) — verified by grep. Legacy orders were back-filled (0016). | A manual DB edit/admin edit can desync counter and ledger | Keep both (counter needed for atomic CAS); add `verify_coupon_consistency` command (pattern of existing `verify_*` commands) | P2 |
| 12 | **Order ↔ coupon links** | `Order.coupon`, `Order.coupon_discount` | `CouponRedemption.order/coupon/discount_amount` | Intentional snapshot redundancy (financial record vs usage ledger) | None | Keep | — |
| 13 | **Campaign vs Coupon fields** | `Coupon` | `Campaign.coupon_*`, `code_*`, limits | Template→instance copy through the single `_create_coupon` function (no second creation path) | New `Coupon` fields must be mirrored manually | Keep; add a test asserting every campaign-driven coupon field is set (guard against drift) | P3 |
| 14 | **Gift wrap** | `ShopSettings.gift_wrap_*`, `CartItem/OrderItem` snapshots, `gift_wrap_service` | Per-product fields, scope, message, `Order.gift_wrap_*`, refund shares — **all inside the same `gift_wrap_service`** | Good reuse. Residual: (a) dead `CartItem/OrderItem.gift_wrap_line_total` properties (qty×price, ignore scope — would be wrong under per_line/per_order, currently unused); (b) PDP JS preview adds one unit price regardless of scope/qty (server authoritative); (c) legacy `catalog/product_detail.html` keeps an old global-price JS stub | Future developer uses the misleading property | Delete (a) or make scope-aware via the service; make (b) scope-aware or label "estimate"; remove (c) stub when the legacy template is retired | P3 |
| 15 | **Order lifecycle orchestration** | `order_service`, `payment_service.simulate_payment`, `gateway_payment_service`, `refund_service`, `return_service` each call legacy SMS | Same modules now also call `mark_redeemed/release`, `business_events.*`, `engagement_hooks` | **Real orchestration duplication**: the "payment succeeded" side-effects are repeated in two places (simulate + gateway) and must stay in sync; "payment failed" side-effects exist only in the simulate path (gateway failures leave the order pending by design — pre-existing). Cancel and refund are single paths (verified). | A third payment path (e.g. COD capture, bank transfer) will silently miss redemption/notification/event-campaign hooks | Introduce `orders/services/lifecycle.py` (`on_order_created/on_payment_succeeded/on_payment_failed/on_order_canceled/on_refund_completed`) that owns these side-effects; existing modules call it. No DB change. | P2 |
| 16 | **Duplicate-processing risk** | — | outbox `dedupe_key`s, unique `CampaignIssuance`, conditional `UPDATE` on payment, claim/skip-locked | **No duplicate processing found** (matrix §8.4) | — | Keep; the gateway-callback replay path is protected twice (conditional update + dedupe) | — |
| 17 | **Background jobs** | cron commands: `refresh_customer_segments`, `process_notification_outbox`, `expire_inventory_reservations`, … (ADR-49: no worker queue) | `run_engagement_jobs` (campaigns + occasions + reminders + deliver) | Consistent with ADR-49 (reuses the cron pattern). Overlap: both outbox commands call `deliver_pending` (safe: atomic claim). Name overlap "reservation" (inventory vs coupon) is unrelated. Segment cron vs campaign cron have no ordering. | Without a scheduler nothing runs; stale segments feed campaigns | Document a reference crontab (segments → engagement jobs → outbox); see #8 | P2 |
| 18 | **Jalali/date helpers** | `templatetags.persian.jalali` (no timezone conversion), `dashboard_service` helper | `core/jalali_utils` (store-tz aware) | **Real**: 3 conversion sites; the template filter converts a UTC datetime's *UTC date* (pre-existing: dates near midnight may show the previous day) | Off-by-one display | Make the filter delegate to `jalali_utils.format_jalali` (tz-aware); keep output format. Visual regression on templates using `|jalali`. | P3 |
| 19 | **Category/line matching** | — | `coupon_rules.line_is_eligible` (live cart lines, parent-map chain) vs `rules._line_matches` (order snapshot, `ancestor_ids`) | Same semantics ("category incl. descendants") implemented twice; **legitimately different data** (live vs historical) | Drift of descendant logic | Share one `category_ancestor_ids` helper; keep both matchers | P3 |
| 20 | **COD / offline payment** | COD never marks `paid` (existing, "until delivery" — no later transition exists) | Redemption reaches `redeemed` only on `paid`; campaigns count `paid` by default | Pre-existing gap surfaced by new features: COD orders stay `reserved` forever and are invisible to default campaign statistics | Under-counted spend/milestones; coupon capacity held by unpaid COD orders | Product decision: add a "mark paid on delivery/collection" transition (calls the lifecycle facade) or document using `pending` in campaign valid statuses | P2 / decision |
| 21 | **Plan entitlements** | `subscriptions.enforcement` gates segments, products… | Campaigns/occasions/templates/gift-wrap pages are **not** gated | Inconsistent with how comparable features (segments) are limited | Plans cannot restrict the new features | Product decision; add `enforce_can_create_campaign` if required | P3 / decision |
| 22 | **Phone normalisation** | `core.phone` (canonical), `orders.forms.PHONE_RE`, `customers.forms.PhoneCleanMixin` | Uses `core.phone` | Pre-existing triple implementation; new code uses the canonical one | Non-canonical `Customer.phone` values would fail SMS validation (skipped as `invalid_recipient`, never mis-sent) | Out of scope; note only | P3 |

### 8.2 Findings in detail

**A. `apps.sms` vs `apps.notifications`**
1. *What is shared correctly*: SMS from the outbox goes through `send_raw_sms` → `_dispatch` → same backends, same credit reservation/refund, same `SmsLog`. There is exactly one path to providers and one billing ledger. ✔ (legitimate reuse)
2. *What is duplicated*: configuration (#1) and history (#2). The legacy `SmsEvent` list (12 events) and the new registry (24 events) overlap on 8 events with different variable names; the legacy default text for `order_placed` says `{order_code}`/`{amount}` while the new registry's says `{order_number}`/`{order_total}`.
3. *Behaviour to preserve*: legacy events send **immediately in `on_commit`**, inside the request thread, with no retry. The new dispatcher intentionally skips SMS for those events (`legacy_sms_event`) so customers never get two SMS — verified by tests and by the E2E run. Any consolidation must keep this property until Phase 2.
4. *Security probe*: `validate_template_body` + `str.format` accepted `"{customer_name.__class__.__name__} / {shop_name.__len__}"` and rendered it. (pre-existing, merchant-authored input; fix = strict renderer).
5. *Retry/state*: three state machines exist (SmsLog, SmsOutboxItem, NotificationOutbox). They model different things (provider attempt, Android-gateway claim, notification lifecycle) → keep.

**B. Segments vs rules** — see #8/#9. The engines differ structurally (flat SQL rule rows with cached membership vs nested Python tree over historical order snapshots, scopes, Jalali periods, per-order semantics) so a merge would lose either performance of list filtering or per-order semantics. The overlap is in *definitions*, so the consolidation target is a shared definitions module, not a shared engine.

**C. Coupons** — one authoritative evaluator in the money path (verified: `checkout_service.apply_coupon/get_applied_coupon`, `order_service.create_order_from_cart` and the cart all call `cart_totals` → `coupon_rules.evaluate_coupon`). Remaining duplicates are read-side (#10). `Coupon.restrictions` (what the code applies to at checkout) vs `Campaign.rules` (who receives a code) are different concerns and stay separate.

**D. Gift wrap** — extended in place (same service module, same snapshot fields, no parallel model). Three consumers (cart totals, order creation, refund share) all use `gift_wrap_service`; no second price/eligibility implementation was found. Residuals in #14.

**E. Order → payment → cancel → refund → jobs** — see #15–#17. Single paths: order creation (`create_order_from_cart` is the only `Order` creator in production code), cancellation (`change_order_status`), refund (`execute_order_refund`, also used by `complete_return`). Two paths: payment success (simulate vs gateway) — synchronised but duplicated.

### 8.3 Safest consolidation strategies (proposals — not implemented)

**S0 — unified history mirror (P1, additive).** Files: `notifications/models.py` (+`sms_log` nullable FK → 1 migration), new `notifications/services/legacy_sms_facade.py`, call sites `order_service.py` (2), `payment_service.py` (2), `gateway_payment_service.py` (1), `auth_service.py` (2). The facade calls `send_event_sms` exactly as today and then writes one `NotificationOutbox` row (`status` from the `SmsLog`, `provider`, `event_key` mapped via `SmsEvent→event`, `order`, `customer`, `dedupe_key=''`). *Compatibility*: SMS behaviour byte-for-byte unchanged; rows are append-only. *Risk*: row-write failure must not break the order → wrap in the existing `safe_dispatch` savepoint pattern. *Tests*: existing SMS tests unchanged; add: row mirrors Sent/Failed logs, no second SMS, history filter by order shows the legacy SMS, failure of mirroring does not raise.

**S1 — single configuration UI (P1).** Files: `notifications/services/template_service.py` (+`LEGACY_VAR_ALIASES`, `get_template/save_template` delegate to `SmsTemplate` for `legacy_sms_event`), `dashboard/engagement_views.py` (editor), `notification_template_form.html`. Data: copy any existing `NotificationTemplate(sms)` rows of legacy events into `SmsTemplate` (data migration, validated; none expected in production because the feature is new). *Compatibility*: runtime unchanged; `SmsTemplate` stays authoritative. *Tests*: editing in the new UI changes the SMS actually sent by `send_event_sms`; alias translation both ways; invalid variables rejected by the legacy validator.

**S2 — strict legacy renderer (P1, tiny).** `sms_service.validate_template_body/_render` → use `template_service` regex rules with legacy variable vocabulary (`EVENT_VARIABLES`). Tests: attribute/index/format-spec braces rejected; every default legacy template still renders; stored legacy templates scanned by a management check before deploy (any stored template with `.`/`[`/`!`/`:` inside braces is reported, not silently broken).

**S3 — optional async legacy SMS (P3, decision).** Behind `NOTIFICATIONS_ASYNC_LEGACY_SMS=False`; routes the 8 legacy events through the outbox; requires cron ≤ 1 min; changes delivery latency/retry semantics, so only after S0/S1 and with an explicit go decision.

**G1 — shared customer-order definitions (P2).** New `orders/services/order_metrics.py` (valid-order queryset, lifetime stats) consumed by `rule_data.load_facts` and `customer_crm_service.refresh_customer_profile_stats`; segment labels clarified; `run_engagement_jobs` refreshes segments referenced by active campaigns. No schema change. *Risk*: CRM numbers change if the profile adopts "valid-order" semantics — prefer to keep CRM as-is and only share the helper where definitions already match. *Tests*: parameterised check that segment/rule/CRM agree on a fixture with cancelled, unpaid and refunded orders (document intentional differences).

**C1 — coupon read-side cleanup (P2).** Files: `cart/services/coupon_rules.py` (+`coupon_state`), `cart/services/coupon_service.py`, `cart/services/pricing.py` (remove `coupon_is_applicable`), `cart/tests/test_pricing.py` (2 tests repointed). No DB. Plus `verify_coupon_consistency` command.

**L1 — lifecycle facade (P2).** New `orders/services/lifecycle.py`; modules call it instead of the scattered trio. No DB. Tests: one parameterised suite asserting that *every* payment-success entry point (simulate, gateway callback, replay) produces exactly: one redemption `redeemed`, one `payment.succeeded` outbox row per channel, one event-campaign run, one legacy SMS.

### 8.4 Duplicate-processing matrix (verified)

| Trigger | Channels/effects | Protection | Duplicate possible? |
|---|---|---|---|
| Order created | legacy SMS (sync) + e-mail + staff e-mail | SMS legacy-only; outbox `order:{id}` | No |
| Payment success (simulate) | redeem, `payment.succeeded`, event campaigns, legacy SMS ×2 (payment + processing) | state guard (`PAID` raises), dedupe, `on_commit` | No (two SMS is legacy cadence: payment + processing) |
| Payment success (gateway callback replay) | same | conditional `UPDATE … WHERE pending`, `mark_redeemed` idempotent, dedupe | No |
| Payment failure retry | `payment.failed` | dedupe includes transaction count; release idempotent | Intended: one per failed attempt |
| Status change / cancel | `order.<status>`, release | dedupe `order:{id}:{status}`; final-status guard | No |
| Return request / approve / reject | `return.*`, staff mail | dedupe `return:{id}` | No |
| Refund (direct or via return completion) | `refund.completed` | single `execute_order_refund`; dedupe `refund:{id}`; return idempotency key | No |
| Campaign run (manual/cron/overlap) | issuance + `coupon.issued` | unique `CampaignIssuance`, row lock, `issuance:{id}` dedupe; PG test with 3 overlapping runs | No |
| Reminder job re-run | `coupon.expiring` | dedupe `expiring:{coupon}` | No |
| Legacy-event SMS enabled in new editor | would be ignored | `legacy_sms_event` skip | No duplicate, but **config has no effect** (#1) |

### 8.5 Legitimate separations (do **not** merge)
`SmsLog` (provider/billing audit) vs `NotificationOutbox` (notification lifecycle); `SmsOutboxItem` (device gateway queue); segment engine vs rule engine (engines) — only definitions are shared; `Coupon.restrictions` vs `Campaign.rules`; `Order.coupon*` snapshot vs redemption ledger; portal owner e-mail vs store e-mail; inventory reservations vs coupon reservations; the legacy synchronous SMS path until S3 is decided.

### 8.6 Backward-compatibility assessment
All S0/S1/S2/C1/G1/L1 proposals are additive or internal refactors with unchanged external behaviour; the only DB change is the nullable `sms_log` FK (S0) and an optional data copy (S1). Existing data/workflows already verified in §7 (populated PostgreSQL migration, base code reading reverted DB, 3 pre-existing failing groups unchanged). The audit introduced **no code changes**.

### 8.7 Decisions needed from the owner
1. Approve **S0 + S1 + S2** (recommended before or immediately after merge; S2 is a security hardening of pre-existing code).
2. Approve **C1 + L1 + G1** as a post-merge hardening PR.
3. Decide on **S3** (async legacy SMS) and on **#20** (COD "mark paid" transition) and **#21** (plan entitlements) — product decisions, not implemented.

---

## 9. Implementation of S0 + S1 + S2 (approved by the owner; legacy SMS stays synchronous)

Scope respected: no C1/L1/G1/S3, no COD auto-paid, no plan restrictions, no second notification system, `SmsLog` and all historical data untouched, legacy delivery path/billing unchanged.

### 9.1 S2 — strict legacy SMS renderer (`apps/sms/services/template_renderer.py`)
* `sms_service._render` no longer uses `str.format`. Allowed constructs: `{name}` (simple identifier ∈ event allowlist) and `{{`/`}}` (literal braces — keeps valid legacy templates working). Rejected: attribute access, indexing, `!conv`, `:format-spec`, empty/numeric/spaced placeholders, stray braces, any expression. Values are inserted via `str()` and never re-interpreted.
* `validate_template_body` (used by the store dashboard form, the platform-admin editor and the new unified editor) now runs the same tokenizer — closes the hole where `{customer_name.__class__.__name__}` passed validation. Unknown-variable message/behaviour unchanged.
* `owner_otp_service` (platform OTP length bookkeeping) also moved off `str.format`.
* **Compatibility/migration strategy**
  * Audit command `manage.py audit_sms_templates` (read-only by default; classes `ok` / `unsafe_syntax` / `unknown_variable`; also counts now-orphaned `NotificationTemplate` SMS rows for legacy events; `--fail-on-issues` for CI).
  * `--apply --backup FILE` resets only `unsafe_syntax` bodies to the event default after writing the originals to the JSON backup (refuses without `--backup`). `unknown_variable` templates (already non-sending before) are reported, never rewritten.
  * Runtime safety net: a *stored* template with unsafe syntax (previously rendered by `str.format`) falls back to the event default text with an ERROR log instead of silently stopping that event's SMS; unknown variables keep the old behaviour (no send). Admin test-send raises instead of falling back.
  * All 12 default templates verified to render byte-identical to `str.format`; `{{`/`}}` cases verified identical.

### 9.2 S1 — unified template administration
* `SmsTemplate` stays the single source of truth for real delivery of legacy events (global, shared by stores — unchanged and now stated in the UI). The notification-template editor for the 8 events with `legacy_sms_event` now **reads and writes that same row** through a validated, bijective alias map (`apps/notifications/legacy_sms.py`: `order_code↔order_number`, `amount↔order_total`, `shop_name↔store_name`, `tracking_code↔tracking_number`, others identical). A test asserts completeness/injectivity/target-validity for every legacy event and lossless round-trip of every default.
* Variables without a legacy equivalent (e.g. `{order_url}`) are rejected with the allowed list; nothing is saved on error.
* Enabled checkbox = `SmsTemplate.is_active` (real effect); reset restores the legacy default; saving deletes the stale, never-used `NotificationTemplate` SMS row so no hidden second copy exists; preview/test-send use the real text.
* Legacy-event SMS editing requires `SMS_SETTINGS_MANAGE` (same as the old settings screen); without it the SMS block is read-only and POST is refused. (Today every role with `SETTINGS_MANAGE` also has it; tested by patching the permission.)
* "Looks active but has no effect" cases removed/flagged: legacy-event SMS banner no longer misleading; a red banner appears on the list and editor when the store's global SMS switch (`ShopSettings.sms_enabled`) is off (applies to all SMS templates).
* The old settings-screen editors keep working and edit the same row (legacy variable names).

### 9.3 S0 — unified history (`apps/notifications/services/legacy_history.py`, migration `notifications.0003_sms_log_mirror`)
* Additive migration: nullable `NotificationOutbox.sms_log` OneToOne → `sms.SmsLog` (SET_NULL). No data migration; `SmsLog` untouched.
* After a legacy send (`send_event_sms`, admin `send_test_sms`, `retry_failed_log`) a **history-only mirror row** is created/synced: event mapped to the new key, status `sent` or `dead` (legacy has no auto-retry), attempts, provider, masked error, `created_at` = the SmsLog time, best-effort customer (by phone) and order (by `order_code` in the send context), `metadata.legacy_sms_log_id/billable_units/cost_toman`.
* No duplicate processing: OneToOne + `dedupe_key=legacy_sms:<id>` + create-or-sync; the outbox worker (`_claim_batch`), `deliver_single` and `retry_notification` ignore mirror rows (guard also survives `SmsLog` deletion through the metadata key). Not mirrored: OTP, platform events, raw `notification` SMS (those already come from the outbox — mirroring would double them), store-less logs, pending logs.
* Mirror failure can never break/alter an SMS send (try/except + log).
* Historical data: `manage.py backfill_sms_history [--store slug] [--dry-run] [--batch-size N] [--limit N]` — idempotent, batched, no links guessed for old rows.
* History UI: “پیامکِ قدیمی” badge; failed legacy rows link to the SMS-log page (credit-aware retry) instead of the outbox retry button.

### 9.4 Tests & verification
* New: `apps/sms/tests/test_strict_renderer.py` (17: injection/format-spec/stray-brace matrix, compatibility vs `str.format`, validator, fallback policy, audit command incl. backup), `apps/notifications/tests/test_legacy_sms_integration.py` (alias-map invariants, unified template service, mirror idempotency/no second delivery/dead handling/retry sync/exclusions/backfill, admin UI incl. permission and disabled-SMS banner, history badge).
* PostgreSQL 16 staging DB: migration 0003 forward/backward/forward OK with 2001 populated `SmsLog` rows; backfill 1200 candidates → 1200 mirrors (otp/notification/store-less excluded), second run 0, no duplicate dedupe keys, `deliver_pending` processed 0, `SmsLog` count unchanged. Reversing 0003 drops only the mirror column (mirrors are rebuildable with the backfill command).
* Regression results: see §9.5.

### 9.5 Regression results (commit `554a7c4`, SQLite, separate processes)
| Group | Result |
|---|---|
| `apps.dashboard` | 1479 tests OK |
| `apps.sms apps.portal apps.notifications apps.engagement` | 713 tests OK (2 skipped) |
| `apps.orders apps.customers apps.cart apps.core` | 725 tests OK (4 skipped) |
| PostgreSQL 16: `apps.notifications`, `test_strict_renderer`, `test_sms_service` | 122 tests OK |

Not re-run for this change (untouched code; previously verified): catalog/billing/blog/content groups; storefront_builder and stores demo-media keep their pre-existing identical failures on the base commit.

---

## 10. C1 — coupon validation consolidation (approved; Task #7)

**Audit (all callers):** `evaluate_coupon` (authoritative; used by `cart_totals` → cart, checkout apply/refresh, `create_order_from_cart`), `pricing.coupon_is_applicable` (public function, used only by tests, partial copy: no ownership/restrictions/per-customer), `coupon_service.customer_coupons` (re-implemented active/expired/upcoming/used with different precedence and ignoring per-customer limits), `coupon_redemption_service` (capacity CAS — the write side of `used_count`, legitimate), campaign reminder/expiry queries (set-based DB filters — legitimate, not per-coupon evaluation), `coupon_service._validate_semantics` (admin input validation — legitimate, different concern).

**Changes (no migration, no interface removed):**
* `coupon_rules.py` now owns the non-cart rules as small pure helpers: `validity_failure` (active + window), `ownership_failure`, `capacity_failure`, `per_customer_used`, `availability_failure` (fixed order: validity → ownership → total capacity → per-customer) and `display_state`. `evaluate_coupon` calls `availability_failure` — behaviour and reason-code precedence unchanged.
* `pricing.coupon_is_applicable` kept (same signature/semantics) as a thin wrapper over those helpers; `customer_coupons` uses `display_state`. Net duplicated rule copies: 3 → 1.
* **Behaviour fix (customer-visible):** an owner's code whose per-customer limit is exhausted now shows “used” in My Coupons (it was shown “active” although checkout rejected it); a rolling window reopens it. Pure display consistency; no pricing/redemption change. State precedence now equals the evaluator's (differs from the old display only for invalid configs `starts_at > expires_at`, which validation already rejects).
* **`manage.py verify_coupon_consistency [--store slug] [--limit N] [--fail-on-issues]`** — strictly read-only. Checks: `used_count` vs ledger (`used_count_drift`), `used_count_over_limit`, config problems (percent range, expiry before start, period without limit, max<min, invalid restrictions), ledger vs order state (`counted_on_canceled_order`, `counted_on_failed_payment`, `released_on_paid_order`, `redeemed_on_unpaid_order`), `order_without_redemption`, cross-store / customer mismatch / personal code used by another customer, `per_customer_limit_exceeded`.

**Tests:** `apps/orders/tests/test_coupon_consistency.py` (10: all surfaces — evaluator, cart totals, `coupon_is_applicable`, My Coupons, order creation — agree for active/inactive/not-started/expired/capacity-full/per-customer/ownership; precedence; legacy signature; command clean after real pay/fail/cancel/reserve flows, detects 10 drift kinds, read-only, scoping, `--fail-on-issues`); PG-only `test_ledger_and_counters_stay_consistent_after_races` (6+3 concurrent orders, zero issues afterwards). Results: SQLite orders/customers/engagement/notifications/cart 585 OK (5 skipped); PostgreSQL concurrency + coupon engine + cart 192 OK (concurrency tests executed, not skipped).

**Finding handed to L1:** `counted_on_failed_payment` is a real possibility on the gateway-failure path (only the simulated payment path releases the redemption on failure) — to be verified in L1.

---

## 11. G1 — shared customer-order definitions (approved with an impact gate; Task #8)

### 11.1 Inconsistencies found (segment engine vs campaign rules engine)
| Aspect | Segments (`segment_service`) — historical | Campaign rules (`rule_data`) | Verdict |
|---|---|---|---|
| Which orders count | **every** order of the store (canceled, unpaid/COD, failed included) | valid: payment status ∈ configured list (default `paid`) and not canceled | **Conflict** |
| Order count | all orders | valid orders | Conflict |
| Total spent | `paid` orders only, **even if later canceled**; gross of refunds | valid orders; `lifetime_spent` gross of refunds (`order_total` leaf is net) | Conflict (cancel) / aligned (gross) |
| Cancelled orders | counted in count/dates/products/coupons; counted in spent if paid | excluded everywhere | Conflict |
| Refunds / partial refunds | `refund_count` = SUCCEEDED refunds (labelled “successful”); no net spending | amount refunded = all refunds except FAILED/CANCELLED (same as `refund_service`) | Legitimately different (count of successful refunds vs. active refunded money) — kept |
| Purchase periods / dates | first/last/inactivity from **any** order | from valid orders, half-open `[start,end)` in store tz | Conflict |
| Purchased product/category/coupon | any order (separate join, not store-scoped on the item join) | valid orders from the order snapshot | Conflict (+ latent cross-store join, see below) |
| Customer stat caches | `Customer.orders_count/total_spent` (dead, never written), `CustomerProfile.total_spent` cache | computed live | Documented, untouched (removal needs migration) |

### 11.2 What was changed (no behaviour change by default)
* New `apps/orders/services/order_definitions.py`: the shared base definitions — `valid_order_q`, `valid_orders`, `active_refunds`, `refunded_amount_subquery`, `net_amount`, default valid statuses, and two named segment definitions: **`LEGACY`** (exact historical behaviour) and **`VALID`** (the shared definition).
* `Refund.INACTIVE_STATUSES = ("failed","cancelled")` — the single “active refund” definition; `refund_service` (5 copies of the tuple) and the rules engine now use it.
* `rule_data.valid_orders_qs` and its refunded-amount subquery delegate to the shared module (pure move, same results).
* `segment_service._matching_customer_ids/evaluate_segment` take a `definition`; default = `current_definition()` = **`legacy`** unless `settings.SEGMENT_ORDER_DEFINITION == "valid"` (unknown value ⇒ legacy). The product/category/coupon rules now apply store + definition on the *same* order join (one `filter`), which is behaviour-identical for same-store ids and closes a latent cross-store join (a rule referencing another store's product id used to match customers who bought it elsewhere).
* Verified identical to the pre-change engine: a one-off differential run of the old module against the new `LEGACY` path over 13 rule/operator combinations on a dataset with cancelled/unpaid/failed/mixed/refunded orders (all equal); golden tests freeze the legacy semantics.
* **`manage.py analyze_segment_definitions [--store] [--sample N]`** — read-only impact report (stored membership, legacy-now, valid, stale-cache drift, would-add/would-remove).
* Preserved separation: persisted cached segments vs live campaign evaluation are unchanged; only base definitions are shared.

### 11.3 Impact analysis of switching segments to `valid` (**NOT applied — approval needed**)
Synthetic but realistic PostgreSQL staging store (2,792 orders: 205 canceled, 209 pending/COD, 121 failed-payment, partial refunds; 1,500 customers; 5 dynamic segments, caches fresh):

| Segment | Members now | Members under `valid` | Would add | Would remove |
|---|---|---|---|---|
| VIP: total_spent > 2,999,999 | 422 | 372 | 0 | 50 (−11.8 %) |
| Repeat: order_count > 1 | 858 | 692 | 0 | 166 (−19.3 %) |
| Lapsed: no purchase ≥ 60 days | 614 | 611 | 63 | 66 |
| Bought product X | 1,274 | 1,173 | 0 | 101 (−7.9 %) |
| New: order_count = 1 | 416 | 481 | 145 | 80 |
| **Total moves** | | | **208** | **463** |

This is a **material change of existing marketing audiences** (up to ~19 % of a segment) → per the instruction the switch was **stopped**; segments keep the legacy definition. Switching later is a one-line setting plus a refresh (`refresh_customer_segments`) after the owner reviews `analyze_segment_definitions` on production data.

Important interaction: **cash-on-delivery orders are never marked paid** (decision: handled by a separate workflow). Under `valid` (and already in campaign rules with the default `paid`) COD customers do not count at all, so the `valid` definition would exclude every COD buyer until payment collection exists. Another reason to keep `legacy` for now.

### 11.4 Defect found (not fixed — needs a migration decision)
`CustomerSegmentRule.operator` is `max_length=20` but the allowed operator `greater_than_or_equal` has 21 characters: on **PostgreSQL** saving such a rule raises `DataError` (HTTP 500); SQLite does not enforce the length. Pre-existing, unrelated to this branch. Fix = widen the column (trivial migration) — awaiting approval because the instruction was to avoid unnecessary migrations. (New tests deliberately avoid persisting that operator so they pass on both databases.)

### 11.5 Tests
`apps/dashboard/tests/test_segment_order_definitions.py` (16): frozen legacy semantics (golden), valid semantics, agreement of `valid` with the rules engine's facts, default/override/unknown setting, store isolation, shared base definitions (valid orders, custom statuses, single active-refund definition consistent between `refund_service` and the rules engine), read-only impact command. Results: dashboard segment suites + engagement + refund 112 OK on PostgreSQL; orders + engagement 445 OK (5 skipped) on SQLite.
