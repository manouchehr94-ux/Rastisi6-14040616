# 12 — Architecture-Smell Audit

Findings are classified by severity (CRITICAL/HIGH/MEDIUM/LOW/OBSERVATION) and evidence class.
Per the governing document, these are **recorded, not repaired**. Severity reflects change-risk /
correctness / duplication impact, justified by evidence; it is not inflated.

Many of these patterns are **deliberate, self-documented migrations** (Strangler-style). That is
noted where true, but the *coexistence itself* is still recorded as a smell because it widens the
surface a future change must reason about.

---

## CRITICAL

_None asserted with confidence._ The highest-risk finding (Order.payment_status) is rated HIGH
rather than CRITICAL because the most dangerous writer (`simulate_payment`) is production-gated by
`PAYMENTS_SIMULATION_ENABLED` and the live gateway path is lock-protected. Elevate to CRITICAL only
if evidence shows the simulation path reachable in production.

---

## HIGH

### H1 — Duplicate order-payment implementation + unguarded `Order.payment_status` — VERIFIED
Two payment implementations write the same field:
- Legacy: `orders.Transaction` + `payment_service.simulate_payment` (direct save PAID/FAILED).
- New: `orders.PaymentAttempt` + `gateway_payment_service.process_callback_and_verify` (lock +
  conditional update), which *also* creates a legacy `Transaction` "for dashboard back-compat".
Plus `refund_service` writes PAID→REFUNDED.
`Order.payment_status` has **no `ALLOWED_TRANSITIONS` table** (unlike `Order.status`,
`ReturnRequest.status`, `StoreSubscription.status`). Three writers; only one locks the Order.
- **Evidence:** `payment_service.py:86-98`, `gateway_payment_service.py:315,353`, `refund_service.py:234`.
- **Risk:** duplicate mutation path + no single guarded boundary for a money field.
- **Future decision required:** yes (choose canonical writer; add transition guard). Do not fix now.

### H2 — `content` domain has no write service; mutated wholesale by `dashboard` views — VERIFIED
`apps/content/services.py` is read/resolve-only (destination URLs, media retention no-ops,
newsletter). All ContentPage/Menu/MenuItem/FooterSettings/HeroSlide/PromotionalBanner/SocialLink/
FooterTrustBadge/FooterPaymentLogo writes are raw `.save()`/`.full_clean()`/`.delete()` in
`dashboard/views.py` (≈ lines 4744–5633). The content model layer owns data but the dashboard view
layer is its de-facto service.
- **Risk:** business logic + multi-object mutations in the presentation/controller layer; no
  transaction/service boundary; cross-domain ownership blur.
- **Class:** CROSS_DOMAIN_WRITE / business-logic-in-controller.

### H3 — Three storefront editor/template generations coexist — VERIFIED
- Legacy/R3: `storefront_builder/views.py` (~3124 LOC) + legacy `row_key/row_span` section model +
  removed `family_registry.py`/`preset_registry.py` (files confirmed absent; only referenced in
  docstrings/tests).
- R4: `r4_views.py` + `r4_mutation_service.py` + Container/Cell model + `settings_schema` Strangler +
  `storefront_appearance` typed engine. **Default** (`r4_editor_enabled=True`).
- A8: `a8_ready_templates.py` (50 Ready Templates) on `layout_preset_registry.py`.
Legacy mutation routes are wired but **fail-closed** via `_require_legacy_editor_active` when R4 is
active.
- **Risk:** two live write surfaces for the same concept; large legacy view retained though guarded.
- **Class:** LEGACY_PARALLEL_PATH / AMBIGUOUS_OWNERSHIP (of the write surface).

---

## MEDIUM

### M1 — Duplicate appearance/theme/palette sources of truth — VERIFIED
Palettes exist in both `appearance_registry.PaletteDefinition` and `palette_pack_64.py`; appearance
templates in `appearance_registry`; occasion themes in `theme_catalog.py`; all re-projected into the
typed `storefront_appearance.COMPONENT_REGISTRY`. Persisted merchant appearance lives in
`StorefrontLayoutVersion.appearance_config` and is *mirrored* into `header_config`/`footer_config`
by `persist_store_appearance_manifest` (e.g. `header_variant` stored twice).
- **Class:** DUPLICATE_SOURCE_OF_TRUTH / configuration duplication.

### M2 — Footer represented three ways — VERIFIED
`StorefrontLayoutVersion.footer_config` (JSON toggles) vs `content.FooterSettings` (~25-field model)
vs footer chrome variant (`global_region_registry`). No single owner.

### M3 — Two "page" concepts — VERIFIED
`storefront_builder.StorefrontPage` (typed 6-slot layout pages) vs `content.ContentPage` (CMS pages
with own draft/publish). Distinct but both called "page".

### M4 — Dual gateway representation in orders — VERIFIED
`orders.PaymentGateway` (legacy order-chosen slug) vs `orders.PaymentGatewayConfig` (operational
config). `payment_initiate` fuzzily matches config to the order's legacy gateway slug (falls back to
"any active online config"). AMBIGUOUS_OWNERSHIP of "which gateway".

### M5 — Dashboard direct mutation of other apps' config models — VERIFIED
`ShopSettings` (core), `ShippingZone/Method/RateRule`, `TaxClass/TaxRate`, `PaymentGatewayConfig`
(orders) are written directly in `dashboard/views.py` (incl. credential encryption at ~5726–5784)
rather than via the owning app's service. Contrast: order-status, refunds, catalog products (mostly)
go through services. Dashboard is a thin controller for some domains, thick for others.

