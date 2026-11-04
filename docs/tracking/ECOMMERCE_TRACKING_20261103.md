# E-commerce tracking layer — implementation notes (2026-11-03)

Scope: migration-free. `RASTISI_STOREFRONT_TRACKING_ENABLED` stays **OFF** by default; with it off (or no provider connected, or on an admin/preview route) nothing below is built, printed or loaded.

## Pipeline
`apps/core/tracking_events.py` (server builders) → `request.rs_track_events` → `TRACKING_EVENTS` (context processor) → `<script id="rs-track-events" type="application/json">` in `tracking_head.html`
**or** `HX-Trigger: {"rsTrack": {...}}` (cart add) → `consent.js` (`cleanEvent` → consent check → provider routing).

| Event | Where | Emitted when | Identity |
|---|---|---|---|
| `view_item` / ViewContent | `catalog.views.product_detail` (shared by classic + builder shell) | a public, visible product page renders (404/other-store/preview: never) | random per render |
| `add_to_cart` / AddToCart | `cart.views.cart_add` | only after `add_item_to_cart` succeeded; quantity just added, `unit_price` of the cart item (server-resolved). Errors (bad qty, stock, 404) carry no event | random per success |
| `begin_checkout` / InitiateCheckout | `orders.views.checkout_step1` (full-page entry only) | non-empty cart of this store | `bc-<store>-<cart>-<k>`, `k` = number of this cart's cycles already closed by an order (`tracking_events.checkout_cycle`, below). `once` ⇒ the browser dedupes THAT identity (no time window decides anything) |
| `purchase` / Purchase | `orders.views.payment_result` (customer's OWN result page only) via `tracking_events.queue_purchase` | verified ONLINE gateway payment (PAID + `Transaction(gateway, ok)`) verified ≤ 30 min ago, tracking active, consent verified server-side (cookie + GPC, same rules as `consent.js`), and this request wins the unique print-claim | `purchase:<order.code>` (also `transaction_id` / Meta `eventID`) |

All money: Toman → ISO `IRR` through `apps.core.currency` (×10); any other source currency is refused. No PII keys; items are validated again in the browser (names, id charset, integer prices/quantities, `currency === 'IRR'`) and unknown keys are dropped.

## Consent / privacy behaviour (browser)
* No choice, refusal, withdrawal → event **dropped**, never queued, never replayed after a later choice (so the first page view of a first-time visitor is not reported).
* Dispatch needs the tag to be **loaded** and the CURRENT cookie to allow its category; Global Privacy Control now also overrides an older stored marketing grant (`readChoice`; fixes a pre-existing gap where a stored `m=1` loaded Meta under GPC).
* GTM present → `dataLayer.push({ecommerce:null}); push({event, event_id, ecommerce})`; GA4 direct (`gtag('event')`) only when GTM does not serve it; Meta → standard event + `{eventID}`. No Conversions API / Measurement Protocol.
* Double dispatch: in-memory id set (+ `localStorage` 24 h TTL for `once` events, best effort, not a durable claim); the events node is removed once consumed; htmx `rsTrack` handled by one document listener.
* Consent Mode v2 defaults untouched.

## begin_checkout identity (corrected 2026-11-04)
Lifecycle facts (verified in code): `Cart.checkout_token` is the payment **idempotency key** — created lazily in `finalize_order`, kept after the order (so a retry replays the order) and cleared when the next cycle's first item is added (`cart_service.start_new_checkout_cycle_if_empty`). It does not exist yet while a checkout is merely *open*, and creating it on the GET would be a write — so it cannot be the analytics identity, and nothing about it was changed.
The platform already records which cart an order came from: `create_order_from_cart` reserves/consumes stock per line with `cart=cart, source="order"` and `consume_inventory_reservation` stamps `order` on the reservation in the same transaction. **`k` = number of distinct orders reached through those reservations for this (store, cart)** — a pure read: tenant-scoped, same for guests and logged-in customers, identical on every render / HTMX partial / reload / second tab of an open checkout, bumped by exactly the order that closes the cycle, unaffected by orders made elsewhere.
The first implementation used *the customer's order count in the store*: it was `0` forever for unauthenticated carts (a reused cart row collided with the previous cycle) and it moved whenever any other order of the customer appeared (duplicate event inside one checkout). Both are reproduced in `test_tracking_checkout_cycle.LegacyIdentityDefectTests`. The old report's *HTTP* guest scenario does not collide in practice (a guest who orders is logged in, so the count grew); the unauthenticated-cart collision is reachable only at service level — the second defect is reachable over HTTP.
Remaining limitations (not hidden): (1) logging in mid-checkout merges the guest cart into the customer cart (different row) → one extra `begin_checkout` for that visitor; (2) emptying the cart and refilling it before ordering keeps the same cycle (no new intent is inferable without a write); (3) the browser's 24 h key is only expiry of old keys — the key is the identity, so a new cycle is never suppressed, but a >24 h-old open checkout reloaded after expiry can re-fire once.

## Purchase — IMPLEMENTED for verified online payments (browser channel); COD / card-transfer / server-side channels remain out of scope
Implemented 2026-11-04 together with the payment-engine integration (migration `core.0024_tracking_emission`). The concerns are separated:

| Concern | Decision | Persistence |
|---|---|---|
| A. Authoritative payment transition | `apply_payment_success` (conditional UPDATE, once). **Untouched** | existing |
| B. Immutable purchase identity | `event_id = "purchase:<order.code>"` (also GA4 `transaction_id`, Meta `eventID`) — deterministic | no |
| C. Eligibility | PAID **and** `Transaction(method=gateway, status=ok)` created ≤ `RASTISI_PURCHASE_WINDOW_MINUTES` (30) ago **and** the request is the customer's own `payment_result` page; a late reconciliation / admin confirmation days later never prints a stale Purchase | no |
| D. Consent | evaluated **at delivery** from the first-party `rs_consent` cookie (current policy version) + `Sec-GPC`, with the SAME `needs` rules as `consent.js` (`consent.would_dispatch`); the browser re-checks. Never stored | no |
| E. Delivery channel | **browser** only (`consent.js` → GTM dataLayer / direct GA4 / Meta Pixel). No Measurement Protocol / CAPI | — |
| F. Dispatch claim / dedup | `TrackingEmission` unique `(order, event_name, channel)`: the ONE request that creates the row prints the event. A request without consent creates **no** row | **1 table** |
| G. Failure / retry | none (no browser acknowledgement exists) — see guarantees | — |

### Guarantees (honest)
* **Authoritative event:** exactly once (A).
* **Server print:** **at-most-once** per order (unique claim row; concurrent renders: one wins).
* **Attempt:** best-effort, **not** at-least-once: a claimed print whose page never ran JS, was ad-blocked, or lost consent is **lost** — we never re-print, because without an acknowledgement a retry cannot be told apart from a duplicate. (A retry/lease design would trade this loss for duplicates; rejected for P1.)
* **Browser:** the `rs_trk_<id>` key adds best-effort once-per-browser, but is not relied on.
* **Provider:** GA4 de-duplicates purchases by `transaction_id`, Meta by `eventID` (documented provider behaviour — **not verified here**, no live calls). RastiSi never claims global exactly-once, never learns whether GA4/Meta/GTM accepted the event.
* Not an acknowledgement of: consent given (only verified at render), browser receipt, tag-manager dispatch, provider acceptance.

### Why a table (rejected fallbacks)
Printing on every eligible render, relying on `localStorage` + provider dedupe, re-fires on every refresh, history revisit, second device and cleared storage; `AuditLog` is append-only evidence with no unique constraint (not a race-safe marker); an ack endpoint is forgeable and cannot prove provider delivery. Rejected: they fail the dedupe/consent guarantees.

### One table is sufficient for P1 — a delivery table is not justified yet
Evidence: one channel (browser) whose per-provider outcome is unobservable, so per-provider delivery rows would store nothing verifiable. A separate business-event vs delivery split becomes necessary only with a server channel (real acks, retries, crash recovery) — then add `TrackingDelivery` additively (separate approval).

### Schema (created: `core.0024_tracking_emission`; additive, reversible)
```python
class TrackingEmission(models.Model):              # apps/core
    store = models.ForeignKey("stores.Store", on_delete=models.CASCADE, related_name="tracking_emissions")
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="tracking_emissions")
    event_name = models.CharField(max_length=32)    # "purchase"
    event_id = models.CharField(max_length=120)     # "purchase:<order.code>"
    channel = models.CharField(max_length=16, default="browser")
    claimed_at = models.DateTimeField(auto_now_add=True)   # = the server printed it to a consenting browser. NOT a delivery acknowledgement.
    class Meta:
        constraints = [models.UniqueConstraint(fields=["order", "event_name", "channel"], name="uniq_tracking_emission")]
        indexes = [models.Index(fields=["store", "claimed_at"], name="idx_trackemission_store_time")]
```
* **Transaction boundary:** the claim is **not** inside `apply_payment_success` (financial path untouched). It is created in the `payment_result` GET after eligibility + consent are verified: `TrackingEmission.objects.get_or_create(order=…, event_name="purchase", channel="browser", defaults={store, event_id})` — `created=True` ⇒ this request prints the event; `IntegrityError`/`created=False` ⇒ print nothing. A request that fails eligibility/consent creates **no** row (a non-consenting render never burns the event).
* **Concurrency:** the unique constraint serialises racing renders (PostgreSQL test: N threads → exactly one row/print). **Crash:** crash after commit, before the response ⇒ event lost (at-most-once); crash before commit ⇒ nothing claimed.
* **Multi-store:** `store` must equal `order.store` (asserted in the service; all reads filter by `store`); the page already enforces own-order + host-store (`_get_own_order`).
* **Retention:** rows are tiny; `CASCADE` with the order; optional prune after 400 days. **No PII, no consent record, no IP** stored.
* **COD / card-to-card (still NOT reported):** they become PAID in the admin panel with no customer browser. No visitor event is simulated. A future *server-side* channel would need (1) an approved provider contract, (2) a **consent snapshot** captured while the browser is present — the `rs_consent` cookie value (`v`,`a`,`m`), `Sec-GPC`, timestamp — stored at order placement (`checkout_pay` POST) and default-deny when absent, (3) a `TrackingDelivery` table (state/attempts/next_attempt/last_error, unique per emission+channel) with a worker and retry, (4) hashed-identifier policy and a legal review of post-order consent withdrawal. All out of scope and unauthorized.

## Tests
`apps/core/tests/test_tracking_events.py` (builders, wiring, isolation, no purchase, JS contract), `apps/core/tests/test_tracking_checkout_cycle.py` (checkout identity, legacy defects), `apps/core/tests/test_preview_tracking_isolation.py`, browser: `node apps/core/tests/browser/tracking_dispatch_qa.js` (Chromium, mocked providers, 23 checks).
