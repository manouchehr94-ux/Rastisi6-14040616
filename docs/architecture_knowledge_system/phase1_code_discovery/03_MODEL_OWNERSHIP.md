# 03 — Model Ownership

For each important model: defining app, owning domain, key lifecycle fields, key constraints,
and ownership notes. Full mutation writers are in doc 06; state machines in doc 09.

Evidence class legend as in doc 01. Line ranges are approximate where a file exceeded a single
read and are marked `~`.

---

## 1. Tenancy — `apps/stores/models.py` (VERIFIED)

| Model | Key lifecycle fields | Key constraints | Ownership note |
|---|---|---|---|
| **Store** | `status` (PROVISIONING/ACTIVE/SUSPENDED/CLOSED), `onboarding_stage` (IDENTITY→INDUSTRY→BRANDING→REVIEW→DONE), `onboarding_completed_at` (null ⇒ private), soft-delete (`deletion_requested_at/by`, `deletion_scheduled_purge_at`, `pre_deletion_status`), suspension (`suspended_at/by`, `suspension_reason`) | `slug` unique (global), `admin_subdomain` unique (ASCII/DNS), `platform_code` unique (9-char, editable=False), `public_id` unique UUID | The tenant boundary. **No `owner` field** — ownership = active OWNER membership. `save()` auto-fills admin_subdomain/platform_code fallbacks. |
| **StoreDomain** | `verification_status` (UNVERIFIED/PENDING/VERIFIED/FAILED), `routing_status`, `tls_status`, `retired_at`, `is_primary`, `domain_type` (GENERATED_TRIAL/PLATFORM_SUBDOMAIN/CUSTOM_DOMAIN) | `hostname` unique (normalized); partial uniques `uniq_primary_domain_per_store`, `uniq_verification_token_when_set`; 5 CheckConstraints tying status↔timestamps↔token; `retired_domain_is_never_primary` | Hostname write path guarded: `StoreDomainQuerySet.update(hostname=)` raises `StoreDomainMutationError`; `bulk_create` normalizes. `domain_type` is descriptive, not routing-determining (ADR-95). |
| **StoreMembership** | `role` (OWNER/ADMINISTRATOR/CATALOG_MANAGER/ORDER_MANAGER/CONTENT_EDITOR/ANALYST), `status` (INVITED/ACTIVE/REVOKED) | `uniq_membership_per_store_user`; **`uniq_active_owner_per_store`** (partial); accepted/revoked timestamp checks | `user` on_delete=**PROTECT** (deleting a user with memberships raises ProtectedError). Authoritative ownership link. |
| **StoreOwnershipTransfer** | `status` (PENDING/COMPLETED/EXPIRED/CANCELLED), `expires_at` | `token` unique (auto secrets), `uniq_pending_ownership_transfer_per_store` | Two-party OTP-gated transfer. |
| **StoreIntegrationConnection** | `is_active` | `uniq_integration_per_store_provider` | Non-payment integrations (eNamad/Torob/GA/GTM/pixel). Reuses `apps.orders.encryption` for credentials. |

## 2. Platform control — `apps/portal/models.py` (VERIFIED)

| Model | Key fields | Note |
|---|---|---|
| **OwnerProfile** | OneToOne User; `phone` unique/nullable | Owner identity extension (ADR-93), separate from Customer. |
| **OwnerOtpChallenge** | `code_hash`, `purpose` (REGISTER/LOGIN/STEP_UP), `attempt_count`, `expires_at`, `consumed_at` | Never stores plaintext OTP. |
| **AdminHandoffTicket** | single-use, short-lived; `issued_by_platform_admin` | Bridges portal-host auth to Store admin host (support login). |
| **PlatformConfiguration** | pk forced to 1 in `save()` | **True platform-wide singleton.** Trial defaults, `deletion_retention_days`, `step_up_actions` (allowlisted), central SMS backend + encrypted creds, platform Zibal creds, maintenance_mode, registration flag, enamad. |
| **PlatformAuditLogEntry** | platform-level audit | Not store-owned (used for purge/config/plan). |
| **PlatformInternalNote** | CheckConstraint: exactly one of store/about_user | — |
| **ContactMessage** | marketing contact form | — |

## 3. Customer/CRM — `apps/customers/models.py` (VERIFIED)