### M6 — Two ownership-transfer implementations — VERIFIED / AMBIGUOUS_OWNERSHIP
`stores.membership_service.transfer_ownership` (direct, synchronous, membership-to-membership) and
`stores.ownership_transfer_service` (two-party OTP-gated via `StoreOwnershipTransfer`). Both demote
OWNER→ADMINISTRATOR and promote a new owner. Which is canonical for the portal UI is unclear;
`membership_service.transfer_ownership` may be POTENTIALLY_DEAD relative to the OTP flow (not confirmed).

> **[PHASE 2 CORRECTION 2026-09-23 — UPGRADED]** `membership_service.transfer_ownership` is
> confirmed **LIVE** (merchant dashboard route `staff/<pk>/transfer-ownership/` →
> `dashboard/views.py:5896`). Both paths are therefore live → this is a genuine **duplicate
> mutation path** for `StoreMembership` owner reassignment, not one-live-plus-one-maybe-dead.
> The smell is *strengthened*. See `../phase2_validation/06_PHASE1_CORRECTIONS.md` (C1).

### M7 — billing co-owns the subscription state machine (tight cross-domain coupling) — VERIFIED
Billing services (confirmation/dunning/renewal/cancellation) drive `StoreSubscription` transitions.
Correctly funneled through `subscription_service` (no direct status writes), but subscription
lifecycle is effectively co-owned. Plan-change logic is split across
`subscriptions.plan_change_service` (preview + platform override) and
`billing.plan_change_billing_service` (merchant purchase/schedule).

### M8 — Derived "store visibility" spans ≥5 signals across 3 apps — VERIFIED
`Store.status` + `Store.onboarding_completed_at` + `StoreDomain` verification/routing +
`StoreSubscription`/entitlement. `publication_service` reconciles them but **fails open**
(AccessState.NONE → ACTIVE_PAID). Multiple interacting state signals → hard to reason about;
fail-open is a deliberate legacy-safety choice.

### M9 — `orders → cart` cross-domain mutation — VERIFIED
Orders writes `CartItem.unit_price` (reprice), deletes cart items (`finalize_order`, checkout
views), and increments `Coupon.used_count`. Cart exposes no service for these; orders reaches into
`cart.items`.

### M10 — Dual settings validation (Strangler) — VERIFIED
`settings_schema.clean_schema_patch` runs, then legacy `SectionDefinition.validate_settings` runs —
two validation mechanisms mid-migration.

### M11 — Dual media representation on placements — VERIFIED
Hero/Banner/Story carry legacy `desktop_image`/`mobile_image` ImageFields AND newer
`desktop_asset`/`mobile_asset` MediaAsset FKs, resolved by `_resolve_placement_media_url` fallback.

### M12 — Dual/parallel section-placement mechanisms — VERIFIED (self-documented)
`StorefrontCell.section` (OneToOne, "executing truth today") vs `StorefrontSection.cell` (FK,
"parallel/future") vs legacy `row_key/row_span` — three coexisting layout mechanisms.

### M13 — Latent circular-dependency management — VERIFIED
`stores` duplicates `core.TimeStampedModel`; `publication_service`/render callers use local imports;
catalog defers section-key validation to storefront_builder — all to avoid module-level cycles.
Managed, but latent.

### M14 — Asymmetric import/export placement — VERIFIED
`export_service` lives in `core/services`; `import_service` lives in `dashboard/services`. Symmetric
features, split ownership.

### M15 — `is_staff` overloading — VERIFIED
`membership_service.add_staff_member` sets `User.is_staff=True`; `dashboard.staff_required`
deliberately **ignores** `is_staff` (uses StoreMembership); platform admin **requires**
`is_staff`+`is_superuser`; Django `/admin/` is superuser-only. Three meanings of one flag.

---

## LOW

### L1 — `simulate_payment` lacks Order `select_for_update` — VERIFIED (prod-gated). See doc 10.
### L2 — `checkout_item_update/remove` mutate CartItem outside the checkout fence — VERIFIED. See doc 10.
### L3 — Duplicated PageType strings — VERIFIED. The 6 page types are hardcoded in
`section_registry.py`/`a8_ready_templates.py` rather than imported from the model enum; kept in sync
only by `PageTypeConstantsMatchModelTests`.
### L4 — Parallel "already paid" guards — INFERRED. Repeated across simulate/initiate/callback with
slightly different semantics (raise vs cancel-attempt vs redirect).

---

## OBSERVATION (context, not necessarily defects)

- **O1 — No signals anywhere (deliberate).** Side effects are explicit service calls + on_commit.
  This is a *good* explicit-coupling posture but means "what happens after X" must be traced through
  callers, not signal receivers.
- **O2 — MED-001 retention no-ops.** `content.delete_media_asset_if_unreferenced` /
  `cleanup_reusable_media_file` are intentional no-ops (accept small storage leak to remove a TOCTOU
  race); live call sites remain but do nothing. Deferred GC.
- **O3 — Reserved permission keys.** `stores.authorization` defines permission constants marked
  "reserved — no view yet" plus back-compat aliases nothing reads. Forward-design, currently inert.
- **O4 — Historical tenant-bleed fixed.** `dashboard_service`/`report_service` docstrings record a
  prior cross-store figures bug, since fixed by `Order.store` scoping.

---

## Cross-reference
- Mutation duplication detail → doc 06. State-machine detail → doc 09. Transaction weakness → doc 10.
- Dead/orphan candidates (blog, membership.transfer_ownership, ShopSettings legacy SMS fields,
  removed registries) → doc 13. Ambiguities/unknowns → doc 14.
