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
| Birthday / consent | `Customer.birth_date`, `apps/customers/services/profile_service.py` |
| Gift wrap | `apps/cart/services/gift_wrap_service.py`, `ShopSettings.gift_wrap_*`, `Product.gift_wrap_*`, `Order.gift_wrap_*` |
| Notifications | `apps/notifications/{events.py,models.py,services/*}` |
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
  redeemed on payment success, released on cancellation or payment failure, `refunded` after a full refund
  (capacity is **not** returned after a completed purchase). A paid retry after a failed payment re-takes capacity.
* **Refunds are net of the coupon share and include gift wrap** (prorated per returned quantity; last unit
  takes the rounding remainder).
* **Esfand 30** birthdays are celebrated on **Esfand 29** in non-leap Jalali years. The reward cycle key is the
  Jalali year of the occasion date → at most one reward per campaign per customer per Jalali year, even if the
  stored birth date is edited. An empty birth date input never clears a stored one.
* **Gift wrap** pricing scope (`ShopSettings.gift_wrap_pricing_scope`): `per_unit` (default) / `per_line` /
  `per_order` (one charge at the highest selected price). Not taxed; discounted only when the coupon has
  `applies_to_gift_wrap`. Variants inherit the parent product's setting. Stored separately on the order.
* **Notifications**: transactional/security events ignore promotional consent; promotional events require the
  customer's per-channel consent (`Customer.accepts_promotional_sms/email`, default true). Outbox rows are
  created in the business transaction; delivery is asynchronous with exponential backoff
  (1, 5, 30, 120, 360 min), `max_attempts` (5) then `dead`; manual retry allowed for `failed/dead` only.
  Legacy SMS events (welcome, order placed, payment, status) still send SMS through `apps.sms`; the new
  system adds email for them and everything for new events.

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
* "Free product / gift with purchase" reward types are not implemented (reward model is `coupon | none`;
  free shipping is a coupon type).
* Redemption limits *within a period* (e.g. once per 30 days) and "validity after delivery" (validity runs from
  issuance) are not implemented.
* No password-recovery / email-verification / support-ticket workflows exist in the project, so no notification
  events were created for them.
* Concurrency: capacity is enforced with an atomic conditional `UPDATE`; per-customer limits additionally rely on
  `SELECT … FOR UPDATE` (effective on PostgreSQL, a no-op on SQLite). No multi-threaded DB test was added.
* `store_customer_ids` materialises customer ids in memory; evaluation itself is chunked (500).