| Model | Key fields | Note |
|---|---|---|
| **Customer** | OneToOne User; `phone` unique | **Global — no store FK** (ADR-50/93). Login identity. |
| **CustomerProfile** | cached stats; `internal_status` | Store-scoped projection (`uniq_customerprofile_per_store`). Stats refreshed explicitly (no signals, ADR-50). |
| **CustomerTag / CustomerNote** | store-scoped | `uniq_customertag_code_per_store`. |
| **CustomerSegment (+Rule/+Membership)** | `segment_type`, `match_mode` | Store-scoped; `uniq_segment_membership`. |
| **Address / Wishlist** | — | Wishlist unique (customer, product). |

## 4. Catalog & inventory — `apps/catalog/models.py` (VERIFIED, ~30 models)

| Model | Key lifecycle fields | Key constraints | Note |
|---|---|---|---|
| **Product** | `status` (active/inactive/draft), `visibility` (public/link_only), `publish_at`, **`is_draft_placeholder`** (independent build-in-progress flag), `stock` | `uniq(store,slug)`, `uniq(store,sku)` | Two orthogonal lifecycles: publish-status vs draft-placeholder. FK store CASCADE, category PROTECT (nullable for drafts). |
| **ProductVariant** | `is_default`, `is_obsolete`, `combination_key` | 4 unique constraints | `store` copied from product; `ProductVariantQuerySet` blocks `update()/bulk_update()/bulk_create()` normalization bypass (`VariantMutationError`). |
| **StockMovement** | append-only ledger | — | Canonical inventory audit; stock never changes without a movement. |
| **Warehouse / WarehouseInventory / InventoryReservation / WarehouseTransfer(+Item)** | reservation `Status` (active/consumed/released/expired/cancelled); transfer has explicit `ALLOWED_TRANSITIONS` (draft→requested→in_transit→received/cancelled) | — | Inventory sub-domain. |
| **Category / Brand / Vendor** | Category tree (self-FK) | `uniq(store,slug)` | `Vendor` coexists with `stores.Store` (ADR-1, AMBIGUOUS_OWNERSHIP — doc 13). |
| **MerchantCollection(+Item)** | — | — | Curated product collections. |
| **IndustryTemplate (+ category/attribute/mapping/recommended)** | `Readiness` (draft/validation_failed/review_required/production_ready/deprecated/archived) | `content_fingerprint` | **Platform-owned** (no Store FK); installed by deep-copy into Store-owned rows. |
| **StoreIndustryInstallation / StoreTemplateUpdate** | update `Status` (pending/completed/failed), `idempotency_key` | OneToOne store (installation) | Rollback-capable pair; storefront layout versioning modeled on this pattern. |
| **Attribute/AttributeValue/ProductAttributeValue, ProductTag, ProductMetafield, ProductOption(+Value), VariantOptionValue, Specification(+Template/Field), Review, CategoryAttributeSchema/CategoryRecommendedOption** | — | — | Supporting catalog data. |

## 5. Cart — `apps/cart/models.py` (VERIFIED)

| Model | Key fields | Note |
|---|---|---|
| **Cart** | `customer` (nullable), `session_key`, **`checkout_token`** (server idempotency anchor) | No status field. |
| **CartItem** | `unit_price` (server snapshot), gift-wrap fields | Price always from catalog effective-price resolver. |
| **Coupon** | `type` (PERCENT/FIXED/FREE_SHIP), `value`, `usage_limit`, `used_count`, `expires_at`, `is_active` | `uniq_coupon_code_per_store`. Store-owned. |

## 6. Orders (storefront money) — `apps/orders/models.py` (VERIFIED; line ranges ~ past 640)

