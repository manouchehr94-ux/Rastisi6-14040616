# 01 — HIGH-Risk Findings Validation

Direct re-verification of the three Phase 1 HIGH findings against the frozen snapshot
`5883a140`. Classification vocabulary: CONFIRMED / CONFIRMED_WITH_CORRECTION / DOWNGRADED /
UPGRADED / NOT_PROVEN / DISPROVED.

---

## H1 — Duplicate order-payment paths + unguarded `Order.payment_status`

**Classification: CONFIRMED.**

### Writers of `Order.payment_status` (exhaustive, non-read)
Direct grep across `apps/` (excluding read-only filter/aggregate uses) yields exactly three
mutation sites:

| Writer | Evidence | Mechanism |
|---|---|---|
| `orders/services/payment_service.py::simulate_payment` | lines 86–98 | `order.payment_status = PAID/FAILED; order.save(update_fields=["payment_status","updated_at"])` — plain assignment |
| `orders/services/gateway_payment_service.py::process_callback_and_verify` | lines 313–316 | conditional `Order.objects.filter(pk=..., payment_status=PENDING).update(payment_status=PAID)` inside `transaction.atomic()` after `select_for_update()` re-lock of the attempt |
| `orders/services/refund_service.py` | line 234 | `order.payment_status = REFUNDED; order.save(update_fields=[...])` — plain assignment |

### Duplicate implementation (VERIFIED)
- Legacy: `simulate_payment` creates a `Transaction` row and marks the order paid.
- New: `process_callback_and_verify` marks the order paid **and also** creates a legacy
  `Transaction` "for backwards compatibility with existing dashboard" (verified in the SUCCESS
  block, ~lines 330–340). So a gateway-paid order gets **both** a `PaymentAttempt` and a
  `Transaction`.

### No guarded state machine for `payment_status` (VERIFIED)
- `order_service.ALLOWED_TRANSITIONS` (line 45) enumerates only `Order.Status` values
  (PENDING→{PROCESSING,CANCELED}, …) and is enforced at line 550 inside `change_order_status`,
  which mutates `Order.status` — **not** `payment_status`.
- There is **no** transition table, `select_for_update`, or legality guard governing
  `payment_status` transitions in `simulate_payment` or `refund_service`. Only the gateway path
  is lock-protected (via a conditional `UPDATE ... WHERE payment_status=PENDING`).

### Risk rationale (kept at HIGH, not CRITICAL)
The most dangerous writer (`simulate_payment`, no Order lock) is production-gated:
`settings.PAYMENTS_SIMULATION_ENABLED` defaults to `DEBUG`, and the simulation callback route
`checkout/payment-callback/<status>` raises `Http404` when the flag is off. HIGH (duplicate
mutation path + unguarded money field) is the correct severity; elevate to CRITICAL only if the
simulation path is shown reachable in production. **Unchanged from Phase 1.**

---

## H2 — `content` mutation authority (no write service; dashboard views mutate directly)

**Classification: CONFIRMED.**

### `content` has no write service (VERIFIED)
- `apps/content/` has **no `services/` package** — only a single `services.py`.
- `services.py` defines: `resolve_destination_url`, `resolve_destination_context`,
  `resolve_destination_setting`, `resolve_background_media_url`, media-cleanup helpers
  (`cleanup_reusable_media_file`, `delete_media_asset_if_unreferenced` — MED-001 no-ops),
  and `subscribe_to_newsletter`. **No create/update/delete service** for `ContentPage`, `Menu`,
  `MenuItem`, `FooterSettings`, `HeroSlide`, `PromotionalBanner`, `SocialLink`,
  `FooterTrustBadge`, `FooterPaymentLogo`, `StoryRailItem`.

### Dashboard views are the de-facto writer (VERIFIED)
- `apps/dashboard/views.py` contains **83** `.save()/.delete()/.full_clean()` call sites
  (grep count), including all content-model CRUD (Phase 1 doc 06 §12 cited views.py:4744–5633).
- The content models exist (13 model classes in `content/models.py`) but the dashboard view
  layer is their only write path. Cross-domain, no service/transaction boundary.

**Classification CONFIRMED.** Severity HIGH unchanged.

---

## H3 — Three storefront editor/template generations coexist

**Classification: CONFIRMED.**

### R4 is the default canonical editor (VERIFIED)
- `StorefrontLayout.r4_editor_enabled` (`storefront_builder/models.py:211`) has `default=True`;
  help text: "R4 is now the default canonical merchant editor (dashboard nav routes here); this
  flag exists only so an individual Store can be pinned back to the legacy editor if a
  regression is found."

### Legacy (R3) mutation routes fail closed when R4 active (VERIFIED)
- `storefront_builder/views.py::_require_legacy_editor_active` (line 65) raises `Http404` when
  `layout.r4_editor_enabled` is True. Applied to a named list of legacy mutation routes
  (decorators at lines 479, 505, 572, 591, 621, 643, 720, …). Shared capabilities (Ready
  Template gallery/apply, preview, history, media) are deliberately not caught.

### All three generations physically present (VERIFIED)
- Legacy/R3: `views.py`. R4: `r4_views.py` (+ `services/r4_mutation_service.py`). A8:
  `a8_ready_templates.py` on `layout_preset_registry.py`.
- Retired registries `family_registry.py` / `preset_registry.py` **confirmed absent** (files do
  not exist); only doc/test references remain.

**Classification CONFIRMED.** Severity HIGH unchanged.

---

## POTENTIALLY_DEAD items resolved by Phase 2 caller tracing

| Item | Phase 1 status | Phase 2 evidence | Phase 2 classification |
|---|---|---|---|
| **D1** blog storefront wiring | POTENTIALLY_DEAD | `blog` appears only as the boilerplate comment in `shop_core/urls.py`; no `include('blog.urls')`, no urls.py, stub views | **CONFIRMED** (storefront wiring dead; model admin-only) |
| **D3** `membership_service.transfer_ownership` | POSSIBLY_DEAD (unconfirmed) | **live caller found:** `dashboard/views.py:5896 staff_transfer_ownership`, route `dashboard/urls.py:390 staff/<pk>/transfer-ownership/` | **DISPROVED as dead** → see doc 06 correction; upgrades ownership-transfer ambiguity |
| **D4** ShopSettings legacy SMS fields | POTENTIALLY_DEAD (data) | `sms_service.py` reads `shop.sms_backend` only for `== SMSRASTI`; melipayamak/kavenegar use `template` + `owner_sms_service` (PlatformConfiguration), not ShopSettings creds | **CONFIRMED** (legacy credential fields inert) |
| **D6** `resolution.require_resolved_store` | POSSIBLY unused (unconfirmed) | no non-test caller found (only its own docstring/exception ref) | **CONFIRMED POTENTIALLY_DEAD** (no live caller; may be intentional API scaffolding — not deleted) |
| **D7** reserved authorization permission keys | inert forward-design | 4 "reserved" markers in `authorization.py`; no view/decorator reads them | **CONFIRMED** (intentional, inert) |

D2 (conditionally-live) and D8 (live-but-inert) were already non-dead in Phase 1 and are
unchanged; D5 (removed registries) is confirmed-absent above.
