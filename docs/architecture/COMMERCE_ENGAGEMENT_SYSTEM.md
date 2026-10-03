# Commerce & Engagement System (campaigns, occasions, gift wrap, notifications)

Permanent technical documentation for the four integrated systems added on
`feature/commerce-engagement-system`. (The temporary progress report lives in
`docs/implementation-audit/commerce-engagement-report.md`.)

## 1. Map of the code

| Concern | Where |
|---|---|
| Coupon model + rules (owner, caps, limits, restrictions) | `apps/cart/models.py::Coupon`, `apps/cart/services/coupon_rules.py` |
| Totals (items, discount, gift wrap, shipping, tax) | `apps/cart/services/pricing.py::cart_totals` |
| Redemption ledger (reserve → redeem → release/refund) | `apps/orders/models.py::CouponRedemption`, `apps/orders/services/coupon_redemption_service.py` |
| Historical item snapshot (brand/category/colour/size/attrs) | `OrderItem.attributes_snapshot`, `apps/orders/services/item_snapshot_service.py` |
| Rule engine (AND/OR/nested/NOT, scopes) | `apps/engagement/services/rules.py`, data loading `rule_data.py` |
| Campaigns/occasions | `apps/engagement/{models.py,services/campaign_service.py,services/occasions.py}` |
| Scheduler / event hook | `manage.py run_engagement_jobs`, `apps/engagement/hooks.py` |
| Jalali utilities | `apps/core/jalali_utils.py` |
| Birthday | `Customer.birth_date`, `apps/customers/services/profile_service.py` |
| Promotional consent (single policy) | `apps/customers/services/consent_service.py`, `Customer.accepts_promotional_*` + `promo_*_consent_{source,changed_at}`, `promotional_consent` command |
| Gift wrap | `apps/cart/services/gift_wrap_service.py`, `ShopSettings.gift_wrap_*`, `Product.gift_wrap_*`, `Order.gift_wrap_*` |
| Notifications | `apps/notifications/{events.py,models.py,services/*}` (events registry → dispatcher → `NotificationOutbox` → `deliver_pending`) |
| Payment lifecycle (single "payment confirmed" orchestration) | `apps/orders/services/lifecycle.py::apply_payment_success` |
| Gateway verification + reconciliation | `apps/orders/gateways/*`, `apps/orders/services/gateway_payment_service.py`, `PaymentReconciliation`, dashboard Finance → تطبیق پرداخت‌ها |
| Cash on delivery confirmation (manual, permissioned) | `apps/orders/services/cod_payment_service.py`, permission `order.confirm_cod_payment`, `Transaction.{method,confirmed_by,confirmed_at}` |
| Unpaid online order expiry (default off) | `apps/orders/services/order_expiry_service.py`, `manage.py expire_unpaid_orders`, `ShopSettings.unpaid_online_order_*` |
| Price re-confirmation at checkout | `apps/cart/services/pricing.py::sync_cart_prices`, `order_service.PriceChangedError`, `checkout_service.PriceChanged` |
| Shared order definitions (valid order, active refund) | `apps/orders/services/order_definitions.py`, `Refund.INACTIVE_STATUSES` |
| Job reliability / health | `apps/core/job_lock.py`, `manage.py check_background_jobs`, `verify_delivery_channels` |
| Admin UI | `apps/dashboard/engagement_views.py`, `engagement_forms.py`, `static/js/rule_builder.js` |

## 2. Policies (explicit decisions)

* **Valid order** for campaigns: store-scoped, not `canceled`, `payment_status` in the campaign's
  allowed list (default `paid`). Amount basis defaults to *net* (grand total minus successful refunds).
* **Period**: Jalali month ranges include both whole months; evaluated as half-open
  `[00:00 first day, 00:00 day after last day)` in `settings.TIME_ZONE` (no per-store timezone field exists).
* **Rule scope**: `aggregate` (default) – each order-level condition is satisfied by *some* order, amounts are
  summed; `same_order` – one single order must satisfy every order-level condition.
  Customer-level conditions (birthday, lifetime spend…) are independent of scope. `OR` groups are evaluated
  as OR; nesting and `negate` are supported (this is how "excluded brands/categories" are expressed).
