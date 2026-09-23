# Data Ownership

```
status: CANONICAL
code_baseline: 5883a140
last_verified_against_code: 5883a140
source_phases: Phase 1 (doc 03) / Phase 2
```

Model → owning domain, with the important lifecycle fields and constraints. This is the "who owns
this model" reference. For "who is allowed to write it" see
[`MUTATION_AUTHORITY.md`](MUTATION_AUTHORITY.md). Detail per domain: `../domains/<app>/DATA_MODEL.md`.

Legend: **[LC]** = lifecycle/status field; **[U]** = unique/constraint of note.

---

## D1 `stores` (tenant boundary)
- **Store** — [LC] `status` (provisioning/active/suspended/closed), `onboarding_stage`,
  `onboarding_completed_at` (null ⇒ private), soft-delete + suspension fields. [U] `slug`,
  `admin_subdomain`, `platform_code`, `public_id` all unique. No `owner` field.
- **StoreDomain** — [LC] `verification_status`, `routing_status`, `tls_status`, `retired_at`,
  `is_primary`, `domain_type`. [U] `hostname` unique; partial `uniq_primary_domain_per_store`;
  5 CheckConstraints. Hostname write path guarded (`StoreDomainQuerySet`).
- **StoreMembership** — [LC] `role`, `status`. [U] `uniq_active_owner_per_store`. `user` PROTECT.
- **StoreOwnershipTransfer** — [LC] `status` (pending/completed/expired/cancelled).
- **StoreIntegrationConnection** — non-payment integrations; credentials via `orders.encryption`.

## D2 `portal` (platform control)
- **OwnerProfile**, **OwnerOtpChallenge**, **AdminHandoffTicket**, **PlatformConfiguration**
  (pk=1 singleton), **PlatformAuditLogEntry**, **PlatformInternalNote**, **ContactMessage**.

## D3 `customers`
- **Customer** (global — no store FK; phone-keyed), **CustomerProfile** (store-scoped),
  **CustomerTag**, **CustomerNote**, **CustomerSegment** (+Rule/+Membership), **Address**,
  **Wishlist**.

## D4 `catalog` (38 model classes)
- **Product** — [LC] `status` (draft/active/inactive), `visibility`, `publish_at`,
  `is_draft_placeholder`, `stock`. [U] `uniq(store,slug)`, `uniq(store,sku)`.
- **ProductVariant** — QuerySet blocks bulk normalization bypass. **StockMovement** (ledger).
- **Category**, **Brand**, **Vendor** (coexists with Store — A1). **MerchantCollection**(+Item).
- **Warehouse**, **WarehouseInventory**, **InventoryReservation**, **WarehouseTransfer**(+Item, [LC]).
- **IndustryTemplate** (platform-owned, [LC] Readiness) + family; **StoreIndustryInstallation**,
  **StoreTemplateUpdate** ([LC]). Plus attributes/options/specs/reviews/metafields/tags.

## D5 `cart`
- **Cart** (`checkout_token` idempotency anchor), **CartItem** (`unit_price` snapshot),
  **Coupon** ([U] `uniq_coupon_code_per_store`).

## D6 `orders` (16 model classes) — ★ see [gold-standard pack](../domains/orders/README.md)
- **Order** — [LC] `status` (guarded), **`payment_status` (NOT guarded — 3 writers, H1)**.
  [U] `code`, partial `uniq_order_idempotency_key_when_set`.
- **OrderItem**, **OrderStatusHistory**, **Transaction** (legacy payment), **PaymentAttempt** (new),
  **PaymentGatewayConfig** + **PaymentGateway** (dual — M4), **Refund**(+Item, MANUAL only),
  **ReturnRequest**(+Item, model-level `ALLOWED_TRANSITIONS`), **ShippingZone/Method/RateRule**,
  **TaxClass/TaxRate**.

## D7 `subscriptions`
- **StoreSubscription** — [LC] `status` (guarded, `ALLOWED_TRANSITIONS`), `is_current`
  ([U] `uniq_current_subscription_per_store`). **Plan**, **PlanVersion** ([LC]),
  **EntitlementDefinition**, **PlanEntitlement**, **SubscriptionEvent** (idempotency), **UsageRecord**.

## D8 `billing`
- **SubscriptionInvoice** ([LC] status; [U] `number`, partial `uniq_renewal_invoice_per_period`),
  **SubscriptionInvoiceLine**, **SubscriptionPaymentAttempt** ([LC]), **BillingWebhookEvent**
  ([U] `(provider, external_event_id)` dedup), **SubscriptionDunningState**,
  **SubscriptionCreditNote**, **SubscriptionRefund**, **ScheduledPlanChange**, **BillingSequence**,
  **StoreBillingAccount**.

## D9 `storefront_builder`
- **StorefrontLayout** (`r4_editor_enabled` default True; publish pointers),
  **StorefrontLayoutVersion** ([LC] draft/published/archived), **StorefrontPage** (6 typed slots),
  **StorefrontSection**, **StorefrontContainer**, **StorefrontCell** (dual placement — M12),
  **StorefrontEditHistoryEntry**.

## D10 `content` (mutated by `dashboard`, not a content service — H2 / DR-2)
- **ContentPage** ([LC] draft/published), **Menu**, **MenuItem**, **FooterSettings** (3rd footer
  representation — M2), **FooterTrustBadge**, **FooterPaymentLogo**, **HeroSlide**,
  **PromotionalBanner**, **StoryRailItem** (FK into `storefront_builder.StorefrontSection`),
  **MediaAsset**, **SocialLink**, **NewsletterSubscriber**, + **DestinationMixin** (abstract).

## D11 `dashboard`
- **No models** (`models.py` empty). Controller only.

## D12 `sms`
- **SmsTemplate**, **SmsBillingPolicy** (pk=1 platform singleton), **SmsLog**, **SmsOutboxItem**
  ([LC] device queue), **SmsBalance**, **SmsPackage**(+Purchase), **SmsCreditAdjustment**, **OtpCode**.

## D13 `notifications`
- **NotificationOutbox** ([LC] channel/status).

## D14 `core` (cross-cutting)
- **TimeStampedModel** (abstract base; NOT reused by `stores`), **ShopSettings** (store-scoped
  OneToOne; legacy SMS fields POTENTIALLY_DEAD), **AuditLogEntry** (immutable), **ExportJob**,
  **ImportJob**(+RowResult).

## D15 `blog`
- **BlogPost** (admin-only; no urls/views — POTENTIALLY_DEAD storefront wiring).

---

## Cross-domain ownership notes
- **`content.HeroSlide/PromotionalBanner/StoryRailItem`** FK **into** `storefront_builder.StorefrontSection`
  (CASCADE) — the tightest content↔builder coupling.
- **`stores` deliberately does not import `core`** (duplicates `TimeStampedModel`) to avoid a future
  `core→stores` cycle.
- **`ShopSettings` is owned by `core`** but write authority is spread (dashboard + sms_service) —
  see MUTATION_AUTHORITY and finding around ShopSettings.

Model-relationship graph: [`graphs/model_relationships.mmd`](graphs/model_relationships.mmd).