| Model | Key lifecycle fields | Key constraints | Note |
|---|---|---|---|
| **Order** | `status` (pending/processing/shipped/delivered/canceled — guarded), `payment_status` (pending/paid/failed/refunded — **NOT guarded**) | `code` unique; partial `uniq_order_idempotency_key_when_set` | FKs mostly PROTECT (store/customer/vendor/shipping_method/payment_gateway). Money snapshots. `clean()` enforces vendor.store == order.store. |
| **OrderItem** | product/sku/variant + price/tax snapshots; `fulfillment_warehouse` | — | Immutable line snapshot. |
| **OrderStatusHistory** | from/to status, changed_by, note | — | Order audit trail. |
| **Transaction** *(LEGACY payment)* | `status` (ok/pending/fail/refund) | `code` unique | Legacy record; also created by the new gateway path "for dashboard back-compat" (dup — doc 13). |
| **PaymentAttempt** *(NEW payment)* | `status` (created/requesting/redirect_ready/pending/succeeded/failed/canceled/expired; FINAL set) | partial uniques on `idempotency_key`, `gateway_track_id`; `public_id` auto | Immutable snapshots; `is_final`/`is_successful`. |
| **PaymentGatewayConfig** *(NEW)* / **PaymentGateway** *(LEGACY)* | `is_active`; `gateway_code` (zibal/cod) | `uniq(store, gateway_code)` | **Dual gateway representation** (config vs order-chosen slug) — AMBIGUOUS_OWNERSHIP (doc 13). Encrypted credentials. |
| **Refund (+RefundItem)** | `status` (pending/approved/processing/succeeded/failed/cancelled), `method` (manual/gateway) | non-negative CheckConstraints; partial unique idempotency_key | **Only MANUAL refund is implemented** (ADR-33); GATEWAY raises. |
| **ReturnRequest (+ReturnItem)** | full `Status` machine with **model-level `ALLOWED_TRANSITIONS`** | — | requested/under_review/approved/rejected/in_transit/received/inspected/completed/cancelled. |
| **ShippingZone/Method/RateRule, TaxClass/TaxRate** | config | — | Store-scoped commerce configuration. |

## 7. Subscriptions (platform money) — `apps/subscriptions/models.py` (VERIFIED)

| Model | Key lifecycle fields | Key constraints | Note |
|---|---|---|---|
| **StoreSubscription** | `status` (pending/trialing/active/grace_period/past_due/suspended/cancelled/expired; TERMINAL={cancelled,expired}), `source`, `is_current`, `cancel_at_period_end` | **`uniq_current_subscription_per_store`** (partial `is_current=True`) | The canonical platform-billing state machine (subject). |
| **Plan / PlanVersion** | version `Status` (draft/published/retired/archived), `billing_interval`, `trial_days`, `grace_period_days` | `uniq(plan, version_number)`; `Plan.code` unique | Immutable-after-use plan codes. |
| **EntitlementDefinition / PlanEntitlement** | `entitlement_type`; `is_unlimited` | `key` unique; `uniq(plan_version, entitlement)`; integer≥0 check | Entitlement matrix. |
| **SubscriptionEvent** | immutable domain history; large `EventType` enum | partial unique `(subscription, idempotency_key)` | Idempotency + audit. |
| **UsageRecord** | period counters | `uniq(store, metric_key, period_start)` | — |

## 8. Billing (platform money) — `apps/billing/models.py` (VERIFIED)

| Model | Key lifecycle fields | Key constraints | Note |
|---|---|---|---|
| **SubscriptionInvoice** | `status` (draft/open/payment_pending/paid/past_due/void/uncollectible/refunded/partially_refunded); `kind` (initial/renewal/plan_change/manual); `FINANCIALLY_LOCKED_STATUSES`, `PAYABLE_STATUSES` | `number` unique; partial `uniq_renewal_invoice_per_period`; amount checks (`amount_paid ≤ grand_total`) | Immutable account snapshot embedded. |
| **SubscriptionInvoiceLine** | `line_type` (plan/proration_*/discount/tax/manual_adjustment) | — | — |
| **SubscriptionPaymentAttempt** | `status` (created/pending/requires_action/succeeded/failed/cancelled/expired; FINAL set) | `public_token` unique, `idempotency_key` unique, partial `(provider, provider_payment_id)` | Separate from orders.PaymentAttempt. |
| **BillingWebhookEvent** | `processing_status` (received/processed/failed/ignored) | `uniq(provider, external_event_id)` (dedup) | Inbox; redacted payload. |
| **SubscriptionDunningState** | `status` (active/resolved/exhausted), stage, next_retry_at | OneToOne invoice | — |
| **SubscriptionCreditNote / SubscriptionRefund** | credit `status` (draft/issued/void); refund `status` (requested/pending/succeeded/failed/cancelled) | amount>0 checks; refund `idempotency_key` unique + partial provider_refund_id | Refund docstring: never uses order Refund models. |
| **ScheduledPlanChange** | next-period downgrade | OneToOne subscription | — |
| **BillingSequence** | race-safe counter | select_for_update | Numbering source. |
| **StoreBillingAccount** | `snapshot()` | OneToOne store | — |

## 9. Storefront presentation — `apps/storefront_builder/models.py` (VERIFIED)