* **Product conditions use the order-time snapshot**, never the current catalogue; legacy rows without a
  snapshot fall back to the live catalogue (flagged `source: "live"`).
* **Coupon redemption**: reserved at order creation (atomic compare-and-set on `used_count`),
  redeemed on payment success, released on cancellation (including automatic expiry) or payment failure, `refunded`
  after a full refund (capacity is **not** returned after a completed purchase). A paid retry after a failed payment
  re-takes capacity. Validity rules live in one place (`coupon_rules.validity_failure/ownership_failure/capacity_failure/
  availability_failure/display_state`); `pricing.coupon_is_applicable` is a thin wrapper. Per-customer limits can be
  rolling (`per_customer_period_days`); validity can be anchored to first successful delivery (`validity_from_delivery`,
  `delivery_anchored_at`). `manage.py verify_coupon_consistency` is the read-only ledger audit.
* **Refunds are net of the coupon share and include gift wrap** (prorated per returned quantity; last unit
  takes the rounding remainder).
* **Esfand 30** birthdays are celebrated on **Esfand 29** in non-leap Jalali years. The reward cycle key is the
  Jalali year of the occasion date → at most one reward per campaign per customer per Jalali year, even if the
  stored birth date is edited. An empty birth date input never clears a stored one.
* **Gift wrap** pricing scope (`ShopSettings.gift_wrap_pricing_scope`): `per_unit` (default) / `per_line` /
  `per_order` (one charge at the highest selected price). Not taxed; discounted only when the coupon has
  `applies_to_gift_wrap`. Variants inherit the parent product's setting. Stored separately on the order.
* **Promotional consent**: one policy (`consent_service`). Unknown = not granted (default `False`); SMS and e-mail are
  independent; each change records source + time and an audit event when a store context exists; consent is checked when the
  notification is queued **and again at send time** (`consent_withdrawn`); transactional/security events never depend on it.
  Existing customers were backfilled conservatively (`customers.0007`): the old unverifiable default `True` became
  `False/legacy_unverified`. Signup/checkout checkboxes are never pre-ticked; checkout only grants.
* **Notifications**: outbox rows are created in the business transaction; delivery is asynchronous with exponential backoff
  (1, 5, 30, 120, 360 min), `max_attempts` (5) then `dead`; manual retry allowed for `failed/dead` only. Legacy
  transactional SMS (welcome, order placed, payment, status, OTP) is **still synchronous** through `apps.sms`
  (history is mirrored into `NotificationOutbox` rows that the worker never sends); the new system adds e-mail for them and
  everything for new events. SMS templates: one global `SmsTemplate` set with a strict allow-listed renderer.
* **SMS delivery method (one per store)**: *Phone* (SmsRasti Android gateway, token-paired, poll/ack queue `SmsOutboxItem`, no platform credit) or *Platform* (central provider from `PlatformConfiguration`, platform credit). Every eligible event follows the store's method automatically via `sms_service.get_backend`; no per-event provider choice, no per-store provider credentials, no silent switch between methods; OTP/security and platform-owner authentication always use the central gateway; customer-facing text carries the store's name, never platform branding. Device protocol: pairing token, last-seen stamp, bounded re-claim (5), idempotent ack, `SmsLog` synced with the device outcome. Admin/ops status: `apps/sms/services/delivery_status_service.py` (dashboard + `verify_delivery_channels`).
* **Payments**: every "payment confirmed" goes through `lifecycle.apply_payment_success` (online callback, simulated
  payment, COD confirmation). Lock order everywhere: **order row first, then attempt**. A callback is always verified with the
  gateway (also for failed/canceled/expired attempts — money may have been taken late). Verified money that cannot be applied
  (canceled/already paid/not payable/processing error), a **confirmed amount mismatch**, or an **ambiguous** verification where the
  customer returned claiming success becomes one `PaymentReconciliation` per attempt (`evidence_level` confirmed|suspected,
  reported amount kept) with a staff e-mail; the order is never reopened, marked paid, or given its coupon/stock back
  automatically, and no second `Transaction` is created. Resolution is explicit and audited. An open reconciliation blocks
  automatic expiry. Gateway amounts are Rial (Toman × 10) and a success without a readable amount is ambiguous, not success.
