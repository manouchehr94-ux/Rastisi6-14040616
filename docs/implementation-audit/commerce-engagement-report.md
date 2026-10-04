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

---

## 12. L1 — minimal order-lifecycle facade (approved; Task #9)

### 12.1 Review of the lifecycle flows
| Flow | Orchestration location(s) | Duplicated? | Decision |
|---|---|---|---|
| Payment **success** (simulated) | `payment_service.simulate_payment` | **Yes — identical 7-step sequence** also in the gateway path | **Extracted** |
| Payment **success** (online gateway) | `gateway_payment_service.process_callback_and_verify` | Yes (same) | **Extracted** |
| Payment failure | `simulate_payment(False)` (simulation only). Gateway failure deliberately leaves the order `pending`, payable, coupon reserved (verified by test) | No (different, legitimate semantics) | Untouched |
| Cancellation | `order_service.change_order_status(→canceled)` is the only path: restock → release coupon → audit → history → event → SMS | No | Untouched (regression-tested) |
| Full/partial refund | `refund_service.execute_order_refund` is the only path (returns call it): refund rows, optional restock, `paid→refunded` + ledger `refunded` on exhaustion, audit, event | No | Untouched (regression-tested) |
| COD | `cod.verify_payment` always returns failure; no code path marks COD paid | n/a | Preserved: never auto-paid |

### 12.2 Change
* New `apps/orders/services/lifecycle.py::apply_payment_success(order, *, store, ref_id, note, from_statuses=None, gateway=None)`: conditional `UPDATE` to `paid` (race-safe; returns `None` and runs **nothing** if the guard fails) → `mark_redeemed` → `payment.succeeded` event → campaign hook (on commit) → compatibility `Transaction` → `change_order_status(PROCESSING)` → `payment_success` SMS (on commit). Guards (what is payable, idempotency, ref-id generation, ValueError messages) stay with the two callers; both now call this single function (≈45 duplicated lines removed). No migration, no data change, public function signatures unchanged.
* Behaviour preserved, including the deliberate edge: a payment on an already-canceled order raises `ValueError` and rolls everything back (test added).

### 12.3 Tests (written first against the pre-change code — characterization — then re-run unchanged after the extraction)
`apps/orders/tests/test_lifecycle.py` (17): simulated vs gateway success produce **identical** effects (payment status, order status, ledger, transaction count, history, notification outbox, SMS); exactly-once effects when repeated; duplicate gateway callback idempotent; second attempt after paid cancelled; no-coupon orders; campaign hook for both paths; canceled-order rollback; failed payment + retry (release/re-take capacity); gateway failure keeps order payable; **COD selection, verification and delivery never mark paid / create an OK transaction / consume the coupon**; cancel of unpaid and paid orders (restock, release, history, single event/SMS, finality); full and partial refunds (ledger `refunded`, capacity not returned, exact sums, events) ending with `verify_coupon_consistency` clean; facade contract (guard ⇒ no side effects, explicit gateway, in-memory order updated). PostgreSQL: 4 parallel payment attempts on one order → 1 success, 3 `ValueError`, 1 OK transaction, ledger redeemed, `used_count`=1, one PROCESSING history row.

### 12.4 Corrections / findings
* The C1 note “counted_on_failed_payment may occur on the gateway path” is **not a defect**: gateway verification failure leaves the order `pending` (retry possible) with the coupon *reserved* by design; the diagnostic only flags `payment_status=failed` (simulation path), which releases the code.
* Pre-existing, not changed (needs a decision): an unpaid online order keeps its coupon capacity reserved until it is canceled — there is no expiry job for abandoned pending orders; a gateway payment that verifies after the order was canceled rolls back and leaves the money unmatched (error is raised to the caller). Both are documented risks, not regressions.

---

## 13. Final regression after C1 + G1 + L1 (commit `HEAD` before this section)

| Suite | Database | Result |
|---|---|---|
| `apps.dashboard` | SQLite | 1494 OK |
| sms, portal, notifications, engagement, core, customers, cart, orders | SQLite | 1467 OK (8 skipped = PG-only) |
| catalog, billing, blog, content, subscriptions | SQLite | 1526 OK (1 skipped) |
| orders, cart, engagement, notifications, sms, segment suites (incl. all concurrency tests) | PostgreSQL 16 | 846 OK |

Not re-run (untouched code): `storefront_builder` and `stores`/`shop_core` — their pre-existing identical failures on the base commit are unchanged (§5.1/§7.1).

### 13.1 Open decisions / remaining architectural risks
1. **G1 switch of segments to the shared “valid order” definition** — stopped; ~8–19 % of members of typical segments would change (§11.3). Needs owner approval after reviewing `analyze_segment_definitions` on production data.
2. **COD “mark paid” workflow** — until it exists, COD buyers are absent from every `valid`/campaign-`paid` statistic and keep coupon capacity reserved.
3. **`CustomerSegmentRule.operator` max_length=20 vs `greater_than_or_equal` (21)** — PostgreSQL DataError on saving such a rule; needs a trivial migration (approval).
4. Abandoned unpaid online orders hold coupon capacity (no expiry job); late gateway success on a canceled order rolls back unmatched (pre-existing).
5. Legacy SMS still synchronous (S3 not implemented, by decision); `SmsTemplate` is global across stores (shared by design, now shown in the UI).
6. Dead fields `Customer.orders_count/total_spent` and the `CustomerProfile.total_spent` cache remain (removal needs migrations).
7. Not verified: real SMS/e-mail providers, production dataset migration, >100k-customer campaign performance, non-Chromium/mobile/accessibility of the rule builder.

---

## 14. Follow-up: segment-rule operator column fix (approved) and standing decisions

### 14.1 Fix
* `CustomerSegmentRule.operator` widened from `max_length=20` to `40` — migration `customers.0005_widen_segment_rule_operator` (single `AlterField`, no data change, no downtime-relevant rewrite; widening a varchar is metadata-only on PostgreSQL).
* Verified on the populated PostgreSQL staging DB (5 segments/rules, 1,500 customers, 2,792 orders): before the migration saving a `greater_than_or_equal` rule raised `DataError: value too long for type character varying(20)`; after it the rule saved, existing rules unchanged, segment refresh results unchanged (416 / 1,274 members as before), `makemigrations --check` clean.
* **Reverse migration** works only while no operator longer than 20 characters is stored (PostgreSQL refuses to narrow otherwise — verified); remove/rename such rules first. Forward/backward/forward cycle verified after removing the test rule.
* Tests (`OperatorColumnLengthTests`, run on SQLite **and** PostgreSQL): every allowed field/operator fits its column; every allowed (field, operator) pair persists and round-trips; a `greater_than_or_equal` segment evaluates. 105 tests OK on PostgreSQL (segment suites + customers), 30 OK on SQLite.

### 14.2 Unchanged by decision
* `SEGMENT_ORDER_DEFINITION` is not set anywhere → `legacy`; no segment membership or campaign audience changed.
* Cash-on-delivery behaviour unchanged (never auto-paid).
* **No automatic coupon-reservation timeout** was added.

### 14.3 Open decisions and their consequences
| # | Decision needed | If decided “yes” | If left as is |
|---|---|---|---|
| 1 | Switch segments to the shared valid-order definition (`SEGMENT_ORDER_DEFINITION="valid"`) | One setting + `refresh_customer_segments`; ~8–19 % of members of typical segments move (§11.3); run `analyze_segment_definitions` on production first | Segments keep counting canceled/unpaid/failed orders; segment and campaign audiences keep disagreeing for the same customer |
| 2 | COD payment-collection workflow (“mark paid” on confirmed cash receipt) | Unlocks correct spend/count statistics, campaign eligibility and coupon `redeemed` state for COD buyers | COD buyers are invisible to `valid`/campaign-`paid` stats; their coupon stays `reserved` forever |
| 3 | Coupon-reservation expiry policy (needs: TTL per gateway type, what happens to a late gateway success, COD handling, who cancels) | Abandoned pending online orders release capacity automatically | Abandoned unpaid orders keep consuming `usage_limit`/per-customer capacity until an admin cancels them; late gateway success on a canceled order rolls back unmatched. **Prerequisite:** define gateway behaviour first (webhook vs callback, retry window) |
| 4 | Remove dead `Customer.orders_count/total_spent` and the `CustomerProfile.total_spent` cache | Migrations; one source of customer stats | Four partially different sources remain (documented) |
| 5 | Async legacy SMS (S3) | Faster checkout, delivery retries for legacy events | Legacy SMS stays synchronous (current behaviour) |
| 6 | Plan entitlements for the new features | New gating logic | Features are available to every plan |
| 7 | Optional features: free-product rewards, lat/long targeting, birthday column in customer list | Separate implementation | Not implemented |
| 8 | Promotional consent default (currently opted-in for existing customers) | Migration to flip default / re-consent campaign | Existing customers can receive promotional messages |

---

## 15. Audit & decision proposal — (A) abandoned unpaid online orders / coupon reservations, (B) cash-on-delivery payment confirmation

**Status: AUDIT ONLY — nothing below is implemented; no code, data or setting was changed. Awaiting approval of the business rules marked ⚑.**