| Model | Key lifecycle fields | Key constraints | Note |
|---|---|---|---|
| **StorefrontLayout** | `uses_visual_storefront_layout`, `r4_editor_enabled` (default **True**), `published_version`/`draft_version` pointers | OneToOne Store | Publish = pointer swap. `r4_editor_enabled` gates active editor generation. |
| **StorefrontLayoutVersion** | `status` (draft/published/archived), `source` (manual/legacy_bootstrap/industry_template/restored), `content_fingerprint`, `template_provenance`, `template_baseline_snapshot`, `edit_revision` (optimistic token) | `uniq(layout, version_number)` | Immutable-after-publish snapshot of header/footer/appearance + all 6 pages. |
| **StorefrontPage** | `page_type` (home/product_detail/listing/collection/search/cart), `page_appearance_overrides` | `uniq(version, page_type)` | 6 typed slots; `ensure_version_pages` idempotent. Distinct from `content.ContentPage`. |
| **StorefrontSection** | `section_key` (validated in service vs SECTION_REGISTRY), `order`, `is_active`, `settings`, `stable_id`, legacy `row_key/row_span`, `cell` FK + `cell_order` | `uniq(page, stable_id)`; `uniq(cell, cell_order)` when cell set | DB owner is `page`; a `version=` init-shim resolves to home. |
| **StorefrontContainer / StorefrontCell** | container per page; cell `span` (1–12 check) | — | Newer layout mechanism; `StorefrontCell.section` OneToOne is "executing truth", `StorefrontSection.cell` FK is "parallel/future" (dup — doc 13). |
| **StorefrontEditHistoryEntry** | `sequence`, `is_undone`, before/after JSON | `uniq(draft_version, sequence)` | Draft-only undo/redo; wiped at publish. |

## 10. Content & navigation — `apps/content/models.py` (VERIFIED)

| Model | Key lifecycle fields | Note |
|---|---|---|
| **ContentPage** | `status` (draft/published), `published_at/by`, footer placement | `uniq(store, slug)`; published requires timestamp. Second "page" concept. |
| **Menu / MenuItem** | `location` (header/footer_1/footer_2/footer_3/mobile); 2-level hierarchy | `uniq(store, location)`. Navigation via `DestinationMixin` safe-link. |
| **FooterSettings** | ~25 toggles | OneToOne Store — **third footer representation** (doc 13). |
| **HeroSlide / PromotionalBanner / StoryRailItem** | section-scoped placements | FK Store + FK `storefront_builder.StorefrontSection` (CASCADE). Dual media (legacy ImageField + MediaAsset FK). |
| **MediaAsset** | `is_referenced()` fail-closed | Store-owned physical media. |
| **SocialLink / FooterTrustBadge / FooterPaymentLogo / NewsletterSubscriber** | — | `uniq(store, email)` for subscribers. |

## 11. Cross-cutting — `apps/core/models.py` (VERIFIED)

| Model | Scope | Note |
|---|---|---|
| **TimeStampedModel** | abstract | Shared base (NOT reused by `stores`, by design). |
| **ShopSettings** | **store-scoped** (OneToOne Store) | Single per-Store identity/tax/branding source; `load(store=)` raises if unprovisioned. Legacy SMS fields POTENTIALLY_DEAD. |
| **AuditLogEntry** | store-scoped, immutable | No ContentType/IP/UA (ADR-36). |
| **ExportJob / ImportJob (+RowResult)** | store-scoped | Synchronous jobs; private storage; import idempotency unique. |

## 12. Ownership ambiguities (summary; full in doc 13)
- **`stores.Store` vs `catalog.Vendor`** — both represent a "seller-ish" entity; Store docstring
  says they are distinct (ADR-1) but the coexistence contract is not fully expressed in code →
  AMBIGUOUS_OWNERSHIP.
- **Footer** — `StorefrontLayoutVersion.footer_config` (JSON) vs `content.FooterSettings` (model)
  vs footer chrome variant (`global_region_registry`).
- **"Page"** — `storefront_builder.StorefrontPage` vs `content.ContentPage`.
- **`ShopSettings`** — owned by `core`, but write authority spread across dashboard views and
  sms_service; carries dead legacy SMS fields.
- **Section placement** — `StorefrontCell.section` (OneToOne, live) vs `StorefrontSection.cell`
  (FK, parallel) vs legacy `row_key/row_span`.