* **COD** is never automatically paid. Owner/Administrator/Order Manager confirm collection manually (exact full amount,
  method, optional receipt reference); order status is preserved; one e-mail receipt; corrections go through the refund workflow.
* **Order expiry** (`unpaid_online_order_ttl_minutes`, default **0 = disabled**, grace 30 min, SMS off): cancels only pending, unpaid,
  definitely-online orders through the normal cancellation path (stock + coupon released). Skips confirmed payments, in-flight
  attempts and open reconciliations; re-checks under the order lock; never touches COD. Not to be enabled until Zibal's session
  lifetime/callback behaviour is verified (see PRODUCTION_CONFIGURATION §12.2).
* **Checkout amount**: the summary re-prices from the authoritative catalogue (`sync_cart_prices`), posts the displayed total, and order
  creation (under product/variant row locks) refuses to create the order when the total differs, so the customer must
  re-confirm the new amount. Payment attempts take `order.grand_total`; the gateway adapter converts to Rial.
* **Segments**: `SEGMENT_ORDER_DEFINITION` stays `legacy`; the shared definitions (`order_definitions`) also provide the `valid`
  definition behind an explicit switch (needs owner approval — audiences change).

## 3. Operations

```
# cron (hourly or daily): scheduled + occasion campaigns, expiry reminders, deliver queued notifications
python manage.py run_engagement_jobs
# alternative: queue only, deliver separately every minute
python manage.py run_engagement_jobs --no-deliver
python manage.py process_notification_outbox
```
All jobs are idempotent (unique `CampaignIssuance(campaign, customer, cycle_key)` + notification `dedupe_key`).
Event campaigns run automatically after a successful payment (`transaction.on_commit`).
The full schedule (frequencies, dependencies, exit codes, advisory locks, health check) is in
`docs/docs/product/deployment/PRODUCTION_CONFIGURATION.md` §12.1 — the single operations document.

## 4. Rule tree schema

```json
{"type":"group","op":"and","negate":false,"children":[
  {"type":"group","op":"or","children":[
    {"type":"line_match","category_ids":[12],"colors":["زیتونی"]},
    {"type":"line_match","category_ids":[15],"brand_ids":[3]}]},
  {"type":"order_total","op":"gt","value":"10000000"},
  {"type":"shipping_city","values":["شیراز"]}]}
```
Leaf catalogue: `rules.LEAVES` (`rules.leaf_catalog()`); UI field metadata: `ui_schema.FIELDS`.
All referenced ids are verified against the campaign's store.

## 5. Known limitations / not implemented

* No latitude/longitude data → "geographic location" is province/city only.
* "Free product / gift with purchase" reward types are not implemented (reward model is `coupon | none`; free shipping is a
  coupon type).
* No password-recovery / email-verification / support-ticket workflows exist in the project, so no notification events were created
  for them.
* Concurrency is covered by real multi-threaded PostgreSQL tests (coupon capacity/limits, payment callback vs cancel/expiry,
  duplicate callbacks, parallel COD confirmation, parallel checkout with one token). SQLite runs skip them.
* Legacy transactional SMS is synchronous (async legacy SMS / "S3" deliberately not implemented).
* Gateway refunds are not implemented; late-payment and mismatch resolution is manual (`refunded_outside` etc.).
* Consent is per customer account (shared across stores) — a product/legal decision still to be confirmed.
* Zibal session lifetime / callback retry behaviour are unverified; expiry stays disabled until they are.
* Campaign engine scaling: see the benchmark section of the progress report (`tools/bench/campaign_benchmark.py`); candidate ids are
  still materialised in memory (ints only) while evaluation is chunked (500).
* Browser coverage: Chromium only in the current environment (Firefox/WebKit cannot be installed here); runs pending where available (`tools/engagement_e2e/`).
* Phone-method delivery means "queued for the device"; real delivery depends on the owner's phone being online and is confirmed only by the device acknowledgement. Real-provider/real-device verification is an operator step (PRODUCTION_CONFIGURATION §12.3).