### 15.1 Verified facts (source-checked)
| Area | Fact |
|---|---|
| Order creation | Stock is reserved **and consumed** in the order transaction (`reserve_inventory` + `consume_inventory_reservation`), the coupon capacity is reserved (`CouponRedemption=RESERVED`, `used_count+1`), the discount is baked into `grand_total`. Both are returned **only** by cancellation (`change_order_status(→canceled)`: restock + `release_redemption`). So an abandoned unpaid order holds **stock and coupon capacity**, not only the coupon. |
| Online attempt lifecycle | `PaymentAttempt`: created → requesting → redirect_ready → pending → succeeded/failed/canceled/**expired**. `EXPIRED` exists but **nothing ever sets it**; no background job touches orders or attempts. Only job precedent: cron command `expire_inventory_reservations` (ADR-49, no Celery). |
| Callback | `gateway_callback` (GET, public, store-scoped) → `process_callback_and_verify`: row-lock attempt; **already-final attempt ⇒ returns immediately without asking the gateway**; order already paid ⇒ attempt `canceled`; verify success ⇒ `apply_payment_success` (conditional UPDATE from `pending`) — safe against duplicate/concurrent callbacks (PG-tested). Verify failure ⇒ attempt `failed`, order stays `pending`, coupon stays `reserved`, customer may retry (new attempt). |
| Gap 1 (real) | **No guard against paying a canceled order**: `payment_start`/`payment_initiate`/`initiate_payment` only reject `paid`; a canceled order still has `payment_status=pending`. If the customer pays anyway, `apply_payment_success` → `change_order_status(processing)` raises (canceled is final) → the whole success transaction rolls back (attempt not marked, order unpaid) and the exception is not `PaymentVerificationFailed`, so `gateway_callback` returns a 500 — **money taken at the gateway with no record on our side** (characterised by `test_payment_success_on_canceled_order_rolls_back_atomically`). Also reachable via admin cancellation during an in-flight payment. |
| Gap 2 (real) | A late callback for an attempt that was ever set final (e.g. once expiry exists) would be ignored without verification → real money silently lost track of. Any expiry feature must close this first. |
| COD identification | `initiate_payment` for an offline adapter marks the attempt `succeeded` immediately and **leaves the order `pending`** (by design); `cod.verify_payment` always returns failure; `payment_callback` simulation is the only other writer. An order is “COD” only by the convention `order.payment_gateway.slug == PaymentGatewayConfig.gateway_code == "cod"` (no explicit flag). Delivery (`delivered`, final) never touches `payment_status`; `paid_amount()` = 0 for such orders, so refunds are impossible and every statistic treats them as unpaid. |
| Authorization | Roles use `ORDER_STATUS_CHANGE` (Owner/Admin/Order Manager) and `REFUND_MANAGE`; no permission expresses “confirm money received”. Audit trail via `record_audit_event(request_id=…)` is idempotent. |
| Side effects of “paid” | `apply_payment_success` (L1): conditional UPDATE, `mark_redeemed`, `payment.succeeded` event, campaign hook, OK `Transaction`, **forces PROCESSING**, `payment_success` SMS. |

### 15.2 (A) Proposal — configurable expiry of abandoned **online** unpaid orders
**Principle (⚑ P1):** *expiry = cancellation.* Releasing only the coupon while keeping the order payable is unsafe (the discount is already inside the total). Reusing `change_order_status(→canceled)` gives, in one transaction: restock, `release_redemption`, audit, history, `order.canceled` notification — all existing, tested paths.

**Rules to approve**
1. ⚑ **Setting** `ShopSettings.unpaid_online_order_ttl_minutes` (integer, **0 = disabled — default, so nothing changes on deploy**). Suggested 60 once enabled; must be ≥ the real gateway session lifetime (Zibal value to be confirmed by you) .
2. ⚑ **Scope:** only orders with `status=pending`, `payment_status=pending`, resolving to an **online** gateway. **COD is never auto-expired.**
3. ⚑ **Grace/in-flight protection:** skip an order if any attempt is `requesting/pending/redirect_ready` and updated within `grace` (default 30 min after TTL) or any attempt `succeeded`. Re-check all conditions under `SELECT … FOR UPDATE` on the order row before canceling.
4. **Attempts:** on expiry mark open attempts `expired` (status already exists, no migration) but **keep them verifiable**.
5. ⚑ **Late callback policy** (decision L): *L-A (recommended)* — a callback for an expired/canceled attempt or canceled order is **still verified with the gateway**; if the gateway confirms money was taken the attempt is recorded `succeeded`, the order is **not** reopened or paid, and a **reconciliation item** is raised (staff notification event + admin filter “پرداخت دیرهنگام”) for manual action (reinstate manually or refund outside the system — gateway refunds are not implemented). *L-B* — auto-reinstate if stock and coupon capacity are still available (more code, stock/price races); not recommended for v1.
6. **Guard (recommended regardless of the TTL decision, small bug-fix scope):** refuse payment initiation for canceled orders, and make a verified payment on a canceled order follow rule 5 instead of a 500.
7. **Duplicate callbacks / retries:** unchanged semantics (attempt row lock + conditional update). While unexpired the customer may retry with a new attempt; after expiry they must re-order (cart/coupon are available again).
8. ⚑ **Customer messaging:** send the normal cancellation SMS/email for expiry, or suppress it? (proposal: send email only, no SMS, to avoid noise).
9. **Race protection (required):** the callback path must lock the **order** row before deciding (today it locks only the attempt), so “job cancels” vs “callback pays” serialise.

**Implementation scope:** `ShopSettings` +1 field (additive migration, default 0); new `expire_unpaid_orders` command (cron, `--batch-size`, `--dry-run`, `--store`) + `order_expiry_service`; changes in `gateway_payment_service` (verify-on-final for expired/canceled, order lock, late-payment recording), `views.payment_start/payment_initiate` (canceled guard), `business_events` (+ `staff.late_payment` event), dashboard settings form + order list filter; extend `verify_coupon_consistency` (`stale_unpaid_orders`).
**Risks:** wrong TTL cancels orders customers are still paying (mitigated by grace + in-flight check + verify-on-late); late-payment reconciliation is manual; stock returns to sale (intended).
**Tests required:** TTL disabled = no-op; COD/paid/processing/recent/in-flight orders untouched; expired order cancelled once (restock, ledger `released`, `used_count` back, history, one notification); idempotent re-run; dry-run read-only; callback vs job race on PostgreSQL (real threads) both orderings; duplicate late callbacks; late success on canceled order → recorded, not paid, reconciliation event once; payment initiation on canceled order refused; retries before expiry; coupon re-usable afterwards; `verify_coupon_consistency` clean.

### 15.3 (B) Proposal — COD payment-collection confirmation
**Rules to approve**
1. ⚑ **Who:** new permission `order.confirm_cod_payment` (proposal: Owner, Administrator, Order Manager). Analysts/others: no access (403).
2. **What qualifies:** order is COD, `payment_status=pending`, `status` ≠ canceled (typical: after `delivered`; also allowed while shipped). One confirmation per order, full `grand_total` only — partial cash collection is out of scope.
3. **Input:** collected amount (must equal `grand_total`, prevents mis-clicks), collection method (cash / POS-on-delivery), receipt/reference text (optional), note. Idempotency key per submit (double-click safe).
4. **Reuse:** call the existing `apply_payment_success` (L1) with `from_statuses=(pending,)` — conditional UPDATE guarantees exactly-once: OK `Transaction` (ref = receipt), coupon `reserved→redeemed`, campaign hook, audit event with actor. Needed small change: a flag so COD confirmation **does not force `PROCESSING`** (order may already be shipped/delivered, where the transition is invalid) — advance only when status is `pending`.
5. ⚑ **Notifications:** send `payment.succeeded` (email, and SMS `payment_success`) **once**, or silence both for COD (proposal: send email receipt, skip SMS). Never twice: guarded by the conditional UPDATE + dedupe key `order:<id>`.
6. **After confirmation:** `paid_amount` becomes `grand_total` ⇒ existing refund/return flows, statistics, segments/campaign `paid` rules and `verify_coupon_consistency` start counting the order — **this changes campaign/segment eligibility for COD buyers** (they become valid); flagged because it alters audiences (affects only orders confirmed after go-live; no back-fill without your approval).
7. ⚑ **No undo:** a wrong confirmation is corrected with the existing refund flow (audit trail kept), not by flipping status back.
8. ⚑ **Coupon capacity for COD:** stays `reserved` until confirmation or cancellation (proposal) vs. auto-redeem at `delivered` even without confirmation.
9. **Never automatic:** nothing marks COD paid on delivery, callbacks or imports; COD stays excluded from expiry (A).

**Implementation scope:** permission constant + role mapping; `lifecycle.apply_payment_success(advance_to_processing=…)`; `order_is_cod(order)` helper (single place for the slug convention); `cod_payment_service.confirm_collection(order, actor, amount, method, reference, idempotency_key)`; dashboard order-detail form/endpoint (POST, CSRF, permission); optional additive `Transaction.confirmed_by` (nullable FK) + `method` (default `"gateway"`) migration — or audit-log only if you prefer no migration; audit event `order.cod_payment_confirmed`; order timeline entry.
**Risks:** staff confirming without receiving cash (mitigated by permission, amount match, audit, reference); COD buyers entering segments/campaigns after go-live; notification wording for already-delivered orders.
**Tests required:** permission matrix (owner/admin/order-manager yes, analyst/catalog no, other store 404); non-COD, canceled, already-paid, wrong-amount rejected; confirmation on pending/shipped/delivered orders (no invalid transition); exactly-once under double submit and parallel requests (PostgreSQL threads); one OK transaction, one notification set, coupon `redeemed`, audit with actor; refund after confirmation works and ends `refunded/REFUNDED`; delivery alone never pays; `verify_coupon_consistency` clean; segment/campaign facts include the order only after confirmation.

### 15.4 Suggested increments (after approval)
1. Canceled-order payment guard + verify-on-final/late-payment recording + order-row lock (bug-fix; independent of TTL). 2. Expiry setting + `expire_unpaid_orders` (default off). 3. COD confirmation workflow. Each with its tests, PostgreSQL race tests and a staging-DB migration check.

### 15.5 Decisions requested
⚑ P1 expiry = cancellation · TTL default/suggested value and real gateway session lifetime · grace length · late-payment policy L-A vs L-B · expiry customer messaging · COD permission/roles · COD notification policy · COD coupon capacity until confirmation vs auto-redeem at delivery · no-undo (refund-only) · whether COD buyers may become segment/campaign-eligible after confirmation · additive `Transaction` fields vs audit-log only.

---

## 16. Implementation of the approved §15 workflows

### 16.1 Milestone M1 — payment safety (done, Task #10)
**Behaviour implemented**
* **Canceled-order guard:** `initiate_payment` re-reads the authoritative order state and raises `OrderNotPayableError` for canceled orders (stale objects included) — no attempt is created; `payment_start`, `payment_initiate` and the simulation callback refuse canceled orders; the payment-result page now tells the customer a canceled order cannot be paid (and no longer claims “no money was deducted” for a canceled order; it also displays the `error`/messages that were previously ignored).
* **Locking:** `change_order_status` now locks the order row and syncs the caller's stale object from the database before validating the transition; the callback path locks **order first, attempt second** (same order as cancellation/expiry) — cancel and callback serialise. Blind attempt-status writes were replaced by conditional updates (a concurrent callback's `SUCCEEDED` can no longer be overwritten — this race was found by the new PostgreSQL test and fixed).
* **Always verify:** a callback for any attempt that is not `SUCCEEDED` — including `failed`, `canceled`, `expired` — is verified with the gateway (an attempt without a track id is not sent). Already-`SUCCEEDED` attempts return idempotently without a second gateway call. Failed verification of an already-final attempt changes nothing.
* **Confirmed money is never lost:** new persistent model `orders.PaymentReconciliation` (one per attempt, additive migration `orders.0017`): kinds `order_canceled`, `already_paid` (duplicate payment, incl. a second confirmed attempt), `not_payable`, `processing_error` (exception while applying — runs in a savepoint so evidence survives). The attempt is recorded `SUCCEEDED` with the gateway reference and sanitised evidence; the order is **not** reopened, **not** marked paid, **no** OK transaction, coupon **not** re-reserved, stock **not** re-consumed. One staff e-mail (`staff.late_payment`, dedupe per record; SMS off by default) and a dashboard page **Finance → تطبیق پرداخت‌ها** (list open/resolved; resolve with outcome + note requires `REFUND_MANAGE`; audit event; idempotent; store-scoped; analysts view-only; catalog manager 403).
* **No uncontrolled 500:** `gateway_callback` catches unexpected exceptions, logs them, redirects to the result page with a notice; a late/duplicate payment shows a “payment received, will be reviewed” notice.
* Policy change (deliberate, per approval): the old rule “order already paid ⇒ cancel the attempt without asking the gateway” could silently lose a second real payment; it now verifies first (gateway failure ⇒ attempt `canceled` as before; gateway success ⇒ `already_paid` reconciliation).

**Files:** `apps/orders/models.py` (+`PaymentReconciliation`), migration `orders/0017_payment_reconciliation.py`, `services/gateway_payment_service.py` (rewritten callback flow), `services/order_service.py` (lock), `views.py`, `templates/orders/payment_result.html`, `apps/notifications/events.py` + `services/business_events.py` (`staff.late_payment`), `apps/dashboard/payment_reconciliation_views.py`, `urls.py`, `templates/dashboard/payment_reconciliations.html`, `base_admin.html` (nav).

**Tests:** `test_payment_safety.py` (15: guard for services/views/stale objects, late success on canceled order — nothing applied & evidence + one e-mail, duplicate late callbacks without re-verification, expired/canceled/failed attempts verified and applied when order still payable, failed verification of final attempts changes nothing, no track id, processing-error preservation, callback view never 500, notice shown, second confirmed attempt reconciled, retry after failure, admin permissions/resolve idempotency/audit/store scope) and PostgreSQL-only `test_payment_concurrency.py` (callback vs cancellation ×8 with invariant “money is either applied or reconciled — never lost, never both”, exactly-once restock/coupon release; 5 parallel duplicate callbacks; two confirmed attempts for one order). Two existing assertions were updated to the new verify-always policy (`test_gateway_payment_service`, `test_lifecycle`). Results: orders + engagement views + notifications 501 OK on SQLite (9 skipped = PG-only); payment/lifecycle/coupon-concurrency suites 55 OK on PostgreSQL, concurrency file re-run 3× stable; migration 0017 forward/backward/forward on the staging PostgreSQL DB.

**Operational notes:** staff e-mail goes to store owners with an e-mail address and optional extra recipients (template editor); with none configured the dashboard page is the only channel — check it regularly. Gateway amount mismatches are still treated as verification failures (no reconciliation record) — see risks.

### 16.2 Milestone M2 — expiry of abandoned online orders (done, Task #11; **ships disabled**)
**Behaviour implemented**
* Per-store settings (`ShopSettings`, additive migration `core.0018`): `unpaid_online_order_ttl_minutes` (**default 0 = disabled**), `unpaid_online_order_grace_minutes` (default 30), `unpaid_expiry_notify_sms` (default off). Dashboard: Settings → Finance → «انقضای سفارش‌های پرداخت‌نشده» (needs `SETTINGS_MANAGE`; value must be 0 or ≥ 15; audit event; the card warns to confirm the gateway session lifetime first).
* Job: `manage.py expire_unpaid_orders [--store slug] [--dry-run] [--batch-size N]` (cron every 5–10 min, ADR-49). Only stores with TTL > 0 are touched.
* Eligible = `status=pending`, `payment_status=pending`, older than TTL, **definitely online** (order's gateway slug matches an online `PaymentGatewayConfig`, or the order has an attempt on an online gateway). **COD and any order without online evidence are never expired.**
* Skipped: any `SUCCEEDED` attempt (confirmed payment) and any open attempt (`requesting/pending/redirect_ready`) updated within the grace period (callback in flight). All conditions are **re-checked under `SELECT … FOR UPDATE` on the order row** (same lock order as the payment callback and cancellation).
* Action: open attempts → `EXPIRED`; then the **existing lifecycle** `change_order_status(→canceled)`: stock restored once, coupon ledger `released` + `used_count` decremented, history/audit (`order.payment_expired`), exactly **one** `order.canceled` transactional e-mail (dedupe `order:<id>:canceled`); the legacy cancellation SMS is suppressed unless `unpaid_expiry_notify_sms` is on (`change_order_status(suppress_sms=…)`, default unchanged for every other caller).
* Idempotent (a canceled order is no longer a candidate); a late callback for an expired attempt is verified and reconciled by M1; coupon capacity is reusable immediately.
* **Zibal session lifetime / callback behaviour: NOT VERIFIED.** The sandbox cannot reach Zibal's documentation (egress blocked) and public search results do not state the trackId lifetime. The repo's adapter treats result `201` (already verified) as success, which makes replayed callbacks safe. **Action for you:** confirm Zibal's session lifetime and callback retry rules before setting a TTL (it must exceed the session lifetime; 60 min is only the proposed value). Until then the setting stays 0.

**Files:** `apps/core/models.py` + `migrations/0018_unpaid_order_expiry_settings.py`, `apps/orders/services/order_expiry_service.py`, `management/commands/expire_unpaid_orders.py`, `services/order_service.py` (`suppress_sms`), `apps/dashboard/forms.py` (`OrderExpirySettingsForm`), `views.py` (`settings_order_expiry`), `urls.py`, `partials/settings_finance.html`.

**Tests:** `test_order_expiry.py` (15: disabled no-op; full effects once incl. attempts EXPIRED/stock/ledger/one e-mail/no SMS/audit/consistency; SMS only when enabled; coupon reusable; expired order unpayable + late payment reconciled; recent/paid/processing/COD (incl. COD attempt)/unknown gateway untouched; online-evidence by attempt; in-flight/confirmed skipped; grace boundary 29/31 min; dry-run & store scoping; command; settings form validation/audit/permission) and PostgreSQL `test_payment_concurrency.py` additions (expiry job vs callback ×8 with “money applied or reconciled, never lost”, exactly-once restock/ledger; 4 parallel expiry jobs cancel once, one e-mail). Results: orders + settings views + notifications OK on SQLite (11 skipped = PG-only); payment/expiry concurrency suite 5 OK on PostgreSQL, re-run 2× stable; migration `core.0018` applied on the staging PostgreSQL DB, `makemigrations --check` clean, dry-run command works.

**Operational requirements:** schedule `expire_unpaid_orders`; keep TTL 0 until the gateway lifetime is confirmed; watch **تطبیق پرداخت‌ها**; the cancellation e-mail template can be edited in Notification templates (`order.canceled`).

### 16.3 Milestone M3 — COD payment confirmation (done, Task #12)
**Behaviour implemented**
* Permission `order.confirm_cod_payment` (new): **Owner, Administrator (all-permissions), Order Manager** only; Analyst/Catalog Manager/Content Editor get 403.
* Dashboard order page shows «تأیید دریافتِ وجه (پرداخت در محل)» only to authorised users and only while the order is COD, unpaid and not canceled. Fields: amount (must equal `grand_total` exactly; thousands separators accepted), method (cash / POS), optional receipt reference (≤ 60), hidden per-render token (audit `request_id`). POST-only, CSRF, store-scoped (other store → 404).
* Service `cod_payment_service.confirm_collection`: locks the order row; rejects canceled, non-COD (COD = gateway slug `cod` or an offline `PaymentGatewayConfig` of the same name), non-pending payment, wrong amount/method/reference; a second confirmation raises `AlreadyConfirmed` and changes nothing.
* **Reuses `lifecycle.apply_payment_success`** (conditional UPDATE `pending→paid`, so duplicates and parallel requests are impossible) with three new opt-outs: `advance_to_processing=False` (**order status preserved** — pending/processing/shipped/delivered all stay as they are, no status-history row), `send_sms=False`, and `method`/`confirmed_by` recorded on the transaction. Effects: one OK `Transaction` (additive fields `method`, `confirmed_by`, `confirmed_at`; receipt reference in `ref_id`; migration `orders.0018`, existing rows default to `gateway`), coupon `reserved → redeemed`, **one** `payment.succeeded` **e-mail** receipt (dedupe `order:<id>`), **no SMS**, campaign hook, audit event `order.cod_payment_confirmed` with actor/amount/method/reference.
* **Coupon capacity stays reserved** for COD until confirmation or cancellation (verified even for delivered orders); cancellation still releases it.
* **No automatic payment and no backfill:** delivery/status changes/callbacks never pay COD; historical COD orders stay `pending` (test). After confirmation the order is a normal paid order: it enters paid-order statistics, refunds, and (by their existing definitions, unchanged) segments/campaigns.
* **Corrections** only through the existing refund flow (full/partial → `refunded`, ledger `refunded`); the original confirmation transaction/audit record is never edited or removed (test).
* Order detail also shows “confirmed by / when / method / receipt” for manually confirmed payments.

**Files:** `apps/stores/authorization.py`, `apps/orders/models.py` + `migrations/0018_transaction_cod_confirmation.py`, `services/lifecycle.py`, `services/cod_payment_service.py`, `apps/dashboard/cod_views.py`, `urls.py`, `views.py` (order-detail context), `templates/dashboard/order_detail.html`.

**Tests:** `test_cod_confirmation.py` (16: status preserved at every stage with exactly-one transaction/receipt/no SMS/no history row, e-mail-only receipt, coupon reserved-until-confirmation, audit, no backfill, statistics only after confirmation, consistency clean, duplicate rejection incl. different token, invalid amount/method/reference/canceled/non-COD/other-store changes nothing, separators, delivery never pays, refund correction + audit trail intact, dashboard permission matrix for 6 roles, form visibility/flow/idempotent repeat, wrong amount & online order rejected, other-store 404 and GET 405) and PostgreSQL `test_payment_concurrency.py` additions (5 parallel confirmations → 1 ok/4 `AlreadyConfirmed`, 1 transaction, 1 e-mail, ledger redeemed once; confirmation vs cancellation ×6 serialised with no half-states). Migration `orders.0018` forward/backward/forward on the staging PostgreSQL DB.

**Operational requirements:** grant the permission by role only (no per-user override exists); staff must confirm only after real collection (amount, method and receipt are audited); the receipt e-mail needs the customer's e-mail address and an enabled `payment.succeeded` e-mail template.

### 16.4 Final regression after M1–M3 (commit `271be59`)
| Suite | Database | Result |
|---|---|---|
| `apps.dashboard` | SQLite | 1496 OK |
| sms, portal, notifications, engagement, core, customers, cart, orders | SQLite | 1520 OK (15 skipped = PostgreSQL-only) |
| catalog, billing, blog, content, subscriptions | SQLite | 1526 OK (1 skipped) |
| `apps.stores` (includes the new permission matrix) | SQLite | 660 run: only the known pre-existing demo-media pair fails (`test_refresh_rasti_mode_demo_visuals_command`: 1 failure + 1 error, identical on the base commit); the extra `shop_core` “error” is a wrong module label in my command line, not a test |
| orders, cart, engagement, notifications, sms, customers, segment/order/settings view suites (incl. all concurrency tests) | PostgreSQL 16 | 1,096 run: 1 error — `AppearanceRenderingRegressionTests.test_appearance_page_renders_when_legacy_blank_tokens_present` (`DataError: value too long for varchar(7)`), **identical on the untouched base commit** (a SQLite-only fixture writing an over-long colour value); everything else OK |
Not re-run (untouched code): `storefront_builder` (its pre-existing failures, §7.1).

### 16.5 Operational requirements and remaining risks after M1–M3
**Operate:** (1) schedule `manage.py expire_unpaid_orders` (every 5–10 min) — only needed once a TTL is set; **leave the TTL at 0 until Zibal's session lifetime and callback retry behaviour are confirmed (NOT VERIFIED here: docs unreachable)**; (2) staff should watch Finance → تطبیق پرداخت‌ها and make sure store owners have an e-mail address (that is the `staff.late_payment` recipient); (3) grant COD confirmation only through roles (Owner/Administrator/Order Manager); (4) apply migrations `orders.0017`, `orders.0018`, `core.0018` (all additive; verified on the populated staging DB).
**Risks / decisions still open:**
1. A gateway **amount mismatch** on a late/duplicate callback is still treated as a verification failure (attempt `failed`, no reconciliation record) although money may have moved — worth a follow-up so mismatches also raise a reconciliation item.
2. Late-payment resolution is manual; gateway refunds are still not implemented.
3. Expiry relies on “definitely online” evidence (gateway slug match or an online attempt); orders from unrecognised legacy gateway names without attempts are deliberately never expired.
4. COD confirmation does not advance the order to *processing* by design (admin controls the fulfilment flow); confirmation cannot be undone except by refund.
5. Newly paid COD orders enter statistics, segments (legacy definition — unchanged) and campaigns from confirmation onwards; no backfill.
6. Staff e-mail for late payments only goes to owners with an e-mail address / configured extra recipients; otherwise the dashboard list is the only channel.
7. Pre-existing and unrelated: SQLite-only appearance fixture (above), storefront_builder/stores demo-media failures.

## 17. Comprehensive production-readiness hardening (nine outstanding risks)

Scope: resolve the nine outstanding risks with the existing architecture only. Branch `feature/commerce-engagement-system`, base of this phase `ca0b11e`.
No merge, no deployment, no live-database migration, `SEGMENT_ORDER_DEFINITION` still `legacy`, COD still never auto-paid, report kept.
Labels: **DONE AND VERIFIED**, **IMPLEMENTED — EXTERNAL VERIFICATION PENDING**, **BLOCKED — AUTHORIZED ACCESS REQUIRED**, **BLOCKED — OWNER DECISION REQUIRED**, **NOT STARTED**.

### 17.0 Status and evidence

| # | Issue | Status | Evidence |
|---|---|---|---|
| 1 | Gateway amount mismatch / reconciliation | **DONE AND VERIFIED** (against the documented Zibal contract; real gateway behaviour is item 3) | `test_payment_discrepancy.py` (22 tests) + PostgreSQL races in `test_payment_concurrency.py` |
| 2 | Promotional consent / existing-customer migration | **IMPLEMENTED — OWNER DECISION REQUIRED** for legal wording/basis and per-store vs per-account consent; engineering acceptance criteria met | `test_promotional_consent.py` (22 tests incl. migration, PostgreSQL-verified); migration run on 100k-customer PostgreSQL |
| 3 | Zibal session lifetime / callback behaviour | **BLOCKED — AUTHORIZED ACCESS REQUIRED** (docs + sandbox unreachable); TTL stays 0; checklist in PRODUCTION_CONFIGURATION §12.2 | adapter-contract tests; egress blocked (`help.zibal.ir` denied by the proxy) |
| 4 | Real SMS/e-mail delivery | **IMPLEMENTED — EXTERNAL VERIFICATION PENDING** (no provider credentials/network) | `verify_delivery_channels` + 6 tests; existing backend contract tests; operator commands in §12.3 |
| 5 | Cron/background jobs | **IMPLEMENTED — EXTERNAL VERIFICATION PENDING** (no scheduler available; no claim that cron runs in production) | `test_background_jobs.py` + PostgreSQL advisory-lock test; `check_background_jobs`; crontab template |
| 6 | Migration safety | **DONE AND VERIFIED** on representative synthetic PostgreSQL data; **production rehearsal outstanding** (no sanitized production copy) | §17.6 |
| 7 | Cart/order pricing consistency | **DONE AND VERIFIED** | `test_checkout_price_confirmation.py` (19 tests) + PostgreSQL parallel-checkout test |
| 8 | Campaign performance at 100k+ | **DONE AND VERIFIED** (budgets met; one documented scaling limit: issuance throughput) | `tools/bench/campaign_benchmark.py`, §17.8 |
| 9 | Cross-browser / mobile / accessibility | **IMPLEMENTED — EXTERNAL VERIFICATION PENDING** (Chromium verified; Firefox/WebKit runtimes not installed) | `accessibility_e2e.py` 67/67 on Chromium (3 viewports) + existing 22/22 and 27/27 |

### 17.1 Issue 1 — amount mismatch and ambiguous verification (commit `a50ec25`)

* **Original problem.** `ZibalAdapter.verify_payment` raised `GatewayVerificationError("amount_mismatch")` *after* Zibal had confirmed the payment (result 100/201); the caller treated it like a plain failure, marked the attempt failed and kept nothing about the money.
* **Reused components.** `gateway_payment_service` (single verification flow), `PaymentAttempt`, `PaymentReconciliation` (+ its staff page/permissions `REFUND_VIEW/REFUND_MANAGE`), `staff.late_payment` event through the existing dispatcher/outbox, the lock order *order row → attempt*.
* **Changes.** `gateways/base.py` (`GatewayAmountMismatchError` carrying Rial evidence), `gateways/zibal.py` (Rial amount compared; a success **without a readable amount** is `GatewayResponseError("amount_unavailable")` — ambiguous, never success), `models.PaymentReconciliation` (`evidence_level` confirmed|suspected, `reported_amount`, kinds `amount_mismatch`/`verify_ambiguous`, resolutions `not_paid`/`auto_verified`; migration `orders.0019`, additive), `gateway_payment_service` (`_record_discrepancy`, `_open_reconciliation` upgrade path, `_close_suspected_record`, `PaymentAmountMismatch`), `order_expiry_service` (an open reconciliation blocks automatic expiry), `notifications` (recipients = owners **plus every active member holding `refund.manage`** via `EventDef.staff_permission`), reconciliation page (level badge, reported amount, new resolution options), `orders/views.py` (customer message).
* **Behaviour.** Confirmed mismatch → attempt `SUCCEEDED` (gateway-supported), one reconciliation (`confirmed`, expected vs reported amount, masked evidence), **no** `Transaction`, order/coupon/stock untouched, one staff e-mail. Ambiguous result (timeout/connection/invalid JSON/missing amount) **only when the callback claimed success** → `suspected` record, attempt not marked succeeded, nothing asserted as collected; a later clean verification applies the payment and auto-closes the record, a later confirmation on a canceled order upgrades the same record (second notification). Gateway rejections never create records.
* **Compatibility.** Existing rows default to `confirmed` (they were all gateway-verified). Old callers unaffected.
* **Tests.** 22 + 1 (financial-staff recipients) in `test_payment_discrepancy.py`: correct amount, toman-as-rial, under/over payment, canceled order, second attempt after paid, duplicate callbacks, ambiguous cases, upgrade/auto-close, expiry block, store isolation and permissions; PostgreSQL: parallel duplicate mismatch callbacks (one record, one notification) and mismatch-vs-cancel race (3 reruns stable).
* **External verification.** None (real Zibal unavailable). **Risk left:** Zibal's real field names/values are taken from the documented contract and third-party SDK descriptions; confirm with item 3's checklist.

### 17.2 Issue 2 — promotional consent (commit `c8b494d`)

* **Audit.** `Customer.accepts_promotional_sms/email` were added by `customers.0004` with `default=True`; no signup/checkout control existed, the account page was the only writer, no timestamp/source/audit trail existed, and the dispatcher checked the flag only when queuing. A stored `True` therefore proves nothing.
* **Policy (one implementation).** `customers/services/consent_service.py`: unknown = not granted; independent channels; `set_promotional_consent` records source + timestamp (+ `customer.consent_changed` audit event with store scope, no personal data); `grant_at_opt_in` for signup/checkout (never withdraws); `fresh_promotional_consent` for the send-time recheck. `profile_service.update_communication_preferences` and the dispatcher delegate to it.
* **Enforcement points.** queue time (`dispatcher._consented`) and **send time** (`notification_service._process` → `skipped/consent_withdrawn`, also for manual retries); transactional/security/staff/test sends exempt.
* **UI.** Signup and checkout show two **unticked** checkboxes; checkout can only grant; account settings grants/withdraws; dashboard customer page shows state + source.
* **Migration.** `customers.0006` (additive fields, defaults → False), `0007` backfill: legacy `True` → `False/legacy_unverified`, legacy `False` → `legacy_opt_out`; idempotent; reverse restores the pre-policy state only for untouched rows. **Effect: bulk promotional sends to existing customers stop until consent is re-recorded.** Operator tooling: `promotional_consent report|import` (dry-run default; import requires `--evidence` and `--store`).
* **Fixture fixes (intended, not weakened).** Test fixtures that relied on the old default now set consent explicitly.
* **Open decisions (not decided by tests).** Lawful basis/wording for Iran; per-store vs per-account consent (currently account-wide); evidence retention; need for an unsubscribe link/short code.

### 17.3 Issue 3 — Zibal (no code change beyond 17.1)

Not verified: payment-session lifetime, link expiry, callback retries, verify-after-expiry, `201` semantics in production, sandbox vs production differences. Official docs (`help.zibal.ir`) and the gateway are blocked by the environment's egress proxy; only third-party SDK pages were reachable (they confirm result `201` = processed before, Rial amounts, callback `trackId/success/status`, and say nothing about lifetime). Therefore `unpaid_online_order_ttl_minutes` remains **0**; an open reconciliation, in-flight attempts and confirmed payments already protect against cancelling money in flight, and late callbacks are always verified. The exact checklist for the person with Zibal access is PRODUCTION_CONFIGURATION §12.2.

### 17.4 Issue 4 — delivery verification

`verify_delivery_channels` (read-only audit; explicit `--confirm-test-recipient` for test sends): flags console/locmem/dummy e-mail backends and the SMS `console` backend as **NOT REAL** (they record `SENT` without delivering — a real production risk because `ShopSettings.sms_backend` defaults to `console`), missing SMTP/provider credentials, missing sender number, zero credits; never prints secrets. Existing contract tests cover Melipayamak/Kavenegar/SMSRasti request/response handling, credit gate, history mirror, dedupe, backoff/retry. **Accepted-by-provider ≠ delivered** (no delivery receipts are consumed) is documented. Real-provider delivery: **not verified** — no authorized credentials/network.

### 17.5 Issue 5 — background jobs

Audit: all jobs were already idempotent and per-item isolated except: exit codes were always 0, a failing order aborted the whole expiry batch, a failing campaign-run summary skipped delivery, no overlap guard, no health command. Changes: `core/job_lock.py` (PostgreSQL advisory lock, no-op elsewhere) on the four overlap-prone commands; non-zero exit after all work is done (campaign errors, any expiry/segment failure, whole-batch delivery failure); per-order error isolation in `expire_unpaid_orders`; `deliver_pending` reports `skipped`; `check_background_jobs` (OK/WARNING/CRITICAL from the data the jobs maintain); crontab template + runbook in PRODUCTION_CONFIGURATION §12.1. No new scheduler/queue/table. Not verified on a real scheduler.

### 17.6 Issue 6 — migration safety

Synthetic populated PostgreSQL 16 database at the **base-commit schema** (not production): 100,000 customers, 150,000 orders, 300,000 items, 89,736 transactions, 200,000 SMS logs, 29,970 coupon orders. Full forward migration (customers 0004–0007, cart 0008–0009, catalog 0039, core 0017–0018, engagement 0001–0002, orders 0011–0019, notifications 0002–0003): **≈16 s total**; slowest `customers.0007` 4.4 s, `orders.0016` 3.0 s, `notifications.0002` 2.1 s. Verified identical before/after: customer/order/item/transaction/SMS counts and the sums of order totals, item lines and transaction amounts; zero orphaned items/transactions; all 29,970 coupon orders got a redemption ledger row; consent backfill 100,000 → `legacy_unverified`; backfills idempotent on re-run; `makemigrations --check` clean; `check` clean. The earlier migrations of this branch (`notifications.0003`, `customers.0005`, `orders.0017/0018`, `core.0018`) were also verified forward/backward/forward on the staging database in earlier phases.
Reversibility: schema reverse exists and ran on the populated copy; **data** reverse is not safe — `customers.0005` reverse fails once a 21-character operator is stored (`value too long for type character varying(20)`; the failed reverse left 0006/0007 reversed, i.e. old unverifiable consent restored), so deployment is **roll-forward with a restorable backup**. Locking: `customers.0006/0007` and `orders.0016` touch every row (seconds at this size), `orders.0015` builds indexes without `CONCURRENTLY`; others additive. Procedure/checklists: PRODUCTION_CONFIGURATION §12.6. **Outstanding:** rehearsal on a sanitized production copy (none available).

### 17.7 Issue 7 — pricing consistency

Audit: `CartItem.unit_price` (and `gift_wrap_unit_price`) are add-time snapshots; `cart_totals` used them directly for both the checkout summary and order creation, so a later catalogue price change was neither shown nor re-validated (the order silently kept the stale price), while coupon/shipping/tax/stock were already evaluated live. Fix: `pricing.sync_cart_prices` (single re-pricing step, `resolve_effective_price` + gift-wrap price rules) used (a) by the checkout summary and (b) in `create_order_from_cart` under the product/variant row locks; the page posts the displayed grand total (`expected_total`, stored in the checkout session so the OTP path keeps it); a differing total raises `PriceChangedError` (everything rolled back, nothing created) → `PriceChanged` toast with the new amount; the customer presses pay again to confirm. Client totals are comparison-only; absent field = direct call (no UI). Persisted order total = attempt amount = gateway amount (Rial = Toman×10). Historical orders/refunds use order snapshots (tested). 19 tests: price up/down, discount %, variant, gift-wrap price/off, shipping, coupon expiry, stock, tampered totals, duplicate token, refunds, history, payment-attempt amount; PostgreSQL parallel checkout with one token → one order, stock decremented once.

### 17.8 Issue 8 — campaign performance (100,000 customers / 150,000 orders / 300,000 items)

Synthetic data only (`tools/bench/campaign_benchmark.py seed|run`, PostgreSQL 16 on the 4-core build container; subprocess per scenario).
**Bottleneck (measured with cProfile):** `effective_item_snapshot → build_item_snapshot` issued live catalogue queries *per order item* for legacy items and the item rows were loaded for every rule type — 13,700 queries / 25 s per 5,000 customers (≈ 280k queries, ≈ 8 min extrapolated for 100k).
**Change:** order lines are loaded lazily per 500-customer chunk (`OrderView.get_lines`, only when a rule reads lines) with prefetch-aware snapshots (`item_snapshot_service._related`): same data, a constant number of queries per chunk. **Exact semantics preserved:** the eligible-ID sets of all four scenarios are identical before/after on the same sample (verified by dumping and diffing), engagement suite unchanged and green, new tests pin the zero-item-query and constant-query properties and snapshot parity.

| Scenario (100k customers) | Eligible | Wall | Queries | Peak RSS |
|---|---|---|---|---|
| order_count ≥ 2 (aggregate) | 22,763 | 13.3 s | 956 | 92 MB |
| spend ≥ 3M (aggregate) | 27,469 | 12.9 s | 956 | 92 MB |
| nested AND/OR/NOT with line_match + canceled-history | 12,174 | 50.5 s | 1,194 | 115 MB |
| customer-only rule (everyone) | 77,630 | 8.2 s | 1,095 | 92 MB |
| preview (same rules) | same counts | 12.8 / 12.8 / 50.1 / 8.2 s | ≈ same | ≈ same |

Baseline (before) on a 5,000-customer sample: 25.2 s / 13,701 queries / 113 MB for each order-based rule (customer-only 1.1 s / 59 queries).
Budgets set for this hardware: eligibility/preview ≤ 60 s, ≤ 2,000 queries, ≤ 150 MB peak at 100k — **met**. Issuance throughput (real `execute_campaign`, personalised coupon + 1 e-mail + 1 SMS notification row + audit): 5,000 issuances in 65 s ≈ **77/s, 16 queries each** → ≈ 22 minutes for 100k in a single run — **documented scaling limit** (each issuance takes the campaign row lock, so parallel runs are serialised by design; runs are resumable and idempotent). Concurrency: PostgreSQL tests run two/three parallel executions → exactly one issuance, coupon and notification per customer, re-runs no-ops. Remaining limit: candidate ids are materialised as ints (≈ 1 MB per 100k) and `execute_campaign` holds the eligible id list in memory.

### 17.9 Issue 9 — browser / accessibility

New `tools/engagement_e2e/accessibility_e2e.py` (Playwright + axe-core WCAG 2.1 A/AA + best-practice): 3 viewports (1280×900, 768×1024 touch, 390×844 mobile touch) on Chromium: keyboard-only add/nest/AND-OR/NOT, focus never lost, tab order monotonic in DOM order, accessible names (unique, descriptive), roles, announced errors, aria-invalid, Persian digits/Jalali input, touch targets ≥ 24 px, no horizontal overflow/clipped controls, touch tap add/delete, no JS errors. First run found 24/67 failures — real defects, all fixed in the existing UI: no `role=group`/names on groups and conditions, duplicate delete/operator names, focus dropped to `<body>` after every add/remove/operator change (focus management added in `rule_builder.js`), delete-button contrast 3.13:1 (`.btn-danger` now `#b91c1c`/dark `#fca5a5`), search-hint contrast, unnamed burger button, nested-interactive search trigger, field errors not announced (`role=alert` in the shared `partials/field.html`). Result: **67/67 pass, axe 0 violations** on all viewports; existing suites 22/22 (rule builder) and 27/27 (workflow) still pass. **Firefox and WebKit: NOT RUN** (runtimes absent: `/opt/pw-browsers` contains only Chromium; downloading browsers is disabled) — run the same script where they are installed.

### 17.10 Architecture consistency review

Checked, no new duplicate found: one payment-success lifecycle (`apply_payment_success`); one gateway verification + reconciliation flow (`gateway_payment_service`/`PaymentReconciliation`, extended not replaced); one coupon rule set (`coupon_rules`) and ledger; one pricing path (`cart_totals` + `sync_cart_prices`, the latter using the same `resolve_effective_price`; `create_order_from_cart` has no caller bypassing it); one outbox/dispatcher (staff recipients extended by `EventDef.staff_permission`); one SMS provider/billing stack; one consent policy (`consent_service`; dispatcher and profile service delegate, the dashboard only displays); one rules engine (optimised, not forked); one job approach (cron + commands + advisory lock helper). Legitimate separations kept: synchronous legacy SMS vs outbox, cached segments vs live campaign evaluation, coupon definitions vs redemption ledger, payment attempts vs transactions. `SEGMENT_ORDER_DEFINITION` is still `legacy`.

### 17.11 Regression (HEAD after the staff-notification commit)

| Suite | DB | Result |
|---|---|---|
| dashboard | SQLite | 1496 run, OK |
| sms, portal, notifications, engagement, core, customers, cart, orders | SQLite | 1609 run, OK (21 skipped = PostgreSQL-only) |
| catalog, billing, blog, content, subscriptions | SQLite | 1526 run, OK (1 skipped) |
| stores + storefront_builder | SQLite | 3278 run, 31 failures + 3 errors, 4 skipped — **the same 34 tests fail on the untouched base export of `185166a`** (31 failures + 3 errors, set diff empty) |
| orders, cart, engagement, notifications, sms, customers, core, segment/order/settings dashboard views, all concurrency tests | PostgreSQL 16 | 1313 run, 0 failures, **1 error**: `AppearanceRenderingRegressionTests` (varchar(7) fixture), identical on the untouched base `185166a` |

Note: a first `--parallel 4` run aborted (`cannot pickle 'traceback' object`) and produced no result; it was discarded and the suites were rerun serially. stores/storefront_builder carry the pre-existing failures documented in §16.4 (storefront_builder, stores demo-media pair); exact counts of this rerun are in the table above. Browser: Chromium 22/22 + 27/27 + 67/67.

### 17.12 Remaining external access and decisions

Zibal documentation/sandbox access (item 3, blocks enabling any TTL); real SMS/e-mail provider credentials and a dedicated test recipient (item 4); a real scheduler/staging server for cron (item 5); a sanitized production DB copy for migration rehearsal and a backup/restore drill (item 6); Firefox + WebKit runtimes (item 9); owner decisions: consent legal basis/wording and per-store vs per-account scope, whether to allow gateway-refund automation, switching segments to the `valid` definition (§11.3), issuance-throughput target for very large campaigns.

## 18. SMS delivery integration, consent audit and remaining verifications (follow-up to §17, base `f9a55d4`)

### 18.1 Correction of §17.4
§17.4 audited per-store provider credentials; that was **wrong for the runtime**. The real model (and now the documented, tested one): each store uses exactly ONE method — **Phone** (SmsRasti Android gateway) or **Platform** (central provider, credentials only in `PlatformConfiguration`); legacy store values `console/melipayamak/kavenegar` all mean Platform. `verify_delivery_channels` was rewritten to report that truth (method, device/credit state per store; platform gateway once; no secrets).

### 18.2 Changes (fixed and automatically tested)
* **Routing/billing.** Platform credit is consumed only by Platform delivery and OTP; Phone sends are free of platform credit; no silent fallback in either direction; changing the method affects only later messages (queued ones are never re-sent); OTP/security and platform-owner authentication stay on the central gateway; legacy transactional SMS stays synchronous with no outbox SMS (no duplicates); campaign/transactional new-system events follow the same route via `send_raw_sms`.
* **Fake-success removed.** An unconfigured platform "console" gateway now fails loudly (credit refunded) unless explicitly allowed (tests/dev flag) — previously it recorded SENT and charged credit for a message that never left.
* **SmsRasti protocol** (`gateway_views.py`, migration `core.0019` additive): last-seen stamp, bounded re-claims (5) then FAILED, idempotent ack (SENT is final), failed ack → `SmsLog` FAILED, retry resets the counter and history follows the real outcome.
* **Admin status** (`delivery_status_service`, Settings → SMS, lazy so other settings sections keep their query ceiling): method, health, platform credit, device paired/online/last seen, queue, 24 h failures, actionable errors.
* **Branding.** Test guards that no store-customer SMS/e-mail default mentions RastiSi (only platform-owner OTP/test do).
* **Email workflow** verified through the real Django SMTP transport against a local sink: envelope, multipart, backoff, single re-send after recovery, invalid recipient, consent (not a real provider).
* **Files:** `apps/core/models.py`, `apps/sms/{gateway_views.py,services/sms_service.py,services/delivery_status_service.py}`, `apps/portal/services/owner_sms_service.py`, `apps/notifications/management/commands/verify_delivery_channels.py`, `apps/dashboard/{views.py,templates/.../settings_sms.html}`; tests `test_delivery_routing.py` (25), `test_gateway_concurrency.py` (PostgreSQL), `test_email_transport.py` (4), `test_verify_delivery_channels.py` (8). No new queue, dispatcher, provider stack, ledger or consent system.

### 18.3 Promotional messages — audit and single finding
Promotional events: `coupon.issued`, `coupon.expiring`, `reward.issued`, `occasion.*` (all others transactional/security/staff, unaffected). After `customers.0007` no pre-existing customer has recorded consent, so automated birthday/coupon/campaign **notifications** reach only customers who opted in since (the coupon is still issued and visible in the account). No code change; no new consent system. **Finding (the only open policy item):** the codebase has no provider-level suppression/unsubscribe mechanism — confirm with the SMS provider/regulator whether promotional SMS needs an opt-out line or a dedicated promotional line, and decide how existing customers' consent is re-established.

### 18.4 Verification status
| Item | Status |
|---|---|
| Phone/platform routing, credit, failures, method switching, transactional + campaign events, device poll/ack/duplicate/timeout/retry, e-mail via SMTP sink, background jobs, financial/notification regression | **Fixed and automatically tested** (below) |
| Backup/restore drill on the representative staging PostgreSQL copy: dump 16 MB → restore → 12 count/sum checks identical → `check` clean → newest migration applied with unchanged data | **Verified on staging data** (synthetic; not production) |
| Zibal session lifetime/callbacks | **Requires external access** — official docs/sandbox unreachable (re-attempted: only third-party SDK pages, nothing on lifetime); TTL stays 0 |
| Firefox/WebKit | **Requires external access** — Playwright CDN, Mozilla and PPA hosts blocked; Ubuntu `firefox` is a snap stub; cannot be installed here |
| Real SMS provider, real SmsRasti Android device, real mail account/domain, real scheduler, sanitized production DB | **Requires external access** — operator steps in PRODUCTION_CONFIGURATION §12.3 / §12.6 |

### 18.5 Test results (this phase)
SQLite: sms, notifications, portal, core, customers, engagement + dashboard settings views — **1097 run, OK (6 skipped)**. PostgreSQL 16: orders, cart, sms, notifications, engagement, customers, core + segment/order/settings dashboard views + all concurrency tests — **1331 run, 1 error**: `AppearanceRenderingRegressionTests` (varchar(7) fixture), identical on base `185166a`. One regression I introduced and fixed in-phase: the status block added 10 queries to every settings page (`SettingsPageQueryPerformanceTests` caught it) — now lazy. The stores/storefront_builder pre-existing failures (§17.11) are untouched by this phase.

## 19. Final completion — acceptance matrix, remaining checks and operator actions (base `72229a9`)

### 19.1 What this phase did (all automatically tested; nothing here is a real-provider/device/scheduler/production verification)
* **Promotional vs reward (no new consent system).** `test_promotional_delivery.py` (5): a customer with no recorded consent (the post-migration state of every pre-existing customer) still receives the birthday/campaign reward, sees it in `customer_coupons` and on the account page, and gets no message; channels are independent; skipped rows are final (no retroactive send after a later opt-in, `retry_notification` refuses them); an e-mail/SMS delivery failure never rolls back or hides the reward. Behaviour that blocks automated promotional notifications for pre-existing customers is exactly the consent gate (§17.2) — the minimal safe solution is to keep it: consent is re-recorded only by the customer (signup/checkout/account) or by the existing evidence-based `promotional_consent import`; no consent is invented and no provider rule is bypassed. **Single external dependency:** the SMS provider/regulator's promotional-message policy (opt-out line / promotional line type) — the codebase has no provider-level suppression/unsubscribe mechanism, so the promotional SMS path stays consent-gated and "unverified" until that policy is confirmed.
* **Android protocol.** `tools/smsrasti_simulator.py` speaks the exact gateway protocol; `test_gateway_live.py` (2) runs it over **real HTTP** against Django's live server (pairing, 401, empty, oldest-first claim, ack sent/failed, history sync, claim-without-ack stays `sending`, dashboard status). Already covered in §18: duplicate polling, timeout/bounded re-claim, idempotent ack, retry reset, parallel polling on PostgreSQL, credit rules, provider failure/refund, method switching, campaign + transactional routing. **Pending real:** the Android app on a physical phone.
* **Cron chain.** `test_job_chain.py` (4) runs the real commands as cron would: `run_engagement_jobs --no-deliver` (scheduled + birthday issuance, 3 issuances) → `process_notification_outbox` (3 e-mails + 3 platform-provider SMS, exactly once) → restart/overlap/re-run creates nothing new → crash mid-delivery (stale `SENDING`) recovered once → provider+SMTP outage is isolated, non-zero exit, `check_background_jobs` CRITICAL after 3 h, recovers to OK; `expire_unpaid_orders` (TTL 0), `expire_inventory_reservations`, `refresh_customer_segments` are safe no-ops. Advisory-lock overlap test on PostgreSQL (§17.5).
* **Deployment artifacts.** `deploy/cron/{rastisi.crontab,run_job.sh,validate_jobs.sh}`: env file, virtualenv, DB URL, `CRON_TZ`, per-job logs, exit-code preservation, alert command. Local test of the wrapper against the staging PostgreSQL found and fixed a real bug (`exit` inside the brace group terminated the script before the alert ran). `validate_jobs.sh` passes locally; the real server is not available.
* **Migrations / backup (staging PostgreSQL, synthetic 100k-customer data):** restore of the pre-`core.0019` dump into a fresh DB → `migrate` applied `core.0019` only → 12 count/sum checks identical → reverse `core.0019` and forward again OK → `makemigrations --check`, `check` clean → re-dump/re-restore identical; the older populated `stg_s0` database applied `core.0019`, `customers.0006/0007` cleanly. (`verify_coupon_consistency` reports `used_count_drift=5` on this database only because the synthetic seed never maintained `Coupon.used_count`; it is a seed artifact, not an application defect.)
* **Browser (Chromium):** rule builder E2E, workflow E2E, accessibility E2E — results below. **Firefox/WebKit: not run** (runtimes unavailable and downloads blocked; not retried). Exact instructions to run them elsewhere: PRODUCTION_CONFIGURATION §12.7.
* **Zibal:** official documentation and sandbox re-checked — still unreachable (egress proxy; only third-party SDK pages, none state session lifetime/callback retries). `unpaid_online_order_ttl_minutes` stays 0. Adapter/callback/concurrency/reconciliation tests were re-run in the regressions below.

### 19.2 Operator checklist for the remaining external checks (short)
1. **Zibal** (account access): confirm (a) `trackId`/payment-page lifetime, (b) callback retries (count/duration), (c) `verify` response after expiry and for a payment completed after expiry (`result`, `amount`, `status`), (d) meaning of `201` and of callback `status`/`success` in production vs sandbox, (e) that `verify` always returns `amount` in Rial. Only then set a TTL **longer than the confirmed lifetime + grace**, per store, and watch Finance → تطبیق پرداخت‌ها.
2. **Platform SMS provider:** configure credentials (Platform Admin), `verify_delivery_channels` → `REAL`; send one test with `--send-test-sms <your number> --store <slug> --confirm-test-recipient`; ask the provider whether promotional SMS needs an opt-out line / promotional line (the single policy dependency).
3. **Android phone:** pair the real SmsRasti app (token from Settings → SMS), confirm "device connected", send the test command, watch pending → sending → sent on the phone's ack; test airplane mode (messages stay queued, device shows offline). `python tools/smsrasti_simulator.py --base-url … --token … --once` reproduces the protocol without a phone.
4. **E-mail:** `verify_delivery_channels --send-test-email you@your-domain --confirm-test-recipient`; check inbox and SPF/DKIM/DMARC.
5. **Cron:** install `deploy/cron/rastisi.crontab`, run `deploy/cron/validate_jobs.sh`, then the manual steps (a)–(e) in §12.1.
6. **Production data:** only with an explicit sanitized copy: backup → restore → `migrate` → compare counts/sums (§12.6). Never run against live data without authorization.
7. **Firefox/WebKit:** run `tools/engagement_e2e/accessibility_e2e.py` on a machine with `playwright install firefox webkit`.

### 19.3 Final acceptance matrix against the original task (as recorded in §2–§3 of this report)
> The master task text is not stored in the repository or this session; the matrix is built from the requirements and gaps recorded in §2 (initial audit), §3 (checklist) and the owner's follow-up instructions. Optional/data-dependent items are labelled as such and do **not** make a core system incomplete.

| System | Mandatory requirement | Status | Evidence |
|---|---|---|---|
| 1. Discounts & campaigns | coupon types (percent/fixed/free-ship), owner-restricted + personal codes, max-discount cap, activation/expiry, usage + per-customer limits, rolling period limits, validity from delivery | **Done, tested** | `test_coupon_engine.py`, `test_coupon_concurrency.py` (PostgreSQL), `PeriodLimitTests`, `DeliveryValidityTests`, `verify_coupon_consistency` |
| | redemption ledger (reserve→redeem→release/refund), atomic capacity, no leak on cancel/failed/expired | **Done, tested** | ledger tests, M1/M2 tests, PostgreSQL races |
| | rule engine: AND/OR/nested/NOT, scopes, product-attribute history, store-scoped ids | **Done, tested** | `test_campaign_scenario.py`, `test_rule_data_scaling.py` |
| | campaign lifecycle: preview, activate, scheduled/event triggers, idempotent issuance, capacity/expiry, admin UI + visual rule builder | **Done, tested** (builder also in a real browser: Chromium 22/22 + a11y) | `test_campaign_scenario.py`, E2E |
| | mandatory Mehr–Aban 1405 scenario | **Done, tested** | `MandatoryCampaignTests` |
| | performance at 100k+ | **Done, measured** | §17.8 |
| | *Optional/extension:* free-product / gift-with-purchase reward | **Not implemented — optional**, needs a product decision; reward model is `coupon \| none` (free shipping is a coupon type). A second reward engine was deliberately not built. | §3 #19 |
| | *Optional/data-dependent:* latitude/longitude targeting | **Not implemented — no coordinate data exists in the project** (province/city targeting exists); collecting coordinates is a separate product/privacy decision | §3 #20 |
| 2. Birthdays, occasions, rewards | birth date (checkout + account, Jalali, never cleared by blank), Esfand-30 policy, once-per-Jalali-year cycle | **Done, tested** | `test_checkout_birth_date.py`, `test_occasions.py` |
| | occasion engine (birthday before/on/after, anniversary, milestones, reactivation, holiday, custom) + automatic scheduler | **Done, tested** (cron chain test) | `test_occasions.py`, `test_job_chain.py` |
| | reward issuance independent of notification; visible in account | **Done, tested** | `test_promotional_delivery.py` |
| | promotional consent respected | **Done, tested** — behaviour change (existing customers not messaged until opt-in) documented; one external policy dependency (§19.1) | §17.2, §19.1 |
| | *Optional:* birthday column in customer list/export | Not implemented (birthday visible on customer detail) | §3 #22 |
| 3. Gift wrapping | per-product eligibility/price, pricing scope, message, separate order total, invoice/admin/fulfilment display, discount rule, refund semantics | **Done, tested** | `test_gift_wrap_engine.py`, `test_gift_wrap_views.py`, scenarios C/D, §17.7 price re-confirmation |
| 4. Notifications | event registry, templates, dispatcher, outbox, dedupe, retry/backoff, per-channel toggles, consent, history UI, preview/test send, manual retry | **Done, tested** | `test_dispatcher.py`, `test_notification_service.py`, admin tests |
| | SMS (Phone/Platform routing, credit, device protocol, OTP separation, store branding) | **Done, tested locally** — real provider/phone unverified | §18, §19.1 |
| | e-mail pipeline | **Done, tested** against the real SMTP transport with a local sink — real provider unverified | `test_email_transport.py` |
| | *Optional/not applicable:* password-recovery / e-mail-verification / support-ticket events | Not implemented — those workflows do not exist in the project | §3 #21 |

Integration/no competing logic: one coupon rule set + ledger, one pricing path (`cart_totals` + `sync_cart_prices`), one payment-success lifecycle, one reconciliation flow, one outbox/dispatcher, one SMS stack with a single routing function, one consent policy, one rules engine, one cron approach (§17.10). Known leftover (not a competing logic): the legacy per-store columns `ShopSettings.melipayamak_username/password/kavenegar_api_key` are unused by any runtime path (kept for migration compatibility, documented in the model).

### 19.4 Environment deviation (unchanged)
The task asked for a local worktree `../commerce-engagement-worktree`. This work ran in an isolated, ephemeral cloud container whose only checkout already has the feature branch checked out (Git refuses a second worktree on the same branch); the container is the isolation. Git history was not altered to reproduce a directory name (§1).

### 19.5 Results
| Run | Result |
|---|---|
| Chromium E2E: rule builder / workflow / accessibility (axe, 3 viewports) | 22/22 · 27/27 · 67/67 passed (Firefox, WebKit: NOT RUN) |
| PostgreSQL 16 (orders, cart, sms, notifications, engagement, customers, core, order/settings/segment dashboard views, all concurrency tests incl. campaign, callback, polling, COD, expiry, checkout) | **1342 run, 1 error** — `AppearanceRenderingRegressionTests` (varchar(7) fixture), identical on base `185166a` |
| SQLite (sms, notifications, portal, core, customers, engagement, dashboard settings views) | **1108 run, OK, 6 skipped** |
| Earlier in this effort (§17.11/§18.5, unchanged code paths) | dashboard 1496 OK; sms…orders 1609 OK; catalog…subscriptions 1526 OK; stores + storefront_builder 3278 run with the same 34 failures as base `185166a` |

**Exact remaining code defects:** none known in the implemented scope. Known non-defects: pre-existing failures on base (above); unused legacy per-store provider columns kept for compatibility; `used_count_drift` on the synthetic staging seed only.
**Not verified against real services:** Zibal behaviour, platform SMS provider, SmsRasti Android app on a phone, real mail account/domain, a real cron scheduler, a production database, Firefox/WebKit.

---

## 20. Integration into `main` (merge of `origin/main` @ `41c2569` into the feature branch)

**Method.** Backup ref created first; `origin/main` merged (merge commit, both histories kept); conflicts resolved file by file; the same suites were run on the merged tree **and** on a `git archive origin/main` export (baseline = current main, not only the old ancestor `185166a`).

**Single price-confirmation mechanism.** The feature branch's earlier price re-confirmation (`PriceChangedError`, `sync_cart_prices`, §17.7/§17.10) was **superseded by main's CAT-002** (`reprice_cart_items`, `LivePriceChangedError`, `CartMembershipChangedError`, `PriceChangeReviewRequired`, `PRICE_CHANGED_MESSAGE`). Only the CAT-002 path remains; gift-wrap unit price is refreshed inside it, and `expected_total` is a comparison-only guard. Any mention of `sync_cart_prices` earlier in this report is historical.

**Fix found during integration.** Main's CAT-002 cart-lock query (`select_for_update()` + `select_related("variant")`) is rejected by PostgreSQL ("FOR UPDATE cannot be applied to the nullable side of an outer join"), so checkout failed on PostgreSQL on main itself (96 failures on the main baseline under PG). Fixed by `select_for_update(of=("self",))` in `order_service._lock_cart_items_and_resolve_final_prices` and `cart_service.reprice_cart_items`; Product/Variant rows are still locked separately.

**Results (merged vs current main).**

| Suite | Merged | Main baseline |
|---|---|---|
| SQLite orders/cart/customers | 798 OK (16 skipped) | 586, 3 pre-existing guest-cart errors |
| SQLite dashboard | 1506 OK | 1459 OK |
| SQLite sms/notifications/portal/core/engagement/billing/blog/content/subscriptions/catalog | 2608; 2 failures (portal host routing, unified login) identical to main; 1 error in `content` banner-delete test under heavy parallel load, **passes in isolation and in a full `apps.content` run** | 2395; the same 2 failures |
| SQLite stores + storefront_builder | 4519; 34 failures/errors, a subset of main's 35 | 4519; 35 |
| PostgreSQL 16 orders/cart/sms/notifications/engagement/customers/core + dashboard order/settings/segment | 1393; 1 error (`AppearanceRenderingRegressionTests`, pre-existing) | 952 (no engagement); 96 failures/errors from the FOR UPDATE defect |

No failure exists on the merged tree that is not also on main (apart from the load-only content flake above). `makemigrations --check`: no changes; `manage.py check`: OK; migrations conflict-free.

**R4 browser regression — NOT fully verified.** The 17-scenario runner `tools/storefront_builder_r4_qa/run.mjs` needs the full R4 QA fixture (hero slides, media, etc.). With the available ad-hoc fixture it fails 17/17 **identically on main and on the merged tree** (scenario 01, `waitSaved`/preview-dependent steps), so it gives no regression signal. What *was* verified in a real Chromium on both trees: the R4 editor route renders the Design Studio shell, `#r4PreviewFrame` is present and visible, the draft-saved state shows, with no page errors. Operators should run the full runner with the project's own R4 fixture before relying on it.

**Unchanged safety settings.** `SEGMENT_ORDER_DEFINITION=legacy`; unpaid-order TTL `0` (expiry disabled); COD never auto-marked paid; Phone/Platform SMS routing suites pass; no external service activated; no deploy, no production-DB migration.
