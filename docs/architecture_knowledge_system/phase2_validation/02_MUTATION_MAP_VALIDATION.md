# 02 — Mutation Map Validation

Validates the writer classifications in Phase 1 `06_MUTATION_MAP.md`, focusing on the two
entities rated **HIGH** (mandatory) plus spot-verification of other high-interest entities.
All evidence is from the frozen snapshot `5883a140`.

Classification: CONFIRMED / CONFIRMED_WITH_CORRECTION / DOWNGRADED / UPGRADED / NOT_PROVEN / DISPROVED.

---

## HIGH-rated entities (mandatory direct validation)

### E1 — `Order.payment_status` — **CONFIRMED** (HIGH)
Exhaustive writer set (grep, non-read): `payment_service.simulate_payment` (86–98),
`gateway_payment_service.process_callback_and_verify` (313–316),
`refund_service` (234). Exactly the 3 writers Phase 1 claimed; the canonical (gateway) path is
lock+conditional, the other two are direct saves; no transition table. See doc 01 H1 / doc 04.
Writer classifications in Phase 1 doc 06 §2 (CANONICAL/SECONDARY×2) hold.

### E2 — `content.*` (pages/menus/footer/media) — **CONFIRMED** (HIGH)
No content write service exists; `dashboard/views.py` performs all CRUD (83 save/delete/clean
sites). CROSS_DOMAIN_WRITE classification confirmed. See doc 01 H2.

---

## Other entities spot-validated

### `Order.status` — **CONFIRMED** (LOW)
Single guarded writer `order_service.change_order_status` with `ALLOWED_TRANSITIONS` (line 45)
enforced at line 550. Callers (`simulate_payment`, `gateway_payment_service`, dashboard
`order_detail`) all funnel here. No competing direct writer found.

### `Transaction` (legacy) — **CONFIRMED** (MEDIUM)
Two create paths verified: `simulate_payment` and the gateway SUCCESS block ("for backwards
compatibility with existing dashboard"). Both create `Transaction`, so a gateway-paid order has
both a `PaymentAttempt` and a `Transaction`.

### `StoreSubscription.status` — **CONFIRMED** (MEDIUM, funneled)
Phase 1 claim that billing drives the state machine only through `subscription_service`
(never direct) is consistent with the code structure observed in Phase 1 (billing
confirmation/dunning/renewal/cancellation call subscription_service transitions). No direct
`subscription.status =` writer outside `subscription_service` was surfaced. Classification holds.
(Deep per-line re-read of every billing service body was not repeated here — Phase 1 read those
bodies; Phase 2 confirms the boundary claim is consistent and finds no contradicting direct write.)

### `ShopSettings` — **CONFIRMED** (MEDIUM)
Writers: `core.ShopSettings.provision_for` (create), dashboard settings views (direct save),
`sms_service.regenerate_smsrasti_device_token`. The sms_service ShopSettings read is limited to
`sms_backend == SMSRASTI` (verified), consistent with the "write authority spread" finding.

### `StoreMembership` — **CONFIRMED_WITH_CORRECTION** (MEDIUM → nuance)
Writers: `membership_service` (add/change/revoke/reactivate/**transfer_ownership**),
`ownership_transfer_service.accept`, provisioning (initial OWNER). Correction: Phase 1 hedged
that `membership_service.transfer_ownership` might be dead; Phase 2 confirms it is **live**
(dashboard route `staff/<pk>/transfer-ownership/`). So there are **two live** owner-transfer
writers of memberships. See doc 03 (ownership) and doc 06 (correction).

---

## Summary

| Entity | Phase 1 risk | Phase 2 classification | Change |
|---|---|---|---|
| Order.payment_status | HIGH | CONFIRMED | none |
| content.* | HIGH | CONFIRMED | none |
| Order.status | LOW | CONFIRMED | none |
| Transaction (legacy) | MEDIUM | CONFIRMED | none |
| StoreSubscription.status | MEDIUM | CONFIRMED | none |
| ShopSettings | MEDIUM | CONFIRMED | none |
| StoreMembership | MEDIUM | CONFIRMED_WITH_CORRECTION | transfer_ownership proven live (2 live transfer paths) |

No mutation-map writer classification was DISPROVED. The only correction tightens a hedge into a
confirmed fact (two live ownership-transfer paths), which strengthens the associated ambiguity.
